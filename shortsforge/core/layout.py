"""Поиск окна вебки в кадре по лицу (OpenCV YuNet).

Раскладка ролика держится на координатах врезки: вебка сверху, игра снизу. Если координаты
взяты «по памяти» с другого стрима, в кадр попадает обрезанная голова — глазами это замечаешь
не сразу. Поэтому окно вебки измеряется: берём кадры по всей записи, ищем лица, отбрасываем
выбросы (в кадрах игры детектор тоже «находит» лица) и считаем окно по медиане.
"""
from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

MODEL_URL = ("https://github.com/opencv/opencv_zoo/raw/main/models/"
             "face_detection_yunet/face_detection_yunet_2023mar.onnx")


@dataclass
class WebcamBox:
    x: int
    y: int
    w: int
    h: int
    frame_w: int
    frame_h: int
    faces_found: int
    corner: str = ""

    def as_dict(self) -> dict:
        return {"x": self.x, "y": self.y, "w": self.w, "h": self.h,
                "frame": [self.frame_w, self.frame_h], "corner": self.corner}


def model_path(cache_dir: str | Path) -> Path:
    """Модель YuNet: 227 КБ, качается один раз."""
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / "face_detection_yunet_2023mar.onnx"
    if path.exists() and path.stat().st_size > 100_000:
        return path
    import urllib.request

    urllib.request.urlretrieve(MODEL_URL, path)
    return path


def _grab(video: str | Path, t: float) -> np.ndarray | None:
    from . import media

    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "f.png"
        subprocess.run([media.ffmpeg(), "-hide_banner", "-v", "error", "-y",
                        "-ss", f"{max(0.0, t):.2f}", "-i", str(video),
                        "-frames:v", "1", str(out)], capture_output=True)
        if not out.exists():
            return None
        return cv2.imread(str(out))


def detect(video: str | Path, cache_dir: str | Path, samples: int = 24,
           duration: float | None = None) -> WebcamBox:
    """Ищет окно вебки. Бросает RuntimeError, если лиц не нашлось."""
    from . import media

    if duration is None:
        duration = media.probe(video).duration
    detector = cv2.FaceDetectorYN.create(str(model_path(cache_dir)), "", (1280, 720), 0.6, 0.3, 5000)

    boxes: list[tuple[float, float, float, float]] = []
    frame_shape: tuple[int, int] | None = None
    for i in range(samples):
        t = duration * (i + 0.5) / samples
        frame = _grab(video, t)
        if frame is None:
            continue
        h, w = frame.shape[:2]
        frame_shape = (w, h)
        scale = 1280 / w
        small = cv2.resize(frame, (1280, int(h * scale)))
        detector.setInputSize((small.shape[1], small.shape[0]))
        _, faces = detector.detect(small)
        if faces is None or len(faces) == 0:
            continue
        f = max(faces, key=lambda r: r[-1])
        x, y, fw, fh = [float(v) / scale for v in f[:4]]
        boxes.append((x, y, fw, fh))

    if not boxes or frame_shape is None:
        raise RuntimeError("лицо в кадре не найдено — окно вебки определить нечем")

    # отсев выбросов: медиана по центрам, всё дальше 1,5 медианного расстояния — не вебка
    cxs = sorted(b[0] + b[2] / 2 for b in boxes)
    cys = sorted(b[1] + b[3] / 2 for b in boxes)
    mcx, mcy = cxs[len(cxs) // 2], cys[len(cys) // 2]
    dists = sorted(((b[0] + b[2] / 2 - mcx) ** 2 + (b[1] + b[3] / 2 - mcy) ** 2) ** 0.5 for b in boxes)
    limit = max(40.0, dists[len(dists) // 2] * 1.5 + 40.0)
    kept = [b for b in boxes
            if ((b[0] + b[2] / 2 - mcx) ** 2 + (b[1] + b[3] / 2 - mcy) ** 2) ** 0.5 <= limit] or boxes

    fw = sorted(b[2] for b in kept)[len(kept) // 2]
    fh = sorted(b[3] for b in kept)[len(kept) // 2]
    cx = sorted(b[0] + b[2] / 2 for b in kept)[len(kept) // 2]
    cy = sorted(b[1] + b[3] / 2 for b in kept)[len(kept) // 2]

    W, H = frame_shape
    # окно вебки — 16:9 высотой в три лица (проверено на реальном стриме: лицо 87 px, окно 252 px)
    w = min(W, int(fh * 3.0) // 2 * 2)
    h = min(H, int(w * 9 / 16) // 2 * 2)
    x = max(0, min(W - w, int(cx - w / 2) // 2 * 2))
    y = max(0, min(H - h, int(cy - h / 2) // 2 * 2))
    corner = ("left" if x + w / 2 < W / 2 else "right") + "_" + \
             ("top" if y + h / 2 < H / 2 else "bottom")
    return WebcamBox(x=x, y=y, w=w, h=h, frame_w=W, frame_h=H,
                     faces_found=len(kept), corner=corner)


def crop_preview(video: str | Path, box: WebcamBox, t: float, out_png: str | Path) -> Path:
    """Вырезает найденное окно — чтобы человек посмотрел глазами, что именно берётся."""
    frame = _grab(video, t)
    if frame is None:
        raise RuntimeError("кадр не получен")
    crop = frame[box.y:box.y + box.h, box.x:box.x + box.w]
    cv2.imwrite(str(out_png), crop)
    return Path(out_png)
