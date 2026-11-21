"""Снимок окна в PNG — для проверки внешнего вида без ручного скриншота.

Запуск: python tests/shot.py [файл.png]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from shortsforge.ui import theme
from shortsforge.ui.main_window import MainWindow


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "shot.png")
    app = QApplication(sys.argv[:1])
    app.setStyleSheet(theme.stylesheet())
    win = MainWindow()
    win.resize(1280, 840)
    win.show()

    def snap() -> None:
        win.grab().save(str(out))
        print(f"снимок: {out}")
        app.quit()

    QTimer.singleShot(1200, snap)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
