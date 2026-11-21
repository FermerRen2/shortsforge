"""Поиск интересных мест: окна по громкости, запасной отбор без ИИ, склейка текста для ИИ.

Проверенные правила:
- громкий пик — это часто выстрел или взрыв, а не речь, поэтому окно вокруг пика только
  подсказка, а не готовый ролик;
- ролик привязывается к СЛОВУ-крючку, а не к пику громкости;
- отбор без ИИ (когда нет ключа) идёт по смеху, восклицаниям и плотности речи.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np

LAUGH = re.compile(r"(ха-?ха|ахах|хех|хахах|хихи)", re.I)
EXCITE = re.compile(r"(!|\?|да ну|ничего себе|офигеть|капец|жесть|смотри|глянь)", re.I)
FILLER = re.compile(r"^(э|эм|ну|вот|типа|короче|значит|как бы)$", re.I)


@dataclass
class Window:
    """Место, куда стоит посмотреть: центр по громкости и всё, что рядом сказано."""
    start: float
    end: float
    loudness: float
    text: str

    @property
    def center(self) -> float:
        return (self.start + self.end) / 2


def loud_peaks(levels: list[float], min_gap: float = 75.0,
               top: int = 60) -> list[tuple[float, float]]:
    """Пики громкости: (дБ, секунда). Сглаживаем по 3 секунды, чтобы не ловить щелчки."""
    if not levels:
        return []
    arr = np.asarray(levels, dtype=np.float32)
    median = float(np.median(arr))
    smooth = np.convolve(arr, np.ones(3) / 3.0, mode="same")
    threshold = median + 9.0
    peaks: list[tuple[float, float]] = []
    last = -1e9
    for i in range(2, len(smooth) - 2):
        if smooth[i] >= threshold and smooth[i] == smooth[i - 2:i + 3].max() and i - last >= min_gap:
            peaks.append((float(smooth[i]), float(i)))
            last = i
    peaks.sort(reverse=True)
    return peaks[:top]


def make_windows(levels: list[float], words: list, half: float = 30.0,
                 min_gap: float = 75.0, top: int = 60) -> list[Window]:
    """Окна вокруг громких мест с текстом внутри — по ним работает отбор."""
    windows: list[Window] = []
    used: list[float] = []
    for loud, at in loud_peaks(levels, min_gap=min_gap, top=top):
        if any(abs(at - u) < min_gap for u in used):
            continue
        used.append(at)
        s, e = max(0.0, at - half), at + half
        text = " ".join(w.text for w in words if s <= w.start < e)
        windows.append(Window(start=s, end=e, loudness=loud, text=text.strip()))
    windows.sort(key=lambda w: w.start)
    return windows


# --- отбор без ИИ ------------------------------------------------------------
def _score_text(text: str, word_count: int) -> float:
    score = 0.0
    score += len(LAUGH.findall(text)) * 3.0
    score += min(len(EXCITE.findall(text)), 6) * 1.5
    score += min(word_count, 60) / 10.0
    return score


def heuristic_candidates(words: list, count: int = 12, min_len: float = 20.0,
                         max_len: float = 38.0, gap: float = 0.6) -> list[dict]:
    """Запасной отбор: без ИИ, по эмоциям в тексте и плотности речи."""
    if not words:
        return []
    phrases: list[list] = []
    current: list = []
    for w in words:
        if current and w.start - current[-1].end > gap:
            phrases.append(current)
            current = []
        current.append(w)
    if current:
        phrases.append(current)

    scored = []
    for i, ph in enumerate(phrases):
        text = " ".join(w.text for w in ph)
        scored.append((_score_text(text, len(ph)), i))
    scored.sort(reverse=True)

    picked: list[dict] = []
    for score, idx in scored:
        anchor = phrases[idx][0].start
        if any(abs(anchor - p["start"]) < 60 for p in picked):
            continue
        start = max(0.0, anchor - 4.0)
        end = min(start + max_len, phrases[idx][-1].end + 6.0)
        if end - start < min_len:
            end = start + min_len
        inside = [w for w in words if start <= w.start < end]
        if len(inside) < 8:
            continue
        text = " ".join(w.text for w in inside)
        picked.append({
            "start": round(start, 1), "end": round(end, 1),
            "title": _title_from(phrases[idx]),
            "text": text[:400],
            "reason": "без ИИ: эмоции и плотность речи",
            "score": round(score, 1),
        })
        if len(picked) >= count:
            break
    picked.sort(key=lambda c: c["start"])
    return picked


def _title_from(phrase: list) -> str:
    text = " ".join(w.text for w in phrase).strip(" .,-—")
    words = [w for w in text.split() if not FILLER.match(w.strip(",.!?"))]
    title = " ".join(words) if words else text
    if len(title) > 70:
        title = title[:67].rsplit(" ", 1)[0] + "…"
    return (title[:1].upper() + title[1:]) if title else "Момент со стрима"


# --- подготовка текста для ИИ ------------------------------------------------
def transcript_for_ai(words: list, max_chars: int = 14_000) -> str:
    """Компактная расшифровка с таймкодами: ИИ ищет по ней крючки и возвращает отрезки."""
    if not words:
        return ""
    lines: list[str] = []
    buf: list[str] = []
    buf_start = words[0].start
    last_end = words[0].end
    for w in words:
        if w.start - last_end > 1.2 and buf:
            lines.append(f"[{_ts(buf_start)}] {' '.join(buf)}")
            buf, buf_start = [], w.start
        buf.append(w.text)
        last_end = w.end
        if len(buf) > 26:
            lines.append(f"[{_ts(buf_start)}] {' '.join(buf)}")
            buf, buf_start = [], w.end
    if buf:
        lines.append(f"[{_ts(buf_start)}] {' '.join(buf)}")

    text = "\n".join(lines)
    if len(text) <= max_chars:
        return text
    # длинную расшифровку режем равномерно по времени, а не по началу
    step = max(1, len(lines) * max_chars // len(text) // len(lines) + 1)
    keep = lines[::step]
    return "\n".join(keep)[:max_chars]


def _ts(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:d}:{s:02d}"
