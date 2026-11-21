"""Где искать ресурсы: в репозитории или внутри собранного .exe.

PyInstaller распаковывает данные в `sys._MEIPASS`. Все пути к шаблонам, шрифтам, иконкам и
бинарям ffmpeg идут только через этот модуль — иначе после сборки приложение «не находит»
шаблон CapCut и ffmpeg, хотя рядом с исходниками всё работало.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def base_dir() -> Path:
    """Корень с данными: temp-папка распаковки для .exe, папка проекта для запуска из кода."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[2]


def asset(rel: str) -> Path:
    """Путь к файлу из `assets/`."""
    return base_dir() / "assets" / rel


def icon(name: str) -> Path:
    return asset(f"{name}.svg")


def binary(name: str) -> str | None:
    """ffmpeg/ffprobe: сначала рядом с приложением (собранный exe), потом PATH."""
    exe = name + (".exe" if os.name == "nt" else "")
    candidates = [
        base_dir() / "bin" / exe,
        base_dir() / exe,
        Path(sys.executable).parent / exe,
        Path(sys.executable).parent / "bin" / exe,
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    # именно .exe: shutil.which("ffmpeg") на Windows находит ffmpeg.CMD, а subprocess его
    # не запускает — на этом уже спотыкались
    found = shutil.which(exe)
    if found and found.lower().endswith(".exe"):
        return found
    loose = shutil.which(name)
    if loose and loose.lower().endswith(".exe"):
        return loose
    # запасные места на этой машине
    for p in (
        os.path.expandvars(r"%LOCALAPPDATA%\AIEditor\tools\ffmpeg\bin") + "\\" + exe,
        r"C:\ffmpeg\bin" + "\\" + exe,
    ):
        if Path(p).exists():
            return p
    return None


def cuda_dirs() -> list[Path]:
    """Где искать DLL CUDA: сначала рядом с приложением, потом папка данных, потом pip-колёса.

    В собранный .exe библиотеки CUDA не входят (это ещё ~1,3 ГБ распакованных), но их можно
    доложить рядом: `python tools/install_cuda_pack.py`. Тогда распознавание пойдёт на
    видеокарте, как при запуске из исходников.
    """
    found: list[Path] = []
    roots = [base_dir() / "cuda", writable_dir() / "cuda"]
    for root in roots:
        for lib in ("cublas", "cudnn", "cuda_nvrtc", "cuda_runtime"):
            for cand in (root / lib / "bin", root / "nvidia" / lib / "bin"):
                if cand.is_dir():
                    found.append(cand)
    import site

    for sp in list(site.getsitepackages()) + [site.getusersitepackages()]:
        nvidia = Path(sp) / "nvidia"
        if not nvidia.is_dir():
            continue
        for lib in ("cublas", "cudnn", "cuda_nvrtc", "cuda_runtime"):
            cand = nvidia / lib / "bin"
            if cand.is_dir():
                found.append(cand)
    return found


def writable_dir() -> Path:
    """Куда писать, если рядом с exe нельзя (например, он в Program Files)."""
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home())
    d = base / "ShortsForge"
    d.mkdir(parents=True, exist_ok=True)
    return d
