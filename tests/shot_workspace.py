"""Снимок окна с загруженным проектом — для проверки рабочего вида.

Запуск: python tests/shot_workspace.py [файл.png]
Создаёт воображаемый проект в памяти: моменты и готовые ролики, без запуска конвейера.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from shortsforge.ui import theme
from shortsforge.ui.main_window import MainWindow


MOMENTS = [
    {"start": 754.0, "end": 792.0, "title": "«Я решил проверить физику» — и нас тут же флипнуло",
     "reason": "Крючок с первой секунды: обещает провал и сразу его показывает", "source": "DeepSeek"},
    {"start": 16480.0, "end": 16512.0, "title": "«Она сама поворачивает направо» — вот это неуправляемое",
     "reason": "Панчлайн про кривую машину, понятен без контекста", "source": "DeepSeek"},
    {"start": 22840.0, "end": 22866.0, "title": "Чёрт, поцарапала! Это было идеально",
     "reason": "Реакция на испорченную покраску — эмоция и развязка", "source": "DeepSeek"},
    {"start": 27080.0, "end": 27105.0, "title": "«Какая ракетница? У меня в руках ракетница!»",
     "reason": "Недоумение и смех, короткая сцена", "source": "DeepSeek"},
]

CLIPS = [
    {"name": "r01-fizika", "title": "«Я решил проверить физику» — и нас тут же флипнуло",
     "start": 754.0, "duration": 40.0, "captions": 43, "pops": 1,
     "folder": "", "preview": "",
     "checks": [{"name": "титры против звука", "ok": True, "detail": "сдвиг -0.25 с"},
                {"name": "проект CapCut", "ok": True, "detail": "целостный"},
                {"name": "слои", "ok": True, "detail": "титров 43, выкриков 1"}]},
    {"name": "r04-avtopodstava", "title": "Это автоподстава! Ты чего в меня целишься?",
     "start": 16547.0, "duration": 27.0, "captions": 11, "pops": 1,
     "folder": "", "preview": "",
     "checks": [{"name": "титры против звука", "ok": True, "detail": "сдвиг -0.5 с"},
                {"name": "проект CapCut", "ok": False, "detail": "не собран"},
                {"name": "слои", "ok": True, "detail": "титров 11, выкриков 1"}]},
]


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "shot_workspace.png")
    app = QApplication(sys.argv[:1])
    app.setStyleSheet(theme.stylesheet())
    win = MainWindow()
    win.resize(1280, 840)
    win.show()

    win.h_title.setText("Recrent (live) 2026-11-18 1851.mp4")
    win.h_sub.setText("рабочая папка: C:\\Users\\Public\\Videos\\ShortsForge\\Recrent")
    win.file_name.setText("Recrent (live) 2026-11-18 1851.mp4")
    win.file_meta.setText("9:06:03 · 1920×1080 · 60 к/с · 30040 МБ")
    win.stack.setCurrentIndex(1)
    win._render_moments(MOMENTS)
    win._render_clips(CLIPS)
    win.progress.setValue(640)
    win.status.setText("[3/4] r04-avtopodstava: титры и звук")
    win._append_log("открыт файл: Recrent (live) 2026-11-18 1851.mp4")
    win._append_log("перепаковка: внутри файла несколько служебных заголовков")
    win._append_log("распознано 1 из 546 мин")
    win._append_log("ИИ предложил 12 моментов")

    def snap() -> None:
        win.grab().save(str(out))
        print(f"снимок: {out}")
        app.quit()

    QTimer.singleShot(1200, snap)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
