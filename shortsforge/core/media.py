"""Работа с медиа: поиск ffmpeg, зондирование, перепаковка, нарезка, измерение звука.

Почему отдельный модуль: половина проблем в нарезке — не в коде, а в том, что исходник
«сырой» (склейка HLS-кусков), и что ffmpeg может исказить время при перемотке. Здесь собраны
приёмы, которые это переживают, и все они проверены на реальной 9-часовой записи.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

SR = 16000          # частота для анализа звука
ENV_STEP = 160      # 10 мс на точку огибающей


# --- инструменты -------------------------------------------------------------
def _which(name: str, extra: list[str]) -> str | None:
    exe = shutil.which(name + ".exe")
    if exe:
        return exe
    for p in extra:
        if p and Path(p).exists():
            return p
    return None


def ffmpeg() -> str:
    """Путь к ffmpeg.exe. В PATH часто лежит только ffmpeg.cmd, а subprocess его не запускает."""
    exe = _which("ffmpeg", [
        os.path.expandvars(r"%LOCALAPPDATA%\AIEditor\tools\ffmpeg\bin\ffmpeg.exe"),
        r"C:\ffmpeg\bin\ffmpeg.exe",
    ])
    if not exe:
        raise RuntimeError("ffmpeg не найден. Установите ffmpeg и добавьте его в PATH.")
    return exe


def ffprobe() -> str:
    exe = _which("ffprobe", [
        os.path.expandvars(r"%LOCALAPPDATA%\AIEditor\tools\ffmpeg\bin\ffprobe.exe"),
        r"C:\ffmpeg\bin\ffprobe.exe",
    ])
    if not exe:
        raise RuntimeError("ffprobe не найден. Установите ffmpeg и добавьте его в PATH.")
    return exe


def run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    res = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and res.returncode != 0:
        tail = (res.stderr or "")[-700:]
        raise RuntimeError(f"ffmpeg вернул ошибку:\n{tail}")
    return res


# --- информация о файле ------------------------------------------------------
@dataclass
class MediaInfo:
    path: str
    duration: float
    width: int
    height: int
    fps: float
    has_audio: bool
    size_mb: float
    start_time: float

    @property
    def is_portrait(self) -> bool:
        return self.height > self.width

    def as_text(self) -> str:
        h = int(self.duration // 3600)
        m = int(self.duration % 3600 // 60)
        s = int(self.duration % 60)
        return (f"{h}:{m:02d}:{s:02d} · {self.width}×{self.height} · {self.fps:.0f} к/с · "
                f"{self.size_mb:.0f} МБ" + ("" if self.has_audio else " · без звука"))


def probe(path: str | Path) -> MediaInfo:
    out = run([ffprobe(), "-v", "error", "-print_format", "json",
               "-show_format", "-show_streams", str(path)]).stdout
    data = json.loads(out or "{}")
    fmt = data.get("format", {})
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if not video:
        raise RuntimeError("в файле нет видеодорожки")

    fps = 0.0
    for key in ("avg_frame_rate", "r_frame_rate"):
        raw = video.get(key) or "0/0"
        num, _, den = raw.partition("/")
        try:
            val = float(num) / float(den or 1)
        except (ZeroDivisionError, ValueError):
            val = 0.0
        if val > 0:
            fps = val
            break

    duration = float(fmt.get("duration") or video.get("duration") or 0)
    size_mb = float(fmt.get("size") or 0) / (1024 * 1024)
    return MediaInfo(
        path=str(path), duration=duration,
        width=int(video.get("width") or 0), height=int(video.get("height") or 0),
        fps=fps, has_audio=audio is not None, size_mb=size_mb,
        start_time=float(fmt.get("start_time") or 0),
    )


def needs_repack(info: MediaInfo, path: str | Path) -> tuple[bool, str]:
    """Нужна ли перепаковка: у «сырых» записей нет индекса и перемотка читает файл целиком."""
    raw = Path(path).read_bytes()[:400_000] if Path(path).stat().st_size > 400_000 else b""
    init_segments = raw.count(b"ftyp") - 1
    if init_segments >= 2:
        return True, ("Внутри файла несколько служебных заголовков — это склейка кусков стрима.\n"
                      "Перемотка в таком файле работает плохо, а плееры могут его не открыть.")
    if info.start_time > 5:
        return True, (f"Запись начинается не с нуля (сдвиг {info.start_time:.0f} с) — "
                      "обычные плееры на этом спотыкаются.")
    return False, ""


# --- перепаковка ------------------------------------------------------------
def repack(src: str | Path, out_dir: str | Path, segment_seconds: int = 3600,
           progress=None, cancel=None) -> list[Path]:
    """Режет запись на куски по часу без пережатия. Возвращает список файлов."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    total = probe(src).duration or 1.0
    pattern = str(out_dir / "part_%02d.mp4")
    cmd = [ffmpeg(), "-hide_banner", "-y", "-i", str(src), "-c", "copy",
           "-f", "segment", "-segment_time", str(segment_seconds),
           "-reset_timestamps", "1", pattern]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace")
    time_re = re.compile(r"time=(\d+):(\d+):(\d+\.\d+)")
    assert proc.stdout is not None
    for line in proc.stdout:
        if cancel and cancel():
            proc.kill()
            raise RuntimeError("отменено")
        m = time_re.search(line or "")
        if m and progress:
            done = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
            progress(min(0.99, done / total))
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError("перепаковка не удалась")
    parts = sorted(out_dir.glob("part_*.mp4"))
    if progress:
        progress(1.0)
    return parts


# --- карта времени -----------------------------------------------------------
@dataclass
class Part:
    path: Path
    start: float      # начало куска в общем времени записи
    duration: float

    @property
    def end(self) -> float:
        return self.start + self.duration


def parts_map(paths: list[str | Path]) -> list[Part]:
    """Собирает карту «общее время записи -> файл и время внутри него»."""
    parts, pos = [], 0.0
    for p in sorted(Path(x) for x in paths):
        info = probe(p)
        if info.duration <= 0:
            continue
        parts.append(Part(path=p, start=pos, duration=info.duration))
        pos += info.duration
    if not parts:
        raise RuntimeError("не удалось прочитать куски записи")
    return parts


def locate(parts: list[Part], t: float) -> tuple[Part, float]:
    """Файл и время внутри него для момента t."""
    for p in parts:
        if p.start <= t < p.end:
            return p, t - p.start
    last = parts[-1]
    return last, max(0.0, min(t - last.start, last.duration - 0.1))


# --- звук -------------------------------------------------------------------
def pcm(path: str | Path, start: float | None = None, dur: float | None = None,
        sample_rate: int = SR) -> np.ndarray:
    cmd = [ffmpeg(), "-hide_banner", "-v", "error"]
    if start is not None:
        cmd += ["-ss", f"{max(0.0, start):.3f}"]
    if dur is not None:
        cmd += ["-t", f"{max(0.0, dur):.3f}"]
    cmd += ["-i", str(path), "-vn", "-ac", "1", "-ar", str(sample_rate), "-f", "s16le", "-"]
    out = subprocess.run(cmd, capture_output=True).stdout
    return np.frombuffer(out, dtype=np.int16).astype(np.float32) / 32768.0


def envelope(path: str | Path, start: float | None = None, dur: float | None = None) -> np.ndarray:
    """Громкость по 10 мс — для поиска криков и для проверки, где реально лёг кусок."""
    data = pcm(path, start, dur)
    n = len(data) // ENV_STEP
    if n == 0:
        return np.zeros(0, dtype=np.float32)
    return np.sqrt((data[:n * ENV_STEP].reshape(n, ENV_STEP) ** 2).mean(axis=1) + 1e-12)


def loudness_per_second(path: str | Path, progress=None, cancel=None) -> list[float]:
    """дБ на каждую секунду записи, одним последовательным проходом."""
    cmd = [ffmpeg(), "-hide_banner", "-v", "error", "-i", str(path),
           "-vn", "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    levels: list[float] = []
    need = SR * 2 * 60
    assert proc.stdout is not None
    while True:
        if cancel and cancel():
            proc.kill()
            raise RuntimeError("отменено")
        buf = proc.stdout.read(need)
        if not buf:
            break
        data = np.frombuffer(buf, dtype=np.int16).astype(np.float32) / 32768.0
        for i in range(len(data) // SR):
            chunk = data[i * SR:(i + 1) * SR]
            rms = float(np.sqrt(np.mean(chunk ** 2)) + 1e-9)
            levels.append(round(20 * np.log10(rms), 1))
        if progress and len(levels) % 3000 < 60:
            progress(None, f"громкость: {len(levels)//60} мин")
    proc.stdout.close()
    proc.wait()
    return levels


def measure_offset(src: str | Path, local_start: float, game_audio: str | Path,
                   window: float = 45.0) -> float:
    """Где на самом деле начинается вырезанный кусок (по форме сигнала).

    Перемотка в «сырых» файлах иногда попадает не туда, а сравнение громкости обманывает —
    в игре музыка повторяется. Поэтому сравниваем форму сигнала и возвращаем фактическое начало.
    """
    from scipy.signal import fftconvolve

    cur = pcm(game_audio)
    if len(cur) < SR // 2:
        return local_start
    half = min(window, max(0.0, local_start))
    span = (max(0.0, local_start) - half) + (len(cur) / SR) + 6.0
    ref = pcm(src, max(0.0, local_start) - half, span)
    if len(ref) <= len(cur):
        return local_start
    corr = fftconvolve(ref, cur[::-1], mode="valid")
    idx = int(np.argmax(np.abs(corr)))
    peak = float(np.abs(corr).max() / (np.linalg.norm(cur) * np.linalg.norm(ref[:len(cur)]) + 1e-9))
    if peak < 0.25:
        return local_start
    return round(max(0.0, local_start) - half + idx / SR, 2)
