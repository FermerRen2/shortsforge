"""Точка входа приложения."""

from __future__ import annotations

import sys


def _run_selftest(quiet: bool = False) -> int:
    from .core import selftest

    code = selftest.run()
    if quiet:
        return code
    # в собранном .exe нет консоли — результат показываем окном, иначе он потеряется
    try:
        if getattr(sys, "frozen", False):
            from PySide6.QtWidgets import QApplication, QMessageBox

            from .core import resources

            app = QApplication.instance() or QApplication(sys.argv[:1])
            log = resources.writable_dir() / "selftest.log"
            text = log.read_text(encoding="utf-8") if log.exists() else "лог не записан"
            box = QMessageBox()
            box.setWindowTitle("ShortsForge · самопроверка")
            box.setText("Всё в порядке" if code == 0 else "Есть ошибки — подробности ниже")
            box.setDetailedText(text)
            box.exec()
    except Exception:                                # noqa: BLE001 - окно не должно ронять проверку
        pass
    return code


def _run_e2e(video: str, count: int) -> int:
    """Скрытый режим проверки: полный конвейер на реальном файле, без интерфейса.

    Нужен, чтобы убедиться, что собранный .exe не просто открывается, а действительно
    распознаёт речь, режет и собирает проект CapCut.
    """
    import json
    from pathlib import Path

    from .core import pipeline, resources
    from .core.config import Settings

    cfg = Settings()
    work = resources.writable_dir() / "e2e"
    if work.exists():
        import shutil

        shutil.rmtree(work, ignore_errors=True)
    cfg.output_dir = str(work)
    cfg.ai_clips = count

    lines: list[str] = []

    def progress(value, text=""):
        if text:
            lines.append(f"[{value:.0%}] {text}" if value is not None else text)

    prj = pipeline.open_project(video, Path(work) / "work", cfg)
    progress(0, "подготовка")
    pipeline.prepare(prj, progress)
    progress(0, "расшифровка")
    pipeline.transcribe(prj, progress)
    pipeline.suggest(prj, progress)
    clips = pipeline.build_all(prj, prj.candidates[:count], progress)

    ok = True
    for clip in clips:
        bad = [c for c in clip.get("checks") or [] if c.get("ok") is False]
        ok = ok and not bad
        lines.append(f"{clip['name']}: {clip['duration']:.0f} с, титров {clip['captions']}, "
                     f"выкриков {clip['pops']}, проект {'есть' if clip['capcut'] else 'нет'}")
        for c in clip.get("checks") or []:
            lines.append(f"   [{'ok' if c.get('ok') else '!!'}] {c.get('name')}: {c.get('detail')}")
    lines.append(f"ИТОГ: роликов {len(clips)}, замечаний {'нет' if ok else 'есть'}")
    log = resources.writable_dir() / "e2e.log"
    log.write_text("\n".join(lines), encoding="utf-8")
    try:
        print("\n".join(lines))
    except Exception:                                # noqa: BLE001
        pass
    return 0 if (ok and clips) else 1


def main() -> int:
    if "--e2e" in sys.argv:
        video = sys.argv[sys.argv.index("--e2e") + 1]
        count = int(sys.argv[sys.argv.index("--e2e") + 2]) if len(sys.argv) > sys.argv.index("--e2e") + 2 else 2
        return _run_e2e(video, count)
    if "--selftest" in sys.argv:
        return _run_selftest(quiet="--quiet" in sys.argv)
    if "--version" in sys.argv:
        from . import __version__

        print(f"ShortsForge {__version__}")
        return 0

    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from .core import resources
    from .ui import theme
    from .ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("ShortsForge")
    app.setApplicationDisplayName("ShortsForge")

    family = theme.load_fonts()
    app.setStyleSheet(theme.stylesheet(family))
    icon_file = resources.asset("app-icon.svg")
    if icon_file.exists():
        app.setWindowIcon(QIcon(str(icon_file)))

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
