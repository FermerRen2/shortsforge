"""Сквозная проверка конвейера на реальном видео (без интерфейса).

Запуск: python tests/e2e_pipeline.py [видео] [сколько_роликов]
Берёт короткую запись, проходит все шаги и печатает отчёт. Папка для роликов — временная.
Проекты CapCut собираются в настоящие черновики (иначе не проверить), после теста удаляются.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shortsforge.core import capcut, pipeline  # noqa: E402
from shortsforge.core.config import Settings  # noqa: E402


def main() -> int:
    video = sys.argv[1] if len(sys.argv) > 1 else None
    if not video:
        parts = sorted(Path(r"C:\Users\Kosmeya\Documents\стримы").glob("*.mp4"))
        if not parts:
            print("нет короткого видео для теста — укажите путь аргументом")
            return 2
        video = str(parts[-1])
    want = int(sys.argv[2]) if len(sys.argv) > 2 else 3

    cfg = Settings()
    cfg.output_dir = tempfile.mkdtemp(prefix="sf_e2e_")
    cfg.ai_clips = want
    cfg.make_capcut = True
    cfg.make_preview = True
    print(f"видео: {video}\nпапка: {cfg.output_dir}")

    def progress(value, text=""):
        if text:
            print(f"  [{value:.0%}] {text}" if value is not None else f"  {text}", flush=True)

    prj = pipeline.open_project(video, Path(cfg.output_dir) / "work", cfg)
    print("шаг 1: подготовка")
    pipeline.prepare(prj, progress)

    print("шаг 2: расшифровка")
    pipeline.transcribe(prj, progress)
    if not prj.words:
        print("речи не найдено — тест прерван")
        return 1

    print("шаг 3: отбор моментов (без ключа — эвристика)")
    pipeline.suggest(prj, progress)
    for c in prj.candidates[:want]:
        print(f"   · {c['start']:.0f}–{c['end']:.0f} с: {c['title'][:60]}")

    chosen = prj.candidates[:want]
    print(f"шаг 4: сборка {len(chosen)} роликов")
    clips = pipeline.build_all(prj, chosen, progress)

    print("\n--- отчёт ---")
    ok = True
    for clip in clips:
        checks = clip.get("checks") or []
        bad = [c for c in checks if c.get("ok") is False]
        ok = ok and not bad
        print(f"{clip['name']}: {clip['duration']:.0f} с, титров {clip['captions']}, "
              f"выкриков {clip['pops']}, проект {'есть' if clip['capcut'] else 'нет'}")
        for c in checks:
            mark = "ok" if c.get("ok") else ("!!" if c.get("ok") is False else "--")
            print(f"    [{mark}] {c.get('name')}: {c.get('detail')}")
        preview = Path(clip["preview"]) if clip["preview"] else None
        print(f"    предпросмотр: {preview.name if preview else '—'} "
              f"({preview.stat().st_size // 1024} КБ)" if preview and preview.exists() else "")

    # чистим за собой черновики CapCut
    for clip in clips:
        if clip.get("capcut"):
            shutil.rmtree(clip["capcut"], ignore_errors=True)
            root = capcut.drafts_root() / "root_meta_info.json"
            if root.exists():
                reg = json.loads(root.read_text(encoding="utf-8"))
                reg["all_draft_store"] = [d for d in reg["all_draft_store"]
                                          if d.get("draft_name") != clip["name"]]
                reg["draft_ids"] = len(reg["all_draft_store"])
                root.write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")

    print("\nИТОГ:", "всё чисто" if ok else "есть замечания в проверках")
    print("папка с роликами осталась:", cfg.output_dir)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
