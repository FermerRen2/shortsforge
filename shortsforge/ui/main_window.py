"""Главное окно: проект, шаги конвейера, моменты, ролики, журнал."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtCore import QSize
from PySide6.QtGui import QDesktopServices, QFont, QIcon
from PySide6.QtWidgets import (QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel,
                               QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit,
                               QProgressBar, QPushButton, QScrollArea, QSizePolicy,
                               QStackedWidget, QTabWidget, QVBoxLayout, QWidget)

from ..core import capcut, media, pipeline, resources
from ..core.config import Settings, get as get_settings
from . import theme
from .jobs import TaskRunner
from .settings_dialog import SettingsDialog
from .widgets import DropArea, MomentCard, badge

APP_TITLE = "ShortsForge — нарезка вертикальных роликов"


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("Root")
        self.setWindowTitle(APP_TITLE)
        self.resize(1280, 840)
        self.cfg: Settings = get_settings()
        self.prj: pipeline.Project | None = None
        self.runner = TaskRunner()
        self.selected: dict[str, bool] = {}
        self.last_moments: list[dict] = []

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_sidebar())
        root.addWidget(self._build_main(), 1)
        QTimer.singleShot(200, self._refresh_env)

    # --- сборка интерфейса ---------------------------------------------------
    def _build_sidebar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("Sidebar")
        bar.setFixedWidth(272)
        lay = QVBoxLayout(bar)
        lay.setContentsMargins(18, 22, 18, 18)
        lay.setSpacing(8)

        logo = QLabel(f"SHORTS<span style='color:{theme.ACCENT2}'>FORGE</span>")
        logo.setObjectName("Logo")
        logo.setTextFormat(Qt.RichText)
        tag = QLabel("нарезка вертикальных роликов")
        tag.setObjectName("Tagline")
        lay.addWidget(logo)
        lay.addWidget(tag)
        lay.addSpacing(18)

        self.nav_project = self._nav_button("Проект", 0, "icon-project")
        self.nav_moments = self._nav_button("Моменты", 1, "icon-moments")
        self.nav_clips = self._nav_button("Ролики", 2, "icon-clips")
        self.nav_log = self._nav_button("Журнал", 3, "icon-log")
        for b in (self.nav_project, self.nav_moments, self.nav_clips, self.nav_log):
            lay.addWidget(b)
        lay.addStretch(1)

        self.env_box = QFrame()
        self.env_box.setObjectName("Card")
        env_lay = QVBoxLayout(self.env_box)
        env_lay.setContentsMargins(12, 10, 12, 10)
        env_lay.setSpacing(6)
        self.env_label = QLabel("проверяю окружение…")
        self.env_label.setObjectName("Muted")
        self.env_label.setTextFormat(Qt.RichText)
        self.env_label.setWordWrap(True)
        env_lay.addWidget(self.env_label)
        lay.addWidget(self.env_box)

        settings_btn = QPushButton("Настройки")
        gear = resources.icon("icon-settings")
        if gear.exists():
            settings_btn.setIcon(QIcon(str(gear)))
            settings_btn.setIconSize(QSize(17, 17))
        settings_btn.clicked.connect(self._open_settings)
        lay.addWidget(settings_btn)
        return bar

    def _nav_button(self, text: str, index: int, icon_name: str = "") -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName("Nav")
        icon_file = resources.icon(icon_name) if icon_name else None
        if icon_file and icon_file.exists():
            btn.setIcon(QIcon(str(icon_file)))
            btn.setIconSize(QSize(18, 18))
        btn.setCheckable(True)
        btn.setChecked(index == 0)
        btn.clicked.connect(lambda: self._set_page(index))
        return btn

    def _build_main(self) -> QWidget:
        main = QWidget()
        lay = QVBoxLayout(main)
        lay.setContentsMargins(22, 18, 22, 14)
        lay.setSpacing(14)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(2)
        self.h_title = QLabel("Новый проект")
        self.h_title.setObjectName("H1")
        self.h_sub = QLabel("перетащите запись стрима, приложение сделает из неё вертикальные ролики")
        self.h_sub.setObjectName("Muted")
        titles.addWidget(self.h_title)
        titles.addWidget(self.h_sub)
        header.addLayout(titles, 1)

        self.open_btn = QPushButton("Открыть видео")
        self.open_btn.clicked.connect(self._pick_file)
        self.folder_btn = QPushButton("Открыть папку")
        self.folder_btn.setObjectName("Ghost")
        folder_icon = resources.icon("icon-folder")
        if folder_icon.exists():
            self.folder_btn.setIcon(QIcon(str(folder_icon)))
            self.folder_btn.setIconSize(QSize(16, 16))
        self.folder_btn.clicked.connect(self._open_output_dir)
        header.addWidget(self.folder_btn)
        header.addWidget(self.open_btn)
        lay.addLayout(header)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_empty())
        self.stack.addWidget(self._build_workspace())
        lay.addWidget(self.stack, 1)

        # прогресс
        bottom = QFrame()
        bottom.setObjectName("Card")
        b_lay = QHBoxLayout(bottom)
        b_lay.setContentsMargins(14, 10, 14, 10)
        b_lay.setSpacing(12)
        self.status = QLabel("Готов к работе")
        self.status.setObjectName("Muted")
        self.status.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.progress.setFixedWidth(320)
        self.cancel_btn = QPushButton("Остановить")
        self.cancel_btn.setObjectName("Ghost")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel)
        b_lay.addWidget(self.status, 1)
        b_lay.addWidget(self.progress)
        b_lay.addWidget(self.cancel_btn)
        lay.addWidget(bottom)
        return main

    def _build_empty(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addSpacing(30)
        self.drop = DropArea()
        self.drop.fileDropped.connect(self.open_video)
        self.drop.clicked.connect(self._pick_file)
        lay.addWidget(self.drop)

        row = QHBoxLayout()
        row.setSpacing(12)
        for title, text in (
            ("1. Подготовка", "Перепаковывает «сырую» запись на куски, чтобы перемотка не занимала минуты."),
            ("2. Расшифровка", "Распознаёт речь локально на видеокарте — в сеть ничего не уходит."),
            ("3. Отбор", "DeepSeek читает расшифровку и предлагает моменты с заголовками."),
            ("4. Ролики", "Режет 9:16, кладёт вебку, титры и выкрики, собирает проект CapCut."),
        ):
            card = QFrame()
            card.setObjectName("Card")
            c_lay = QVBoxLayout(card)
            c_lay.setContentsMargins(14, 12, 14, 12)
            t = QLabel(title)
            t.setObjectName("H2")
            d = QLabel(text)
            d.setObjectName("Muted")
            d.setWordWrap(True)
            c_lay.addWidget(t)
            c_lay.addWidget(d)
            c_lay.addStretch(1)
            row.addWidget(card, 1)
        lay.addLayout(row)

        recent_box = QFrame()
        recent_box.setObjectName("Card")
        r_lay = QVBoxLayout(recent_box)
        r_lay.setContentsMargins(16, 12, 16, 12)
        r_lay.setSpacing(6)
        r_title = QLabel("Недавние записи")
        r_title.setObjectName("H2")
        r_lay.addWidget(r_title)
        self.recent_layout = QVBoxLayout()
        self.recent_layout.setSpacing(4)
        r_lay.addLayout(self.recent_layout)
        self.recent_empty = QLabel("Пока пусто — откройте первую запись.")
        self.recent_empty.setObjectName("Muted")
        r_lay.addWidget(self.recent_empty)
        lay.addWidget(recent_box)
        self._refresh_recent()
        lay.addStretch(1)
        return page

    def _build_workspace(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        self.info_card = QFrame()
        self.info_card.setObjectName("Card")
        i_lay = QHBoxLayout(self.info_card)
        i_lay.setContentsMargins(16, 12, 16, 12)
        i_lay.setSpacing(12)
        info_col = QVBoxLayout()
        info_col.setSpacing(4)
        self.file_name = QLabel("—")
        self.file_name.setObjectName("H2")
        self.file_meta = QLabel("")
        self.file_meta.setObjectName("Muted")
        info_col.addWidget(self.file_name)
        info_col.addWidget(self.file_meta)
        i_lay.addLayout(info_col, 1)
        self.badges = QHBoxLayout()
        self.badges.setSpacing(8)
        i_lay.addLayout(self.badges)
        lay.addWidget(self.info_card)

        steps = QHBoxLayout()
        steps.setSpacing(10)
        self.btn_prepare = QPushButton("1 · Подготовить файл")
        # кнопка 2 делает сразу два дела: быстрый поиск мест + отбор моментов.
        # Раньше это были два шага, и человек не понимал, чего ждёт и сколько ещё ждать.
        self.btn_transcribe = QPushButton("2 · Найти моменты")
        self.btn_transcribe.setObjectName("Primary")
        self.btn_full = QPushButton("Расшифровать всё")
        self.btn_full.setObjectName("Ghost")
        self.btn_full.setToolTip("Медленнее, но ничего не пропустит: расшифровывает запись целиком")
        self.btn_build = QPushButton("3 · Сделать ролики")
        self.btn_build.setObjectName("Primary")
        self.btn_prepare.clicked.connect(self._do_prepare)
        self.btn_transcribe.clicked.connect(self._do_find_moments)
        self.btn_full.clicked.connect(self._do_full_transcribe)
        self.btn_build.clicked.connect(self._do_build)
        steps.addWidget(self.btn_prepare, 1)
        steps.addWidget(self.btn_transcribe, 2)
        steps.addWidget(self.btn_full, 0)
        steps.addWidget(self.btn_build, 2)
        lay.addLayout(steps)

        self.hint = QLabel("")
        self.hint.setObjectName("Muted")
        self.hint.setWordWrap(True)
        lay.addWidget(self.hint)

        self.tabs = QTabWidget()
        self.moments_list = QListWidget()
        self.moments_list.setSpacing(2)
        self.tabs.addTab(self.moments_list, "Моменты")

        self.clips_scroll = QScrollArea()
        self.clips_scroll.setWidgetResizable(True)
        self.clips_host = QWidget()
        self.clips_layout = QVBoxLayout(self.clips_host)
        self.clips_layout.setSpacing(8)
        self.clips_layout.setContentsMargins(4, 4, 4, 4)
        self.clips_layout.addStretch(1)
        self.clips_scroll.setWidget(self.clips_host)
        self.tabs.addTab(self.clips_scroll, "Ролики")

        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("Log")
        self.log_view.setReadOnly(True)
        self.tabs.addTab(self.log_view, "Журнал")
        lay.addWidget(self.tabs, 1)
        return page

    # --- окружение -----------------------------------------------------------
    def _refresh_env(self) -> None:
        """Строки окружения цветными точками: без эмодзи, которые на Windows 10 не рисуются."""
        def row(ok: bool | None, text: str) -> str:
            color = theme.ACCENT2 if ok else (theme.WARN if ok is None else theme.DANGER)
            return f'<span style="color:{color}">●</span> {text}'

        lines = []
        try:
            media.ffmpeg()
            lines.append(row(True, "ffmpeg готов"))
        except RuntimeError:
            lines.append(row(False, "ffmpeg не найден"))
        try:
            import faster_whisper  # noqa: F401
            lines.append(row(True, "распознавание готово"))
        except ImportError:
            lines.append(row(False, "нет faster-whisper"))
        lines.append(row(True, "ключ DeepSeek задан") if self.cfg.has_key()
                     else row(None, "ключ DeepSeek не задан"))
        lines.append(row(True, "CapCut найден") if capcut.available()
                     else row(None, "CapCut не найден"))
        self.env_label.setText("<br>".join(lines))

    # --- страницы -------------------------------------------------------------
    def _set_page(self, index: int) -> None:
        for i, b in enumerate((self.nav_project, self.nav_moments, self.nav_clips, self.nav_log)):
            b.setChecked(i == index)
        if index == 3:
            self.tabs.setCurrentIndex(2)
        elif index == 2:
            self.tabs.setCurrentIndex(1)
        elif index == 1:
            self.tabs.setCurrentIndex(0)

    # --- работа с задачей -----------------------------------------------------
    def _run(self, func, on_done=None, label: str = "") -> None:
        if self.runner.busy():
            QMessageBox.information(self, "Подождите", "Уже идёт другая операция.")
            return
        self._set_busy(True)
        if label:
            self.status.setText(label)
        try:
            task = self.runner.start(func)
        except RuntimeError as e:
            self._set_busy(False)
            QMessageBox.warning(self, "Занято", str(e))
            return
        task.progress.connect(self._on_progress)
        task.log.connect(self._append_log)
        task.failed.connect(self._on_failed)
        if on_done:
            task.done.connect(on_done)
        task.finished.connect(lambda: self._set_busy(False))

    def _on_progress(self, value: float, text: str) -> None:
        if value < 0:
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, 1000)
            self.progress.setValue(int(value * 1000))
        if text:
            self.status.setText(text)
            self._append_log(text)

    def _on_failed(self, message: str) -> None:
        self.status.setText("Ошибка: " + message.splitlines()[0][:120])
        self._append_log("ОШИБКА: " + message)
        QMessageBox.critical(self, "Не получилось", message[:1500])

    def _set_busy(self, busy: bool) -> None:
        for b in (self.btn_prepare, self.btn_transcribe, self.btn_full, self.btn_build,
                  self.open_btn):
            b.setEnabled(not busy)
        self.cancel_btn.setEnabled(busy)
        if not busy:
            self.progress.setRange(0, 1000)
            if self.progress.value() >= 999:
                self.progress.setValue(1000)

    def _cancel(self) -> None:
        self.runner.cancel()
        self.status.setText("Останавливаю…")

    def _append_log(self, text: str) -> None:
        if text:
            stamp = time.strftime("%H:%M:%S")
            self.log_view.appendPlainText(f"{stamp}  {text}")

    # --- открытие видео -------------------------------------------------------
    def _pick_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Выберите запись", str(Path.home()),
            "Видео (*.mp4 *.mkv *.mov *.ts *.flv *.webm *.m4v);;Все файлы (*.*)")
        if path:
            self.open_video(path)

    def open_video(self, path: str) -> None:
        try:
            info = media.probe(path)
        except RuntimeError as e:
            QMessageBox.critical(self, "Файл не открылся", str(e))
            return
        work = Path(self.cfg.output_dir) / Path(path).stem
        try:
            self.prj = pipeline.open_project(path, work, self.cfg)
        except RuntimeError as e:
            QMessageBox.critical(self, "Ошибка", str(e))
            return
        if path not in self.cfg.recent_files:
            self.cfg.recent_files = ([path] + self.cfg.recent_files)[:10]
            try:
                self.cfg.save()
            except OSError:
                pass
        self._refresh_recent()
        self.stack.setCurrentIndex(1)
        self.h_title.setText(Path(path).name)
        self.h_sub.setText(f"рабочая папка: {work}")
        self.file_name.setText(Path(path).name)
        self.file_meta.setText(info.as_text())
        self.selected = {}
        self._refresh_badges()
        self._update_hint()
        self._render_moments(self.prj.candidates or [])
        self._render_clips(self.prj.clips or [])
        self._append_log(f"открыт файл: {path}")
        if self.prj.notes:
            for n in self.prj.notes[-5:]:
                self._append_log("· " + n)

    def _update_hint(self) -> None:
        """Понятная подсказка: что нажимать и сколько это займёт."""
        if not self.prj or not hasattr(self, "hint"):
            return
        info = self.prj.info
        minutes = (info.duration / 60) if info else 0
        fast = max(1.0, minutes / 18)      # замерено: 2,5 ч записи ≈ 8 минут в быстром режиме
        full = pipeline.estimate_full_minutes(self.prj)
        self.hint.setText(
            f"Запись {minutes:.0f} мин. «Найти моменты» — примерно {fast:.0f} мин "
            f"(слушает громкость и расшифровывает только громкие места). "
            f"«Расшифровать всё» — около {full:.0f} мин, зато ничего не пропустит."
        )

    def _refresh_badges(self) -> None:
        while self.badges.count():
            item = self.badges.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not self.prj:
            return
        words = len(self.prj.words)
        self.badges.addWidget(badge(f"слов: {words}", "good" if words else "normal"))
        if self.prj.parts and len(self.prj.parts) > 1:
            self.badges.addWidget(badge(f"кусков: {len(self.prj.parts)}"))
        if self.prj.webcam:
            w = self.prj.webcam
            self.badges.addWidget(badge(f"вебка {w['w']}×{w['h']}", "good"))
        if self.prj.candidates:
            self.badges.addWidget(badge(f"моментов: {len(self.prj.candidates)}"))
        if self.prj.clips:
            self.badges.addWidget(badge(f"роликов: {len(self.prj.clips)}", "good"))

    # --- шаги -----------------------------------------------------------------
    def _require_project(self) -> bool:
        if not self.prj:
            QMessageBox.information(self, "Сначала файл", "Откройте запись — кнопка «Открыть видео».")
            return False
        return True

    def _do_prepare(self) -> None:
        if not self._require_project():
            return
        assert self.prj
        self._run(lambda progress, cancel: pipeline.prepare(self.prj, progress, cancel),
                  on_done=self._after_prepare, label="подготовка файла")

    def _after_prepare(self, prj) -> None:
        self.prj = prj
        self._refresh_badges()
        self._append_log(f"готово: кусков {len(prj.parts)}")

    def _do_transcribe(self) -> None:
        if not self._require_project():
            return
        assert self.prj
        self._run(lambda progress, cancel: pipeline.transcribe(self.prj, progress, cancel),
                  on_done=self._after_transcribe, label="распознавание речи")

    def _after_transcribe(self, prj) -> None:
        self.prj = prj
        self._refresh_badges()
        self._append_log(f"расшифровка: {len(prj.words)} слов")

    def _do_find_moments(self) -> None:
        """Кнопка 2: быстрый поиск мест + отбор моментов за один заход."""
        if not self._require_project():
            return
        assert self.prj
        prj = self.prj
        self._run(lambda progress, cancel: self._find_fast(prj, progress, cancel),
                  on_done=self._after_suggest, label="ищу моменты")

    @staticmethod
    def _find_fast(prj, progress, cancel):
        pipeline.prepare(prj, lambda p, m="": progress(p * 0.05, m), cancel)
        pipeline.fast_select(prj, lambda p, m="": progress(0.05 + p * 0.85, m), cancel)
        return pipeline.suggest(prj, lambda p, m="": progress(0.9 + p * 0.1, m), cancel)

    def _do_full_transcribe(self) -> None:
        """Запасной путь: расшифровать всю запись (медленно, зато ничего не пропустит)."""
        if not self._require_project():
            return
        assert self.prj
        minutes = pipeline.estimate_full_minutes(self.prj)
        if QMessageBox.question(
                self, "Полная расшифровка",
                f"Это займёт примерно {minutes:.0f} минут и загрузит видеокарту.\n"
                f"Быстрый поиск делает то же самое за пару минут.\n\nВсё равно расшифровать всё?"
        ) != QMessageBox.Yes:
            return
        prj = self.prj
        self._run(lambda progress, cancel: self._find_full(prj, progress, cancel),
                  on_done=self._after_suggest, label="расшифровка всей записи")

    @staticmethod
    def _find_full(prj, progress, cancel):
        pipeline.prepare(prj, lambda p, m="": progress(p * 0.03, m), cancel)
        pipeline.transcribe(prj, lambda p, m="": progress(0.03 + p * 0.87, m), cancel)
        return pipeline.suggest(prj, lambda p, m="": progress(0.9 + p * 0.1, m), cancel)

    def _do_suggest(self) -> None:
        if not self._require_project():
            return
        assert self.prj
        if not self.prj.words:
            QMessageBox.information(self, "Нет расшифровки",
                                    "Сначала нажмите «Найти моменты» (шаг 2).")
            return
        self._run(lambda progress, cancel: pipeline.suggest(self.prj, progress, cancel),
                  on_done=self._after_suggest, label="отбор моментов")

    def _after_suggest(self, prj) -> None:
        self.prj = prj
        self._refresh_badges()
        self._render_moments(prj.candidates)
        self.tabs.setCurrentIndex(0)
        self._set_page(1)
        self._append_log(f"моментов: {len(prj.candidates)}")

    def _do_build(self) -> None:
        if not self._require_project():
            return
        assert self.prj
        chosen = [m for m in self.last_moments if self.selected.get(self._moment_key(m), True)]
        if not chosen:
            QMessageBox.information(self, "Нет моментов",
                                    "Сначала отберите моменты (шаг 3).")
            return
        self._run(lambda progress, cancel: pipeline.build_all(self.prj, chosen, progress, cancel),
                  on_done=self._after_build, label="сборка роликов")

    def _after_build(self, clips) -> None:
        assert self.prj
        self._render_clips(self.prj.clips)
        self._refresh_badges()
        self.tabs.setCurrentIndex(1)
        self._set_page(2)
        self._append_log(f"роликов собрано: {len(clips)}")

    # --- списки ---------------------------------------------------------------
    @staticmethod
    def _moment_key(m: dict) -> str:
        return f"{m.get('start')}-{m.get('end')}"

    def _render_moments(self, moments: list[dict]) -> None:
        self.last_moments = list(moments)
        self.moments_list.clear()
        for m in moments:
            key = self._moment_key(m)
            item = QListWidgetItem()
            card = MomentCard({**m, "selected": self.selected.get(key, True)})
            item.setSizeHint(card.sizeHint())
            item.setData(Qt.UserRole, m)
            self.moments_list.addItem(item)
            self.moments_list.setItemWidget(item, card)
        if not moments:
            item = QListWidgetItem("Пока пусто: отберите моменты на шаге 3 или загрузите проект.")
            item.setFlags(Qt.NoItemFlags)
            self.moments_list.addItem(item)

    def _render_clips(self, clips: list[dict]) -> None:
        while self.clips_layout.count() > 1:
            item = self.clips_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not clips:
            label = QLabel("Роликов пока нет.")
            label.setObjectName("Muted")
            self.clips_layout.insertWidget(0, label)
            return

        for i, clip in enumerate(sorted(clips, key=lambda c: c.get("start", 0))):
            card = self._clip_card(clip)
            self.clips_layout.insertWidget(i, card)

    def _clip_card(self, clip: dict) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")
        row = QHBoxLayout(card)
        row.setContentsMargins(14, 10, 14, 10)
        row.setSpacing(12)

        cover = QLabel()
        cover.setFixedSize(96, 54)
        cover.setAlignment(Qt.AlignCenter)
        cover.setStyleSheet(f"background:#0a0d13;border-radius:8px;border:1px solid {theme.BORDER};")
        img = Path(clip.get("folder", "")) / "cover.jpg"
        if img.exists():
            from PySide6.QtGui import QPixmap
            cover.setPixmap(QPixmap(str(img)).scaled(96, 54, Qt.KeepAspectRatioByExpanding,
                                                     Qt.SmoothTransformation))
        else:
            cover.setText("🎞")
        row.addWidget(cover)

        col = QVBoxLayout()
        col.setSpacing(2)
        title = QLabel(clip.get("title") or clip.get("name"))
        title.setObjectName("H2")
        title.setWordWrap(True)
        meta = QLabel(f"{clip.get('duration', 0):.0f} с · титров {clip.get('captions', 0)} · "
                      f"выкриков {clip.get('pops', 0)}")
        meta.setObjectName("Muted")
        col.addWidget(title)
        col.addWidget(meta)
        row.addLayout(col, 1)

        for check in clip.get("checks") or []:
            kind = "good" if check.get("ok") else ("bad" if check.get("ok") is False else "normal")
            lbl = badge(check.get("name", ""), kind)
            lbl.setToolTip(check.get("detail", ""))
            row.addWidget(lbl)

        if clip.get("preview") and Path(clip["preview"]).exists():
            play = QPushButton("▶ смотреть")
            play.clicked.connect(lambda _=False, p=clip["preview"]: self._open_path(p))
            row.addWidget(play)
        folder = Path(clip.get("folder", ""))
        if folder.exists():
            open_btn = QPushButton("папка")
            open_btn.setObjectName("Ghost")
            open_btn.clicked.connect(lambda _=False, p=str(folder): self._open_path(p))
            row.addWidget(open_btn)
        return card

    def _refresh_recent(self) -> None:
        """Список последних открытых записей — чтобы не искать файл заново."""
        if not hasattr(self, "recent_layout"):
            return
        while self.recent_layout.count():
            item = self.recent_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        recent = [p for p in self.cfg.recent_files if Path(p).exists()][:6]
        self.recent_empty.setVisible(not recent)
        for path in recent:
            btn = QPushButton(f"🎞  {Path(path).name}")
            btn.setObjectName("Ghost")
            btn.setToolTip(path)
            btn.setStyleSheet("text-align:left; padding:8px 12px;")
            btn.clicked.connect(lambda _=False, p=path: self.open_video(p))
            self.recent_layout.addWidget(btn)

    # --- прочее ---------------------------------------------------------------
    def _open_path(self, path: str) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _open_output_dir(self) -> None:
        target = Path(self.cfg.output_dir)
        target.mkdir(parents=True, exist_ok=True)
        self._open_path(str(target))

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self.cfg, self)
        if dialog.exec():
            self._refresh_env()
            self._append_log("настройки сохранены")
