"""Чат стрима как подсказка: где зрители реально реагировали.

Громкость обманывает — выстрел в игре громче шутки. Всплеск сообщений в чате честнее: люди
пишут, когда смешно или неожиданно. Здесь читаются локальные логи чата (онлайн-загрузка не
нужна), считаются всплески и отдаются как дополнительные места для нарезки.

Поддерживаются форматы:
- TwitchDownloader: `{"comments": [{"content_offset_seconds": 12.3, "message": {"body": "..."}}]}`
- yt-dlp `--write-chat`: построчный JSON с `time_in_seconds`
- простой текст: `[00:12:33] ник: сообщение` или `00:12:33 ник: сообщение`
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

CHAT_SUFFIXES = (".chat.json", ".chat.jsonl", ".chat.txt", ".live_chat.json",
                 "_chat.json", "_chat.txt", ".jsonl")
TEXT_LINE = re.compile(r"^\[?(?:(\d{1,2}):)?(\d{1,2}):(\d{2})\]?\s*(?:[<\[]?([^:>\]]{1,40})[>\]]?:\s*)?(.*)$")


@dataclass
class ChatBurst:
    time: float
    messages: int
    sample: str

    def as_dict(self) -> dict:
        return {"time": round(self.time, 1), "messages": self.messages, "sample": self.sample}


def find_chat_file(video: str | Path) -> Path | None:
    """Ищет лог чата рядом с записью: те же имя + расширения чата."""
    video = Path(video)
    folder = video.parent
    stem = video.stem
    for suffix in CHAT_SUFFIXES:
        for name in (stem + suffix, stem + ".chat" + suffix):
            cand = folder / name
            if cand.exists():
                return cand
    # иногда лог лежит рядом без привязки к имени
    for cand in folder.glob("*.chat.json*"):
        return cand
    return None


def _from_twitchdownloader(data: dict) -> list[tuple[float, str]]:
    out = []
    for item in data.get("comments") or []:
        t = item.get("content_offset_seconds")
        body = ((item.get("message") or {}).get("body") or "").strip()
        if t is None:
            continue
        out.append((float(t), body))
    return out


def _from_json_lines(path: Path) -> list[tuple[float, str]]:
    out = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip().rstrip(",")
            if not line or line in ("[", "]"):
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = (item.get("time_in_seconds") or item.get("content_offset_seconds")
                 or item.get("t") or item.get("time"))
            body = item.get("message") or item.get("body") or ""
            if isinstance(body, dict):
                body = body.get("body", "")
            if t is None:
                continue
            try:
                out.append((float(t), str(body)))
            except (TypeError, ValueError):
                continue
    return out


def _from_text(path: Path) -> list[tuple[float, str]]:
    out = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = TEXT_LINE.match(line.strip())
            if not m:
                continue
            hours = int(m.group(1) or 0)
            minutes = int(m.group(2))
            seconds = int(m.group(3))
            out.append((hours * 3600 + minutes * 60 + seconds, m.group(5) or ""))
    return out


def load_messages(path: str | Path) -> list[tuple[float, str]]:
    """Читает лог чата в список (секунды от начала записи, текст сообщения)."""
    path = Path(path)
    raw = path.read_text(encoding="utf-8", errors="replace")[:2000].lstrip()
    if raw.startswith("{"):
        try:
            data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            if isinstance(data, dict) and "comments" in data:
                return _from_twitchdownloader(data)
        except (json.JSONDecodeError, OSError):
            pass
        return _from_json_lines(path)
    return _from_text(path)


def bursts(path: str | Path, bucket: float = 15.0, top: int = 40) -> list[ChatBurst]:
    """Всплески активности чата: где писали чаще обычного."""
    messages = load_messages(path)
    if not messages:
        return []
    duration = max(t for t, _ in messages) + bucket
    buckets = max(1, int(duration // bucket) + 1)
    counts = [0] * buckets
    samples: list[str] = [""] * buckets
    for t, body in messages:
        i = min(buckets - 1, max(0, int(t // bucket)))
        counts[i] += 1
        if body and len(samples[i]) < 120:
            samples[i] = (samples[i] + " " + body).strip()

    ordered = sorted(counts)
    median = ordered[len(ordered) // 2]
    peak = max(counts)
    # Порог: обычно это «втрое больше обычного». Но на коротком или редком чате
    # такой порог не срабатывает никогда — тогда берём просто самые живые отрезки,
    # иначе подсказка по чату молча отключается (проверено на тесте 25.11.2026).
    threshold = max(median * 2.5, median + 4, 2)
    if peak < threshold:
        threshold = max(2, peak)
    found = []
    for i, c in enumerate(counts):
        if c < threshold:
            continue
        neighbours = counts[max(0, i - 1):i + 2]
        if c < max(neighbours):
            continue
        found.append(ChatBurst(time=i * bucket + bucket / 2, messages=c,
                               sample=samples[i][:120]))
    found.sort(key=lambda b: b.messages, reverse=True)
    found = found[:top]
    found.sort(key=lambda b: b.time)
    return found


def summary(path: str | Path) -> str:
    """Короткая строка для интерфейса: сколько сообщений и сколько всплесков."""
    messages = load_messages(path)
    if not messages:
        return "чат пуст или формат не распознан"
    found = bursts(path)
    duration = max(t for t, _ in messages) / 60
    return f"сообщений {len(messages)}, всплесков {len(found)}, охват {duration:.0f} мин"
