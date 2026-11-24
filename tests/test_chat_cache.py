"""Проверки чата стрима и кэша по файлу (без медиа)."""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shortsforge.core import cache as fc, chat

passed = 0


def check(name, cond, detail=""):
    global passed
    if not cond:
        raise AssertionError(f"{name}: {detail}")
    passed += 1
    print(f"  ok  {name}")


def test_text_chat() -> None:
    print("чат: простой текст")
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "rec.chat.txt"
        # будничный чат + один всплеск: 40 сообщений в минуту 5 против 1-2 в остальное время
        lines = []
        for i in range(20):
            lines.append(f"[00:{i:02d}:05] ник{i}: обычное сообщение")
        for i in range(40):
            lines.append(f"[00:05:{i:02d}] фанат{i}: ХАХАХА ЭТО ЧТО")
        for i in range(10):
            lines.append(f"[00:{i + 20:02d}:30] ник{i}: ещё одно")
        p.write_text("\n".join(lines), encoding="utf-8")
        msgs = chat.load_messages(p)
        check("строки разобраны", len(msgs) == 70, str(len(msgs)))
        check("время верное", msgs[0][0] == 5 and min(m[0] for m in msgs) == 5)
        found = chat.bursts(p, bucket=15)
        check("всплеск найден", len(found) >= 1, str([b.as_dict() for b in found]))
        check("всплеск там, где ржали", any(280 <= b.time <= 340 for b in found),
              str([round(b.time) for b in found]))


def test_json_chat() -> None:
    print("чат: json и jsonl")
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "a.chat.json"
        data = {"comments": [{"content_offset_seconds": 5, "message": {"body": "раз"}},
                             {"content_offset_seconds": 6, "message": {"body": "два"}}]}
        p.write_text(json.dumps(data), encoding="utf-8")
        check("twitchdownloader разобран", len(chat.load_messages(p)) == 2)

        p2 = Path(td) / "b.chat.jsonl"
        p2.write_text('{"time_in_seconds": 3, "message": "раз"}\n'
                      '{"time_in_seconds": 4, "message": "два"}\n', encoding="utf-8")
        check("jsonl разобран", len(chat.load_messages(p2)) == 2)


def test_find_chat() -> None:
    print("чат: автопоиск рядом с видео")
    with tempfile.TemporaryDirectory() as td:
        video = Path(td) / "stream.mp4"
        video.write_bytes(b"\x00" * 10)
        check("без лога — None", chat.find_chat_file(video) is None)
        (Path(td) / "stream.chat.json").write_text("{}", encoding="utf-8")
        check("лог найден", chat.find_chat_file(video) is not None)


def test_cache() -> None:
    print("кэш по файлу")
    with tempfile.TemporaryDirectory() as td:
        video = Path(td) / "v.mp4"
        video.write_bytes(b"\x00" * 128)
        c1 = fc.FileCache(video)
        key = c1.key
        check("ключ стабилен", fc.file_key(video) == key)
        video.write_bytes(b"\x01" * 256)
        check("ключ меняется при изменении файла", fc.file_key(video) != key)

        c1.put_loudness([-20.0, -19.5, -21.0])
        check("громкость читается", c1.get_loudness() == [-20.0, -19.5, -21.0])

        from shortsforge.core.transcribe import Word
        c1.put_words([Word(1.0, 2.0, "привет")], "fast")
        back = c1.get_words("fast")
        check("слова читаются", back and back[0][2] == "привет")
        check("описание кэша", "расшифровка" in c1.describe(), c1.describe())


def main() -> int:
    for t in (test_text_chat, test_json_chat, test_find_chat, test_cache):
        t()
    print(f"\nвсе проверки чата и кэша прошли: {passed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
