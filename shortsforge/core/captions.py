"""Субтитры и мат: короткие фразы по 1–3 слова с подсветкой текущего слова.

Правила взяты из разбора референсов: не больше трёх слов и полутора секунд в кадре, пауза
дольше половины секунды — новый кадр. Подсветка двигается по слову, поэтому на каждое слово
внутри фразы делается свой сегмент с тем же текстом.

Мат убирается в двух местах: в титрах слово превращается в первую букву со звёздочками,
в звуке этот промежуток глушится (см. `mute_filter`).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

MAX_WORDS = 3
MAX_CHARS = 16
MAX_DUR = 1.5
GAP_SPLIT = 0.5
MIN_SUB = 0.18
GAP_FILL = 0.35

# корни, а не целые слова: мат склоняется как угодно
ROOTS = [
    r"бля\w*", r"бляд\w*",
    r"ху[йяеёи]\w*", r"хуйн\w*",
    r"пизд\w*", r"пизж\w*",
    r"захуя\w*", r"нахуя?\w*", r"нихуя\w*", r"похуй\w*", r"охуе\w*", r"ахуе\w*",
    r"еба\w*", r"ебё\w*", r"ебет\w*", r"ебал\w*", r"ебан\w*", r"ебн\w*", r"ебуч\w*",
    r"ёба\w*", r"ёбн\w*", r"заеб\w*", r"наеб\w*", r"въеб\w*", r"уеб\w*", r"отъеб\w*",
    r"съеб\w*", r"выеб\w*", r"перееб\w*", r"долбоеб\w*",
    r"сука\w*", r"сучк\w*", r"мудак\w*", r"мудил\w*",
    r"пидор\w*", r"пидар\w*", r"педик\w*", r"гандон\w*", r"гондон\w*",
    r"залуп\w*", r"дроч\w*", r"шлюх\w*", r"блядин\w*",
    r"говн\w*", r"срать\w*", r"срал\w*", r"обоср\w*", r"жоп\w*",
]
PATTERN = re.compile(r"\b(" + "|".join(ROOTS) + r")", re.IGNORECASE)
WHITELIST = re.compile(r"^(сукно|сукн|хутор|ебер|еберт|пизdec)", re.IGNORECASE)


def is_profane(text: str) -> bool:
    clean = re.sub(r"[^\wа-яё]", "", (text or "").lower())
    if not clean or WHITELIST.match(clean):
        return False
    return bool(PATTERN.search(clean))


def mask_text(text: str) -> str:
    """Оставляет первую букву и пунктуацию: БЛЯТЬ -> Б****."""
    return PATTERN.sub(lambda m: m.group(1)[0] + "*" * (len(m.group(1)) - 1), text or "")


# --- сегменты субтитров ------------------------------------------------------
@dataclass
class Caption:
    start: float
    end: float
    text: str
    highlight: str

    def as_dict(self) -> dict:
        return {"start": round(self.start, 2), "end": round(self.end, 2),
                "text": self.text, "highlight": self.highlight}


def _clean(word: str) -> str:
    return mask_text(word.strip().upper())


def build_captions(words: list, clip_start: float, clip_end: float) -> list[Caption]:
    """Сегменты субтитров в времени ролика (не записи)."""
    inside = [w for w in words if w.end > clip_start and w.start < clip_end]
    inside = [(max(w.start, clip_start), min(w.end, clip_end), w.text) for w in inside]
    if not inside:
        return []

    groups: list[list] = []
    current: list = []
    for start, end, text in inside:
        word = _clean(text)
        if not word:
            continue
        if current:
            gap = start - current[-1][1]
            too_long = (end - current[0][0]) > MAX_DUR
            too_wide = sum(len(c[2]) + 1 for c in current) + len(word) > MAX_CHARS
            if gap > GAP_SPLIT or len(current) >= MAX_WORDS or too_long or too_wide:
                groups.append(current)
                current = []
        current.append((start, end, word))
    if current:
        groups.append(current)

    segs: list[Caption] = []
    for group in groups:
        text = " ".join(g[2] for g in group)
        for i, (start, end, word) in enumerate(group):
            seg_start = start - clip_start
            seg_end = (group[i + 1][0] if i + 1 < len(group) else end) - clip_start
            if seg_end - seg_start < MIN_SUB:
                seg_end = seg_start + MIN_SUB
            segs.append(Caption(max(0.0, seg_start), seg_end, text, word))

    # короткие паузы дотягиваем предыдущим титром — иначе текст мигает
    for i in range(len(segs) - 1):
        gap = segs[i + 1].start - segs[i].end
        if 0 < gap < GAP_FILL:
            segs[i].end = segs[i + 1].start
    # наложение недопустимо: два титра одновременно печатаются друг на друге
    for i in range(len(segs) - 1):
        if segs[i].end > segs[i + 1].start:
            segs[i].end = segs[i + 1].start
    return [s for s in segs if s.end - s.start >= 0.05]


def drop_popped(captions: list[Caption], pops: list[dict]) -> list[Caption]:
    """Титр, который целиком повторяет выкрик, убираем — иначе слово видно дважды."""
    if not pops:
        return captions

    def norm(s: str) -> str:
        return re.sub(r"[^\wа-яё]", "", s.lower())

    pop_words = {norm(p["text"]) for p in pops}
    out = []
    for c in captions:
        words = {norm(w) for w in c.text.split()}
        if words and words <= pop_words:
            continue
        out.append(c)
    return out


# --- звук --------------------------------------------------------------------
def profane_spans(words: list, clip_start: float, clip_end: float) -> list[tuple[float, float]]:
    spans = []
    for w in words:
        if w.end <= clip_start or w.start >= clip_end:
            continue
        if is_profane(w.text):
            spans.append((round(max(w.start, clip_start) - clip_start, 2),
                          round(min(w.end, clip_end) - clip_start, 2)))
    return spans


def mute_filter(words: list, clip_start: float, clip_end: float, pad: float = 0.03) -> str | None:
    """Фильтр ffmpeg, глушащий матерные слова в звуке ролика."""
    spans = [(max(0.0, a - pad), b + pad) for a, b in profane_spans(words, clip_start, clip_end)]
    spans = [(a, b) for a, b in spans if b > a]
    if not spans:
        return None
    spans.sort()
    merged = [list(spans[0])]
    for a, b in spans[1:]:
        if a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    expr = "+".join(f"between(t\\,{a:.2f}\\,{b:.2f})" for a, b in merged)
    return f"volume=enable='{expr}':volume=0"


# --- файлы субтитров ---------------------------------------------------------
ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{font},{size},{color},{mask},&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,6,0,2,70,70,360,1
Style: Pop,{font},{pop_size},{hl},{mask},&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,10,0,5,40,40,40,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _ass_color(hex_color: str) -> str:
    """#RRGGBB -> &H00BBGGRR."""
    h = hex_color.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H00{b}{g}{r}".upper()


def _ass_time(t: float) -> str:
    h = int(t // 3600)
    m = int(t % 3600 // 60)
    return f"{h}:{m:02d}:{t % 60:05.2f}"


def write_ass(captions: list[Caption], pops: list[dict], path: str, *,
              width: int, height: int, font: str, size: int,
              color: str, highlight: str, pop_size: int) -> None:
    head = ASS_HEADER.format(w=width, h=height, font=font, size=size, pop_size=pop_size,
                             color=_ass_color(color), hl=_ass_color(highlight),
                             mask="&H000000FF")
    hl_tag, base_tag = f"{{\\c{_ass_color(highlight)}}}", f"{{\\c{_ass_color(color)}}}"
    lines = [head]
    for c in captions:
        pos = c.text.find(c.highlight)
        if pos >= 0:
            shown = (c.text[:pos] + hl_tag + c.text[pos:pos + len(c.highlight)] + base_tag
                     + c.text[pos + len(c.highlight):])
        else:
            shown = c.text
        lines.append(f"Dialogue: 0,{_ass_time(c.start)},{_ass_time(c.end)},Cap,,0,0,0,,{shown}\n")
    for p in pops:
        # кегль от длины: длинное слово при полном кегле вылезает за кадр
        sc = min(pop_size, int(1000 / max(4, len(p["text"]))))
        lines.append(f"Dialogue: 1,{_ass_time(p['start'])},{_ass_time(p['end'])},Pop,,0,0,0,,"
                     f"{{\\fs{sc}\\pos({width // 2},{int(height * 0.36)})}}{p['text']}\n")
    with open(path, "w", encoding="utf-8") as f:
        f.write("".join(lines))


def write_srt(captions: list[Caption], path: str) -> None:
    def ts(x: float) -> str:
        h, m = int(x // 3600), int(x % 3600 // 60)
        return f"{h:02d}:{m:02d}:{int(x % 60):02d},{int(round((x - int(x)) * 1000)):03d}"

    with open(path, "w", encoding="utf-8") as f:
        for i, c in enumerate(captions, 1):
            f.write(f"{i}\n{ts(c.start)} --> {ts(c.end)}\n{c.text}\n\n")
