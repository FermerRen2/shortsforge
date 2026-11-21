"""Самопроверка ролика: титры против того, что реально слышно.

Проверка «похожесть громкости» и «сравнение по словам общей расшифровки» на практике врут:
в игре повторяется музыка, а распознавание на одном и том же месте пишет разные слова. Поэтому
здесь титры сверяются с распознаванием САМОГО ролика: ищем сдвиг, при котором совпадает больше
всего слов. Сдвиг до полусекунды — норма (это шум распознавания), больше секунды — титры уехали.
"""
from __future__ import annotations

import re
from pathlib import Path


def _norm(s: str) -> str:
    return re.sub(r"[^\wа-яё]", "", (s or "").lower())


def read_srt(path: str | Path) -> list[tuple[float, float, str]]:
    """Читает SRT: (начало, конец, текст)."""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    out: list[tuple[float, float, str]] = []
    time_re = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)")
    blocks = re.split(r"\n\s*\n", text)
    for block in blocks:
        lines = [ln for ln in block.strip().splitlines() if ln.strip()]
        if len(lines) < 2:
            continue
        m = time_re.search(lines[0] if time_re.search(lines[0]) else lines[1])
        if not m:
            continue
        g = [int(x) for x in m.groups()]
        start = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
        end = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
        body = lines[-1].strip()
        out.append((start, end, body))
    return out


def captions_vs_audio(srt_path: str | Path, words: list, tolerance: float = 0.6) -> dict:
    """Сверяет титры из SRT с распознанными словами ролика."""
    segs = read_srt(srt_path)
    if not segs:
        return {"name": "титры против звука", "ok": None, "detail": "титров нет"}
    heard = [(float(w.start), _norm(w.text if hasattr(w, "text") else w[2])) for w in words]
    heard = [(t, w) for t, w in heard if len(w) > 1]
    if not heard:
        return {"name": "титры против звука", "ok": None, "detail": "речь в ролике не распознана"}

    phrases = [(s, e, [_norm(x) for x in txt.split() if len(_norm(x)) > 1]) for s, e, txt in segs]
    phrases = [p for p in phrases if p[2]]
    if not phrases:
        return {"name": "титры против звука", "ok": None, "detail": "в титрах нет слов"}

    # слова внутри титра получают время по линейке: (начало + доля длительности).
    # Так проверка цепляется за конкретные слова, а не за «где-то в этом титре» — иначе
    # при плотных титрах сдвиг в секунду выглядит как «всё на месте».
    points: list[tuple[float, str]] = []
    for start, end, words_in in phrases:
        span = max(0.05, end - start)
        for i, w in enumerate(words_in):
            points.append((start + span * i / len(words_in), w))
    if not points:
        return {"name": "титры против звука", "ok": None, "detail": "в титрах нет слов"}

    def score(shift: float) -> int:
        hit = 0
        for t, w in heard:
            target = t - shift
            for pt, pw in points:
                if abs(pt - target) <= 0.35 and (pw.startswith(w[:4]) or w.startswith(pw[:4])):
                    hit += 1
                    break
        return hit

    # при равном счёте выбираем сдвиг ближе к нулю
    best_score, best_shift = -1, 0.0
    shift = -3.0
    while shift <= 3.0001:
        s = score(shift)
        if s > best_score or (s == best_score and abs(shift) < abs(best_shift)):
            best_score, best_shift = s, shift
        shift += 0.25

    share = best_score / max(1, len(heard))
    ok = abs(best_shift) <= 1.0 and share >= 0.3
    return {
        "name": "титры против звука",
        "ok": ok,
        "detail": f"сдвиг {best_shift:+.2f} с, совпало слов {share:.0%}",
    }
