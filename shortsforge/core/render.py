"""Рендер ролика: слои отдельно, предпросмотр со впёченными титрами.

Слои рендерятся раздельно (игра снизу, вебка сверху), потому что заказчик правит ролик руками:
каждый слой должен двигаться и выключаться отдельно. Предпросмотр собирается из тех же слоёв,
чтобы можно было посмотреть результат, не открывая редактор.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import captions as caps
from . import media
from .config import Settings
from .layout import WebcamBox


@dataclass
class Pops:
    """Крупные слова-выкрики: время берётся из расшифровки, не выдумывается."""

    start: float
    end: float
    text: str

    def as_dict(self) -> dict:
        return {"start": round(self.start, 2), "end": round(self.end, 2), "text": self.text}


def find_pops(words: list, clip_start: float, clip_end: float, wanted: list[str],
              extra: int = 0) -> list[dict]:
    """Ищет в речи заданные слова; если их нет — берёт самые длинные эмоциональные слова."""
    def norm(s: str) -> str:
        return re.sub(r"[^\wа-яё]", "", s.lower())

    inside = [w for w in words if clip_start <= w.start < clip_end]
    found: list[dict] = []
    used: set[str] = set()
    targets = [norm(w) for w in wanted if w.strip()]
    for w in inside:
        key = norm(w.text)
        match = next((t for t in targets
                      if key == t or (len(t) >= 4 and key.startswith(t))), None)
        if match and match not in used:
            used.add(match)
            found.append({"start": round(float(w.start) - clip_start, 2),
                          "end": round(float(w.end) - clip_start + 0.25, 2),
                          "text": caps.mask_text(w.text.strip().upper())})
    if extra > 0 and len(found) < extra:
        scored = []
        for w in inside:
            key = norm(w.text)
            if len(key) < 5 or key in used:
                continue
            scored.append((len(key), w))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        for _, w in scored[:extra - len(found)]:
            found.append({"start": round(float(w.start) - clip_start, 2),
                          "end": round(float(w.end) - clip_start + 0.25, 2),
                          "text": caps.mask_text(w.text.strip().upper())})
    found.sort(key=lambda p: p["start"])
    return found[:4]


# --- рендер -----------------------------------------------------------------
def render_layers(src: str | Path, local_start: float, dur: float, out_dir: str | Path,
                  box: WebcamBox, cfg: Settings, mute_expr: str | None = None,
                  progress=None) -> tuple[Path, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    game = out_dir / "game.mp4"
    face = out_dir / "face.mp4"
    game_h = cfg.canvas_h - cfg.face_height

    if progress:
        progress(0.05, "рендер основы")
    cmd = [media.ffmpeg(), "-hide_banner", "-v", "error", "-y",
           "-ss", f"{max(0.0, local_start):.2f}", "-t", f"{dur:.2f}", "-i", str(src),
           "-vf", (f"fps={cfg.fps},scale=-2:{game_h}:flags=lanczos,"
                   f"crop={cfg.canvas_w}:{game_h}:(iw-{cfg.canvas_w})/2:0")]
    if mute_expr:
        cmd += ["-af", mute_expr]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
            "-c:a", "aac", "-b:a", "192k", str(game)]
    media.run(cmd)

    if progress:
        progress(0.6, "рендер вебки")
    media.run([media.ffmpeg(), "-hide_banner", "-v", "error", "-y",
               "-ss", f"{max(0.0, local_start):.2f}", "-t", f"{dur:.2f}", "-i", str(src),
               "-vf", (f"fps={cfg.fps},crop={box.w}:{box.h}:{box.x}:{box.y},"
                       f"scale={cfg.canvas_w}:{cfg.face_height}:flags=lanczos,"
                       f"unsharp=5:5:0.7:5:5:0.0"),
               "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", str(face)])
    if progress:
        progress(1.0, "слои готовы")
    return game, face


def render_preview(game: Path, face: Path, ass_path: Path, out_path: Path,
                   cfg: Settings, progress=None) -> Path:
    """Собирает слои в готовый вертикальный ролик с впёченными титрами."""
    if progress:
        progress(0.3, "сборка предпросмотра")
    ass_arg = str(ass_path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    media.run([media.ffmpeg(), "-hide_banner", "-v", "error", "-y",
               "-i", str(game), "-i", str(face),
               "-filter_complex",
               (f"[0:v]pad={cfg.canvas_w}:{cfg.canvas_h}:0:{cfg.face_height}:color=black[bg];"
                f"[bg][1:v]overlay=0:0:shortest=1[comp];"
                f"[comp]ass=filename='{ass_arg}'[v]"),
               "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-preset", "veryfast",
               "-crf", "20", "-c:a", "aac", "-b:a", "192k", str(out_path)])
    if progress:
        progress(1.0, "предпросмотр готов")
    return out_path


def snapshot(video: Path, t: float, out_png: Path) -> Path:
    """Кадр из ролика — для карточки в интерфейсе."""
    subprocess.run([media.ffmpeg(), "-hide_banner", "-v", "error", "-y",
                    "-ss", f"{max(0.0, t):.2f}", "-i", str(video), "-frames:v", "1",
                    "-vf", "scale=270:-2", str(out_png)], capture_output=True)
    return out_png
