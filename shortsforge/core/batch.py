"""Очередь записей: поставить несколько файлов и уйти спать.

Каждый файл проходит тот же путь, что и в одиночном режиме (подготовка → быстрый поиск
моментов → отбор → сборка роликов), но без участия человека. Состояние очереди хранится
в `%LOCALAPPDATA%\\ShortsForge\\queue.json`, поэтому после перезапуска видно, что уже сделано,
а повторный прогон не пересчитывает готовое.

Один сломанный файл не останавливает очередь: ошибка записывается в его строку, остальные едут.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import pipeline
from .config import Settings

STATUS_WAIT = "ждёт"
STATUS_WORK = "в работе"
STATUS_DONE = "готово"
STATUS_FAIL = "ошибка"
STATUS_SKIP = "пропущено"


def queue_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home())
    folder = base / "ShortsForge"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "queue.json"


@dataclass
class QueueItem:
    path: str
    status: str = STATUS_WAIT
    clips: int = 0
    detail: str = ""
    duration_min: float = 0.0
    spent_min: float = 0.0

    @property
    def name(self) -> str:
        return Path(self.path).name


@dataclass
class BatchReport:
    done: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    clips: int = 0

    def as_text(self) -> str:
        parts = [f"готово записей: {len(self.done)}", f"роликов собрано: {self.clips}"]
        if self.failed:
            parts.append("ошибки: " + "; ".join(f"{n} — {e[:80]}" for n, e in self.failed))
        if self.skipped:
            parts.append(f"пропущено: {len(self.skipped)}")
        return ". ".join(parts)


class Queue:
    """Список записей с сохранением на диск."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else queue_path()
        self.items: list[QueueItem] = []
        self.load()

    def load(self) -> None:
        self.items = []
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        for raw in data.get("items") or []:
            try:
                item = QueueItem(**{k: v for k, v in raw.items()
                                    if k in QueueItem.__dataclass_fields__})
            except TypeError:
                continue
            # «в работе» после перезапуска — снова «ждёт»
            if item.status == STATUS_WORK:
                item.status = STATUS_WAIT
            self.items.append(item)

    def save(self) -> None:
        try:
            self.path.write_text(json.dumps({"items": [asdict(i) for i in self.items]},
                                            ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass

    def add(self, paths: list[str]) -> int:
        known = {str(Path(i.path).resolve()) for i in self.items}
        added = 0
        for p in paths:
            key = str(Path(p).resolve())
            if key in known:
                continue
            self.items.append(QueueItem(path=key))
            known.add(key)
            added += 1
        self.save()
        return added

    def remove(self, index: int) -> None:
        if 0 <= index < len(self.items):
            del self.items[index]
            self.save()

    def clear_finished(self) -> None:
        self.items = [i for i in self.items if i.status not in (STATUS_DONE, STATUS_SKIP)]
        self.save()

    def reset_failed(self) -> None:
        for item in self.items:
            if item.status == STATUS_FAIL:
                item.status = STATUS_WAIT
                item.detail = ""
        self.save()

    def pending(self) -> list[int]:
        return [i for i, item in enumerate(self.items) if item.status in (STATUS_WAIT, STATUS_FAIL)]


def run_queue(queue: Queue, cfg: Settings, progress=None, cancel=None,
              clips_per_file: int | None = None) -> BatchReport:
    """Проходит очередь до конца. Возвращает отчёт."""
    from . import media

    progress = progress or (lambda *a, **k: None)
    report = BatchReport()
    todo = queue.pending()
    if not todo:
        progress(1.0, "в очереди нечего делать")
        return report

    per_file = clips_per_file or max(1, cfg.ai_clips)
    for n, index in enumerate(todo):
        item = queue.items[index]
        if cancel and cancel():
            item.status = STATUS_WAIT
            queue.save()
            raise RuntimeError("отменено")

        base_share = n / len(todo)

        def sub(value, text="", base_share=base_share, n=n, item=item):
            total = base_share + (value or 0) / len(todo)
            progress(min(0.999, total),
                     f"[{n + 1}/{len(todo)}] {item.name}: {text}" if text else item.name)

        started = time.time()
        item.status = STATUS_WORK
        item.detail = ""
        queue.save()
        try:
            sub(0, "открываю")
            info = media.probe(item.path)
            item.duration_min = info.duration / 60
            work = Path(cfg.output_dir) / Path(item.path).stem
            prj = pipeline.open_project(item.path, work, cfg)

            pipeline.prepare(prj, lambda p, m="": sub(p * 0.03, m), cancel)
            pipeline.fast_select(prj, lambda p, m="": sub(0.03 + p * 0.62, m), cancel)
            pipeline.suggest(prj, lambda p, m="": sub(0.65 + p * 0.05, m), cancel)

            chosen = prj.candidates[:per_file]
            if not chosen:
                item.status = STATUS_SKIP
                item.detail = "не нашлось моментов"
                queue.save()
                report.skipped.append(item.name)
                continue

            made = pipeline.build_all(prj, chosen,
                                     lambda p, m="": sub(0.7 + p * 0.3, m), cancel)
            item.clips = len(made)
            item.status = STATUS_DONE
            item.spent_min = (time.time() - started) / 60
            item.detail = f"роликов {len(made)} за {item.spent_min:.0f} мин"
            report.done.append(item.name)
            report.clips += len(made)
        except RuntimeError as e:
            if "отменено" in str(e):
                item.status = STATUS_WAIT
                queue.save()
                raise
            item.status = STATUS_FAIL
            item.detail = str(e)[:300]
            report.failed.append((item.name, str(e)))
        except Exception as e:                       # noqa: BLE001 - очередь не должна падать целиком
            item.status = STATUS_FAIL
            item.detail = f"{type(e).__name__}: {e}"[:300]
            report.failed.append((item.name, str(e)))
        finally:
            queue.save()

    progress(1.0, report.as_text())
    return report
