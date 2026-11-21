# -*- mode: python ; coding: utf-8 -*-
"""Сборка одного файла ShortsForge.exe.

Запуск:  python build_exe.py     (или  pyinstaller ShortsForge.spec --noconfirm --clean)

Внутрь кладём: ffmpeg/ffprobe (в папку bin), шаблон CapCut, шрифты Inter, иконки.
Модели распознавания не кладём: они скачиваются при первом запуске и весят больше гигабайта.
"""
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH)                                    # noqa: F821 - даёт PyInstaller
FFMPEG_DIR = Path(r"C:\Users\Kosmeya\AppData\Local\AIEditor\tools\ffmpeg\bin")

datas = [
    (str(ROOT / "assets"), "assets"),
]
binaries = []
for exe in ("ffmpeg.exe", "ffprobe.exe"):
    path = FFMPEG_DIR / exe
    if path.exists():
        binaries.append((str(path), "bin"))

# свои данные у зависимостей (ctranslate2, onnxruntime, tokenizers тянут dll/данные)
hiddenimports = ["ctranslate2", "onnxruntime", "tokenizers", "av", "huggingface_hub"]
for package in ("ctranslate2", "onnxruntime"):
    extra_datas, extra_binaries, extra_hidden = collect_all(package)
    datas += extra_datas
    binaries += extra_binaries
    hiddenimports += extra_hidden

excludes = [
    "tkinter", "matplotlib", "PIL.ImageQt", "IPython", "pytest",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtMultimedia",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtBluetooth",
    "PySide6.QtSerialPort", "PySide6.QtPositioning", "PySide6.QtNfc", "PySide6.QtSql",
    "PySide6.QtTest", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets",
    "torch", "torchaudio", "torchvision", "tensorflow",
]

a = Analysis(
    [str(ROOT / "run.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="ShortsForge",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                     # UPX калечит подписанные dll — не используем
    runtime_tmpdir=None,
    console=False,                 # окно без чёрной консоли
    disable_windowed_traceback=True,   # иначе ошибка запуска висит окном и блокирует проверку
    icon=str(ROOT / "assets" / "app.ico"),
    version=None,
)
