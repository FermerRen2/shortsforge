"""Модульные проверки без медиа: субтитры, мат, разбор ответа ИИ, настройки.

Запуск: python tests/test_units.py      (без pytest, обычные assert)
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shortsforge.core import analysis, captions as caps, deepseek, verify  # noqa: E402
from shortsforge.core.config import Settings  # noqa: E402
from shortsforge.core.transcribe import Word  # noqa: E402

passed = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global passed
    if not condition:
        raise AssertionError(f"{name}: {detail}")
    passed += 1
    print(f"  ok  {name}")


def words_from(pairs: list[tuple[float, float, str]]) -> list[Word]:
    return [Word(s, e, t) for s, e, t in pairs]


def test_captions() -> None:
    print("субтитры")
    ws = words_from([(0.0, 0.4, "это"), (0.4, 0.9, "просто"), (0.9, 1.3, "огонь"),
                     (2.0, 2.5, "смотри")])
    segs = caps.build_captions(ws, 0.0, 3.0)
    check("титры собраны", len(segs) >= 2, f"получили {len(segs)}")
    check("в титре не больше 3 слов", all(len(s.text.split()) <= 3 for s in segs))
    check("регистр верхний", segs[0].text.isupper(), segs[0].text)
    check("сегменты не пересекаются",
          all(segs[i].end <= segs[i + 1].start + 1e-6 for i in range(len(segs) - 1)))
    check("подсветка указывает на слово из титра",
          all(s.highlight in s.text.split() for s in segs))


def test_censor() -> None:
    print("мат")
    check("мат находится", caps.is_profane("блять"))
    check("нормальное слово не задевается", not caps.is_profane("сукно"))
    check("маскировка сохраняет первую букву", caps.mask_text("БЛЯТЬ")[0] == "Б")
    check("маскировка ставит звёздочки", "*" in caps.mask_text("блять"))
    ws = words_from([(0.0, 0.5, "блять"), (1.0, 1.5, "норм")])
    spans = caps.profane_spans(ws, 0.0, 2.0)
    check("промежуток мата найден", len(spans) == 1, str(spans))
    flt = caps.mute_filter(ws, 0.0, 2.0)
    check("фильтр глушения собран", flt is not None and "volume" in flt, str(flt))


def test_drop_popped() -> None:
    print("выкрики и титры")
    segs = caps.build_captions(words_from([(0.0, 0.5, "автоподстава")]), 0.0, 1.0)
    pops = [{"start": 0.0, "end": 0.6, "text": "АВТОПОДСТАВА"}]
    left = caps.drop_popped(segs, pops)
    check("повторяющийся титр убран", len(left) == 0, f"осталось {len(left)}")
    left2 = caps.drop_popped(segs, [{"start": 5.0, "end": 6.0, "text": "ДРУГОЕ"}])
    check("другие титры не страдают", len(left2) == len(segs))


def test_verify() -> None:
    print("сверка титров")
    with tempfile.TemporaryDirectory() as td:
        srt = Path(td) / "c.srt"
        srt.write_text(
            "1\n00:00:01,000 --> 00:00:02,000\nПРИВЕТ КАК ДЕЛА\n\n"
            "2\n00:00:04,000 --> 00:00:05,000\nСМОТРИ СЮДА\n\n"
            "3\n00:00:07,000 --> 00:00:08,000\nЭТО ОГОНЬ\n\n",
            encoding="utf-8")
        heard = [Word(1.05, 1.3, "привет"), Word(1.4, 1.8, "дела"),
                 Word(4.1, 4.4, "смотри"), Word(4.4, 4.9, "сюда"),
                 Word(7.1, 7.5, "это"), Word(7.5, 7.9, "огонь")]
        result = verify.captions_vs_audio(srt, heard)
        check("титры на месте", result["ok"] is True, str(result))
        # титры уехали на две секунды вперёд — проверка обязана это увидеть
        shifted = [Word(w.start + 2.0, w.end + 2.0, w.text) for w in heard]
        result2 = verify.captions_vs_audio(srt, shifted)
        check("сдвиг замечен", result2["ok"] is False, str(result2))


def test_deepseek_parse() -> None:
    print("разбор ответа ИИ")
    raw = '```json\n{"clips": [{"start": "1:02:03", "end": "1:02:30", ' \
          '"title": "Тест", "hashtags": "#shorts"}]}\n```'
    data = deepseek._extract_json(raw)
    check("JSON в обёртке разобран", "clips" in data)
    check("таймкод из трёх частей", deepseek._parse_ts("1:02:03") == 3723)
    check("таймкод из двух частей", deepseek._parse_ts("02:03") == 123)
    check("плохой таймкод не проходит", deepseek._parse_ts("скоро") is None)
    fixed = deepseek._extract_json('{"clips": [{"start": 1,}, ],}')
    check("висячие запятые терпим", "clips" in fixed)


def test_analysis() -> None:
    print("отбор моментов")
    speech = ("ха ха ха! это просто огонь, смотри сюда да ну ничего себе капец "
              "жесть как красиво ну и что дальше поехали братцы").split()
    ws = words_from([(float(i), float(i) + 0.4, w) for i, w in enumerate(speech)])
    cands = analysis.heuristic_candidates(ws, 3, min_len=3, max_len=12)
    check("кандидаты есть", len(cands) >= 1, f"нашли {len(cands)}")
    check("границы в порядке", all(c["end"] > c["start"] for c in cands))
    text = analysis.transcript_for_ai(ws)
    check("текст для ИИ с таймкодами", text.startswith("[0:00]"), text[:40])


def test_settings() -> None:
    print("настройки и ключ")
    cfg = Settings()
    cfg.api_key = "sk-test-1234567890"
    check("ключ замаскирован", cfg.masked_key().startswith("sk-tes"), cfg.masked_key())
    with tempfile.TemporaryDirectory() as td:
        cfg._path = str(Path(td) / "config.json")
        cfg.save()
        raw = Path(cfg._path).read_text(encoding="utf-8")
        check("ключ не сохранён открытым текстом", "sk-test-1234567890" not in raw)
        back = Settings.load(cfg._path)
        check("настройки читаются", back.ai_clips == cfg.ai_clips)
    cfg._api_key = ""


def main() -> int:
    for test in (test_captions, test_censor, test_drop_popped, test_verify,
                 test_deepseek_parse, test_analysis, test_settings):
        test()
    print(f"\nвсе проверки прошли: {passed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
