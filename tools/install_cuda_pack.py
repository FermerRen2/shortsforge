"""Докладывает библиотеки CUDA рядом с приложением — чтобы распознавание шло на видеокарте.

В .exe библиотеки CUDA не входят: cublas и cudnn вместе занимают ~1,3 ГБ распакованными,
и таскать их в каждом файле бессмысленно. Если на машине есть видеокарта NVIDIA, запустите
один раз этот скрипт — он скачает библиотеки в папку данных приложения, и ShortsForge
подхватит их сам (и .exe, и запуск из исходников).

Запуск: python tools/install_cuda_pack.py [--dir <папка>]
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_DIR = Path.home() / "AppData" / "Local" / "ShortsForge" / "cuda"
PACKAGES = ["nvidia-cublas-cu12", "nvidia-cudnn-cu12", "nvidia-cuda-nvrtc-cu12"]


def main() -> int:
    target = DEFAULT_DIR
    if "--dir" in sys.argv:
        target = Path(sys.argv[sys.argv.index("--dir") + 1])
    target.mkdir(parents=True, exist_ok=True)
    print(f"ставлю библиотеки CUDA в {target}")
    print("(скачивание ~1,3 ГБ, это разово)")

    cmd = [sys.executable, "-m", "pip", "install", "--upgrade",
           "--no-warn-script-location", "--target", str(target), *PACKAGES]
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print("не удалось установить. Проверьте интернет и попробуйте снова.")
        return result.returncode

    # pip кладёт всё в <target>/nvidia/<lib>/bin — приложение ищет именно там
    found = sorted(p for p in (target / "nvidia").glob("*/bin") if p.is_dir())
    print("\nготово, найдено папок с библиотеками:", len(found))
    for p in found:
        dlls = list(p.glob("*.dll"))
        print(f"  {p}  ({len(dlls)} dll)")
    if not found:
        print("папки nvidia не появились — что-то пошло не так")
        return 1
    print("\nтеперь распознавание пойдёт на видеокарте (проверьте: shortsforge --selftest)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
