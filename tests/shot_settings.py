"""Снимок окна настроек — для README."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from shortsforge.core.config import Settings
from shortsforge.ui import theme
from shortsforge.ui.settings_dialog import SettingsDialog


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "shot_settings.png")
    app = QApplication(sys.argv[:1])
    app.setStyleSheet(theme.stylesheet())
    dlg = SettingsDialog(Settings())
    dlg.show()

    def snap() -> None:
        dlg.grab().save(str(out))
        print(f"снимок: {out}")
        app.quit()

    QTimer.singleShot(900, snap)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
