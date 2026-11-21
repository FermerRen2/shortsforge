"""Точка входа приложения."""

from __future__ import annotations

import sys


def main() -> int:
    from PySide6.QtWidgets import QApplication

    from .ui import theme
    from .ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("ShortsForge")
    app.setApplicationDisplayName("ShortsForge")
    app.setStyleSheet(theme.stylesheet())
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
