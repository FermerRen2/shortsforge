"""Сборка ShortsForge.exe одной командой.

Запуск: python build_exe.py
Результат: dist/ShortsForge.exe (один файл, всё внутри).

После сборки скрипт сам запускает `--selftest` у готового exe и печатает отчёт: так видно,
что внутри упаковано всё нужное (ffmpeg, шаблон CapCut, шрифты, разбор ответов ИИ).
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> int:
    for folder in ("build", "dist"):
        shutil.rmtree(ROOT / folder, ignore_errors=True)

    print("собираю .exe (это несколько минут)…")
    started = time.time()
    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller", "ShortsForge.spec", "--noconfirm", "--clean"],
        cwd=ROOT,
    )
    if result.returncode != 0:
        print("сборка не удалась")
        return result.returncode

    exe = ROOT / "dist" / "ShortsForge.exe"
    if not exe.exists():
        print("exe не появился")
        return 1
    size_mb = exe.stat().st_size / (1024 * 1024)
    print(f"готово за {time.time() - started:.0f} с: {exe} ({size_mb:.0f} МБ)")

    print("\nпроверяю собранный файл…")
    log = Path.home() / "AppData" / "Local" / "ShortsForge" / "selftest.log"
    log.unlink(missing_ok=True)
    check = subprocess.run([str(exe), "--selftest", "--quiet"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=600)
    out = (check.stdout or "") + (check.stderr or "")
    if len(out.strip()) < 40 and log.exists():
        out = log.read_text(encoding="utf-8")
    print(out[-3000:])
    return 0 if (check.returncode == 0 and "ОШИБКА" not in out) else 1


if __name__ == "__main__":
    raise SystemExit(main())
