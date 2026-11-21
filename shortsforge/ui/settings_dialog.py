"""Окно настроек: ключ DeepSeek с проверкой, папки, распознавание, вид кадра."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QPushButton, QSpinBox, QTabWidget,
                               QVBoxLayout, QWidget)

from ..core import deepseek
from ..core.config import Settings


class SettingsDialog(QDialog):
    def __init__(self, cfg: Settings, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("Настройки ShortsForge")
        self.setMinimumWidth(640)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)

        tabs = QTabWidget()
        tabs.addTab(self._tab_ai(), "ИИ и ключ")
        tabs.addTab(self._tab_whisper(), "Распознавание")
        tabs.addTab(self._tab_frame(), "Кадр и титры")
        tabs.addTab(self._tab_output(), "Файлы")
        root.addWidget(tabs)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Сохранить")
        buttons.button(QDialogButtonBox.Cancel).setText("Отмена")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    # --- вкладки ---
    def _tab_ai(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        box = QGroupBox("DeepSeek")
        form = QFormLayout(box)
        self.key_edit = QLineEdit(self.cfg.api_key)
        self.key_edit.setEchoMode(QLineEdit.Password)
        self.key_edit.setPlaceholderText("sk-… (ключ с platform.deepseek.com)")
        show = QPushButton("показать")
        show.setObjectName("Ghost")
        show.setCheckable(True)
        show.toggled.connect(
            lambda on: self.key_edit.setEchoMode(QLineEdit.Normal if on else QLineEdit.Password))
        key_row = QHBoxLayout()
        key_row.addWidget(self.key_edit, 1)
        key_row.addWidget(show)
        test = QPushButton("проверить ключ")
        test.clicked.connect(self._test_key)
        key_row.addWidget(test)
        form.addRow("API-ключ", key_row)

        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.addItems(["deepseek-chat", "deepseek-reasoner"])
        self.model_combo.setCurrentText(self.cfg.deepseek_model)
        form.addRow("Модель", self.model_combo)

        self.base_edit = QLineEdit(self.cfg.deepseek_base_url)
        form.addRow("Адрес API", self.base_edit)

        self.clips_spin = QSpinBox()
        self.clips_spin.setRange(1, 40)
        self.clips_spin.setValue(self.cfg.ai_clips)
        form.addRow("Сколько моментов искать", self.clips_spin)
        layout.addWidget(box)

        self.key_hint = QLabel(
            "Ключ хранится зашифрованным средствами Windows (DPAPI) и привязан к вашей "
            "учётной записи. В открытом виде он не сохраняется и в репозиторий не попадает.\n"
            "Без ключа приложение работает: моменты отбираются по эмоциям и громкости.")
        self.key_hint.setObjectName("Muted")
        self.key_hint.setWordWrap(True)
        layout.addWidget(self.key_hint)
        layout.addStretch(1)
        return page

    def _tab_whisper(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.whisper_combo = QComboBox()
        self.whisper_combo.setEditable(True)
        self.whisper_combo.addItems(["large-v3-turbo", "medium", "small", "large-v3"])
        self.whisper_combo.setCurrentText(self.cfg.whisper_model)
        form.addRow("Модель", self.whisper_combo)

        self.device_combo = QComboBox()
        self.device_combo.addItems(["auto", "cuda", "cpu"])
        self.device_combo.setCurrentText(self.cfg.whisper_device)
        form.addRow("Устройство", self.device_combo)

        self.lang_edit = QLineEdit(self.cfg.whisper_language)
        self.lang_edit.setPlaceholderText("ru, en, uk… (пусто — определить самому)")
        form.addRow("Язык речи", self.lang_edit)

        note = QLabel(
            "На видеокартах без поддержки int8/fp16 (например GTX 1060) приложение само "
            "переключится на float32, а если видеокарта не годится — на процессор.")
        note.setObjectName("Muted")
        note.setWordWrap(True)
        form.addRow(note)
        return page

    def _tab_frame(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        form = QFormLayout()
        self.w_spin = QSpinBox(); self.w_spin.setRange(540, 2160); self.w_spin.setSingleStep(2)
        self.w_spin.setValue(self.cfg.canvas_w)
        self.h_spin = QSpinBox(); self.h_spin.setRange(960, 3840); self.h_spin.setSingleStep(2)
        self.h_spin.setValue(self.cfg.canvas_h)
        self.fps_spin = QSpinBox(); self.fps_spin.setRange(24, 60); self.fps_spin.setValue(self.cfg.fps)
        self.face_spin = QSpinBox(); self.face_spin.setRange(240, 1400)
        self.face_spin.setValue(self.cfg.face_height); self.face_spin.setSingleStep(2)
        form.addRow("Ширина холста", self.w_spin)
        form.addRow("Высота холста", self.h_spin)
        form.addRow("Кадров в секунду", self.fps_spin)
        form.addRow("Высота слоя вебки", self.face_spin)
        layout.addLayout(form)

        box = QGroupBox("Титры")
        form2 = QFormLayout(box)
        self.font_edit = QLineEdit(self.cfg.caption_font)
        self.size_spin = QSpinBox(); self.size_spin.setRange(36, 140); self.size_spin.setValue(self.cfg.caption_size)
        self.pop_spin = QSpinBox(); self.pop_spin.setRange(80, 400); self.pop_spin.setValue(self.cfg.pop_size)
        self.color_edit = QLineEdit(self.cfg.caption_color)
        self.hl_edit = QLineEdit(self.cfg.caption_highlight)
        form2.addRow("Шрифт", self.font_edit)
        form2.addRow("Кегль субтитров", self.size_spin)
        form2.addRow("Кегль выкриков", self.pop_spin)
        form2.addRow("Цвет текста (#RRGGBB)", self.color_edit)
        form2.addRow("Цвет подсветки", self.hl_edit)
        layout.addWidget(box)

        self.mute_check = QCheckBox("Глушить мат в звуке")
        self.mute_check.setChecked(self.cfg.mute_profanity)
        layout.addWidget(self.mute_check)
        layout.addStretch(1)
        return page

    def _tab_output(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.out_edit = QLineEdit(self.cfg.output_dir)
        browse = QPushButton("выбрать…")
        browse.clicked.connect(self._pick_dir)
        row = QHBoxLayout(); row.addWidget(self.out_edit, 1); row.addWidget(browse)
        form.addRow("Куда складывать ролики", row)

        self.seg_spin = QSpinBox(); self.seg_spin.setRange(600, 7200); self.seg_spin.setSingleStep(300)
        self.seg_spin.setValue(self.cfg.segment_seconds)
        form.addRow("Длина куска при перепаковке, сек", self.seg_spin)

        self.preview_check = QCheckBox("Собирать готовый mp4 (предпросмотр)")
        self.preview_check.setChecked(self.cfg.make_preview)
        self.capcut_check = QCheckBox("Собирать проект CapCut")
        self.capcut_check.setChecked(self.cfg.make_capcut)
        form.addRow(self.preview_check)
        form.addRow(self.capcut_check)
        return page

    # --- действия ---
    def _pick_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Куда складывать ролики", self.out_edit.text())
        if d:
            self.out_edit.setText(d)

    def _test_key(self) -> None:
        key = self.key_edit.text().strip()
        if not key:
            QMessageBox.warning(self, "Ключ", "Сначала введите ключ DeepSeek.")
            return
        try:
            result = deepseek.ping(key, self.model_combo.currentText(), self.base_edit.text().strip())
            QMessageBox.information(self, "Ключ DeepSeek", result)
        except deepseek.DeepSeekError as e:
            QMessageBox.critical(self, "Ключ DeepSeek", str(e))

    def _save(self) -> None:
        cfg = self.cfg
        cfg.api_key = self.key_edit.text().strip()
        cfg.deepseek_model = self.model_combo.currentText().strip()
        cfg.deepseek_base_url = self.base_edit.text().strip() or "https://api.deepseek.com"
        cfg.ai_clips = self.clips_spin.value()
        cfg.whisper_model = self.whisper_combo.currentText().strip()
        cfg.whisper_device = self.device_combo.currentText()
        cfg.whisper_language = self.lang_edit.text().strip()
        cfg.canvas_w = self.w_spin.value()
        cfg.canvas_h = self.h_spin.value()
        cfg.fps = self.fps_spin.value()
        cfg.face_height = self.face_spin.value()
        cfg.caption_font = self.font_edit.text().strip() or "Arial"
        cfg.caption_size = self.size_spin.value()
        cfg.pop_size = self.pop_spin.value()
        cfg.caption_color = self.color_edit.text().strip() or "#FFFFFF"
        cfg.caption_highlight = self.hl_edit.text().strip() or "#F0FF00"
        cfg.mute_profanity = self.mute_check.isChecked()
        cfg.output_dir = self.out_edit.text().strip()
        cfg.segment_seconds = self.seg_spin.value()
        cfg.make_preview = self.preview_check.isChecked()
        cfg.make_capcut = self.capcut_check.isChecked()
        try:
            cfg.save()
        except OSError as e:
            QMessageBox.critical(self, "Настройки", f"не удалось сохранить: {e}")
            return
        self.accept()
