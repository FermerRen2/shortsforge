"""Точка входа для сборки .exe.

PyInstaller запускает этот файл как обычный скрипт, поэтому относительные импорты
(`from .core import ...`) внутри пакета не работают — здесь импорт абсолютный.
"""

from __future__ import annotations

import multiprocessing
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()
    from shortsforge.__main__ import main

    sys.exit(main())
