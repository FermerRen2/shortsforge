"""Встроенная самопроверка: то же, что гоняют тесты, но доступно из собранного .exe.

Запуск: `shortsforge.exe --selftest` (или `python -m shortsforge --selftest`).
Проверяет окружение и ключевые функции без медиа, пишет отчёт в лог и возвращает код 0/1.
Смысл: убедиться, что внутри .exe всё на месте — ffmpeg, шаблон CapCut, шрифты, иконки,
разбор ответов ИИ, субтитры, хранилище ключа.
"""
from __future__ import annotations

import io
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path


def _checks() -> list[tuple[str, bool, str]]:
    from . import captions as caps, deepseek, resources
    from .config import Settings

    results: list[tuple[str, bool, str]] = []

    def add(name: str, fn) -> None:
        try:
            detail = fn() or ""
            results.append((name, True, str(detail)))
        except Exception as e:                       # noqa: BLE001 - отчёт важнее исключения
            results.append((name, False, f"{type(e).__name__}: {e}"))

    def ffmpeg() -> str:
        from . import media

        path = media.ffmpeg()
        version = media.run([path, "-version"], check=False).stdout.splitlines()[0][:40]
        return f"{Path(path).name} · {version}"

    def ffprobe() -> str:
        from . import media

        return Path(media.ffprobe()).name

    def capcut_template() -> str:
        from . import capcut

        path = capcut.template_path()
        size = path.stat().st_size
        return f"{path.name}, {size} байт"

    def capcut_drafts() -> str:
        from . import capcut

        return "найдены" if capcut.available() else "не найдены (экспорт пропустится)"

    def whisper() -> str:
        import faster_whisper

        return f"faster-whisper {faster_whisper.__version__}"

    def cuda() -> str:
        from .transcribe import add_cuda_dlls

        added = add_cuda_dlls()
        return f"подключено DLL: {len(added)}"

    def fonts() -> str:
        for name in ("Inter-Regular.ttf", "Inter-SemiBold.ttf"):
            if not resources.asset(f"fonts/{name}").exists():
                raise FileNotFoundError(name)
        return "Inter на месте"

    def icons() -> str:
        need = ["app-icon.svg", "icon-project.svg", "icon-settings.svg"]
        missing = [n for n in need if not resources.asset(n).exists()]
        if missing:
            raise FileNotFoundError(", ".join(missing))
        return f"{len(need)} иконки"

    def captions_check() -> str:
        from .transcribe import Word

        words = [Word(0.0, 0.4, "это"), Word(0.4, 0.9, "просто"), Word(0.9, 1.3, "огонь")]
        segs = caps.build_captions(words, 0.0, 2.0)
        if not segs:
            raise AssertionError("титры не собрались")
        if any(len(s.text.split()) > 3 for s in segs):
            raise AssertionError("в титре больше трёх слов")
        return f"{len(segs)} титра"

    def censor_check() -> str:
        if not caps.is_profane("блять") or caps.is_profane("сукно"):
            raise AssertionError("определение мата сбоит")
        return caps.mask_text("блять")

    def ai_parse() -> str:
        raw = '```json\n{"clips": [{"start": "1:02:03", "end": "1:02:30", "title": "x"}]}\n```'
        data = deepseek._extract_json(raw)
        if not data.get("clips"):
            raise AssertionError("ответ не разобран")
        return f"таймкод {deepseek._parse_ts('1:02:03'):.0f} с"

    def settings_roundtrip() -> str:
        cfg = Settings()
        value = cfg.ai_clips
        if value < 1:
            raise AssertionError("настройки не прочитались")
        return f"моментов по умолчанию: {value}"

    def writable() -> str:
        target = resources.writable_dir() / "selftest_write.txt"
        target.write_text("ok", encoding="utf-8")
        target.unlink(missing_ok=True)
        return str(target.parent)

    def chat_parse() -> str:
        from . import chat

        import tempfile

        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "c.chat.txt"
            f.write_text("[00:00:05] ник: привет\n[00:00:06] ник2: хаха", encoding="utf-8")
            msgs = chat.load_messages(f)
            if len(msgs) != 2:
                raise AssertionError("лог чата не разобран")
            return f"строк {len(msgs)}"

    def cache_key() -> str:
        from . import cache

        import tempfile

        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "v.mp4"
            f.write_bytes(b"0" * 64)
            key = cache.file_key(f)
            if len(key) < 8:
                raise AssertionError("ключ кэша не посчитан")
            return f"ключ {key[:8]}…"

    for name, fn in (
        ("ffmpeg", ffmpeg), ("ffprobe", ffprobe),
        ("чат стрима", chat_parse), ("кэш по файлу", cache_key),
        ("шаблон CapCut", capcut_template), ("черновики CapCut", capcut_drafts),
        ("faster-whisper", whisper), ("CUDA-библиотеки", cuda),
        ("шрифты", fonts), ("иконки", icons),
        ("субтитры", captions_check), ("мат", censor_check),
        ("разбор ответа ИИ", ai_parse), ("настройки", settings_roundtrip),
        ("запись в папку данных", writable),
    ):
        add(name, fn)
    return results


def run(log_path: Path | None = None) -> int:
    from . import resources

    started = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    buffer = io.StringIO()

    def out(line: str) -> None:
        buffer.write(line + "\n")
        try:
            print(line, flush=True)
        except Exception:                            # noqa: BLE001 - в windowed exe stdout нет
            pass

    out(f"ShortsForge · самопроверка {started}")
    out(f"запуск: {'собранный .exe' if resources.is_frozen() else 'из исходников'}")
    out(f"данные: {resources.base_dir()}")
    out(f"python: {sys.version.split()[0]}")
    out("")
    failures = 0
    try:
        results = _checks()
    except Exception:                                # noqa: BLE001
        out(traceback.format_exc())
        results = []
        failures = 1
    for name, ok, detail in results:
        out(f"[{'OK ' if ok else 'ОШИБКА'}] {name}: {detail}")
        if not ok:
            failures += 1
    out("")
    out(f"ИТОГ: {len(results) - failures} из {len(results)} проверок пройдено"
        if results else "ИТОГ: проверки не запустились")

    target = log_path or (resources.writable_dir() / "selftest.log")
    try:
        target.write_text(buffer.getvalue(), encoding="utf-8")
        print(f"лог: {target}")
    except OSError:
        pass
    return 0 if failures == 0 else 1
