"""Снимок страницы очереди с примером записей."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from shortsforge.core import batch
from shortsforge.ui import theme
from shortsforge.ui.main_window import MainWindow


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "shot_queue.png")
    app = QApplication(sys.argv[:1])
    app.setStyleSheet(theme.stylesheet(theme.load_fonts()))
    win = MainWindow()
    win.resize(1280, 840)
    win.show()

    win.queue.items = [
        batch.QueueItem(path=r"D:\Скачанные стримы\GTA 6 с Дариночкой 🤍 День 3 🔫  Донаты ВКЛ 🎮.mp4",
                        status=batch.STATUS_DONE, clips=12, duration_min=144,
                        detail="роликов 12 за 19 мин"),
        batch.QueueItem(path=r"D:\Скачанные стримы\GTA 6 с Дариночкой 🤍 День 4 🔫.mp4",
                        status=batch.STATUS_WORK, duration_min=138, detail="окно 22 из 48"),
        batch.QueueItem(path=r"D:\Скачанные стримы\RDR 2 вечер.mp4", duration_min=95),
        batch.QueueItem(path=r"D:\Скачанные стримы\битый_файл.mp4", status=batch.STATUS_FAIL,
                        detail="ffprobe: нет видеодорожки"),
    ]
    win._refresh_queue()
    win._set_page(4)

    def snap() -> None:
        win.grab().save(str(out))
        print(f"снимок: {out}")
        app.quit()

    QTimer.singleShot(1000, snap)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
