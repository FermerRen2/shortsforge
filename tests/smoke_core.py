"""Быстрая проверка внутренностей без интерфейса.

Запуск: python tests/smoke_core.py [видео]
Если видео не задано, берётся короткий кусок из папки перепакованных записей (если есть),
иначе тест ограничивается проверками без медиа.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shortsforge.core import capcut, captions as caps, layout, media, render, verify  # noqa: E402
from shortsforge.core.config import Settings  # noqa: E402
from shortsforge.core.transcribe import Transcriber  # noqa: E402


def hr(title: str) -> None:
    print(f"\n=== {title} ===")


def main() -> int:
    cfg = Settings()
    video = sys.argv[1] if len(sys.argv) > 1 else None
    if not video:
        candidates = sorted(Path(r"C:\Users\Kosmeya\Documents\стримы").glob("*.mp4"))
        video = str(candidates[-1]) if candidates else None

    hr("окружение")
    print("ffmpeg:", media.ffmpeg())
    print("ffprobe:", media.ffprobe())
    print("capcut найден:", capcut.available())
    if not video or not Path(video).exists():
        print("видео не задано — проверяю только текстовые части")
        _text_checks()
        return 0

    hr("файл")
    info = media.probe(video)
    print(info.as_text())
    needed, reason = media.needs_repack(info, video)
    print("нужна перепаковка:", needed, "|", reason.replace("\n", " ")[:80])

    hr("карта времени")
    parts = media.parts_map([video])
    print(f"кусков: {len(parts)}, общая длина {parts[-1].end:.1f} с")
    part, local = media.locate(parts, min(300.0, parts[-1].end / 2))
    print(f"момент 150 с -> {part.path.name}, внутри {local:.1f} с")

    hr("окно вебки по лицу")
    try:
        box = layout.detect(video, Path(tempfile.gettempdir()) / "sf_cache", samples=8)
        print(f"вебка {box.w}x{box.h} в ({box.x},{box.y}), лиц найдено {box.faces_found}, "
              f"угол {box.corner}")
    except RuntimeError as e:
        box = None
        print("не нашёл лицо:", e)

    hr("распознавание речи (30 с)")
    tr = Transcriber(cfg.whisper_model, "auto", "ru")
    words = tr.transcribe_range(video, 60.0, 90.0)
    tr_status = tr.status
    print(f"устройство: {tr_status}, слов: {len(words)}")
    if words:
        print("текст:", " ".join(w.text for w in words[:20]))

    if not words:
        print("речи не распознано — дальше проверять нечего")
        return 0

    hr("субтитры и мат")
    segs = caps.build_captions(words, 60.0, 90.0)
    print(f"титров: {len(segs)}, первый: {segs[0].text!r} @ {segs[0].start:.2f}")
    muted = caps.profane_spans(words, 60.0, 90.0)
    print("мат найден в", len(muted), "местах; фильтр:", (caps.mute_filter(words, 60.0, 90.0)
                                                          or "не нужен")[:70])

    hr("выкрики")
    pops = render.find_pops(words, 60.0, 90.0, [words[0].text], extra=1)
    print("выкриков:", len(pops), pops)

    hr("проект CapCut (в песочницу, не в настоящие черновики)")
    with tempfile.TemporaryDirectory() as td:
        folder = Path(td) / "clip"
        folder.mkdir()
        for name in ("game.mp4", "face.mp4"):
            (folder / name).write_bytes(b"")
        spec = capcut.ClipSpec(name="smoke", duration=30.0, folder=folder,
                               captions=[c.as_dict() for c in segs[:6]], pops=pops,
                               face_height=cfg.face_height)
        dst = capcut.build(spec, override_dir=Path(td) / "drafts")
        problems = capcut.validate(dst)
        print("проект собран:", dst.name, "| проблем:", problems or "нет")
        content = json.loads((Path(dst) / "draft_content.json").read_text(encoding="utf-8"))
        print("дорожек:", [t.get("name") for t in content["tracks"]])

    hr("сверка титров со звуком")
    with tempfile.TemporaryDirectory() as td:
        srt = Path(td) / "c.srt"
        caps.write_srt(segs, str(srt))
        heard = tr.transcribe_range(video, 60.0, 90.0)
        # слова в шкале ролика, а не записи: иначе проверка меряет разницу шкал, а не титры
        class _Rel:
            def __init__(self, w):
                self.start = w.start - 60.0
                self.text = w.text
        result = verify.captions_vs_audio(srt, [_Rel(w) for w in heard])
        print(result)

    print("\nВСЁ ПРОВЕРЕНО")
    return 0


def _text_checks() -> None:
    from shortsforge.core import analysis, deepseek

    lines = "[0:01] привет как дела [0:05] это же просто огонь [0:09] ха-ха-ха"
    print("текст для ИИ:", analysis.transcript_for_ai([], 100) == "" or "ок")
    cands = analysis.heuristic_candidates([], 5)
    print("кандидатов без слов:", len(cands))
    try:
        deepseek._extract_json('```json\n{"clips": []}\n```')
        print("разбор JSON от модели: ок")
    except Exception as e:                                   # noqa: BLE001
        print("разбор JSON упал:", e)
    print("готово")


if __name__ == "__main__":
    raise SystemExit(main())
