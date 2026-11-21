"""Мелкие элементы интерфейса: зона перетаскивания, карточка момента, строка статуса."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout,
                               QWidget)

from . import theme

VIDEO_EXT = {".mp4", ".mkv", ".mov", ".avi", ".ts", ".flv", ".webm", ".m4v", ".mpg", ".mpeg"}


class DropArea(QFrame):
    """Куда бросать видеофайл. Принимает и клик — открывает выбор файла."""

    fileDropped = Signal(str)
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("DropArea")
        self.setAcceptDrops(True)
        self.setMinimumHeight(190)
        self.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(6)

        icon = QLabel("🎬")
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("font-size: 40px;")
        title = QLabel("Перетащите видео или папку с записью")
        title.setAlignment(Qt.AlignCenter)
        title.setObjectName("H2")
        hint = QLabel("mp4, mkv, mov, ts · можно бросать прямо из проводника")
        hint.setAlignment(Qt.AlignCenter)
        hint.setObjectName("Muted")
        layout.addWidget(icon)
        layout.addWidget(title)
        layout.addWidget(hint)

    # --- события ---
    def mousePressEvent(self, event):               # noqa: N802 - метод Qt
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def dragEnterEvent(self, event):                # noqa: N802
        if self._has_video(event.mimeData()):
            event.acceptProposedAction()
            self.setProperty("drag", "true")
            self.style().unpolish(self)
            self.style().polish(self)

    def dragLeaveEvent(self, event):                # noqa: N802
        self.setProperty("drag", "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def dropEvent(self, event):                     # noqa: N802
        self.setProperty("drag", "false")
        self.style().unpolish(self)
        self.style().polish(self)
        path = self._first_video(event.mimeData())
        if path:
            self.fileDropped.emit(path)
            event.acceptProposedAction()

    @staticmethod
    def _has_video(mime) -> bool:
        return bool(DropArea._first_video(mime))

    @staticmethod
    def _first_video(mime) -> str | None:
        if not mime.hasUrls():
            return None
        for url in mime.urls():
            p = Path(url.toLocalFile())
            if p.is_dir():
                for child in sorted(p.iterdir()):
                    if child.suffix.lower() in VIDEO_EXT:
                        return str(child)
            elif p.suffix.lower() in VIDEO_EXT:
                return str(p)
        return None


class MomentCard(QFrame):
    """Карточка момента: кадр, название, отрезок и причина выбора."""

    toggled = Signal(str, bool)

    def __init__(self, data: dict, parent=None):
        super().__init__(parent)
        self.data = data
        self.setObjectName("CardHi" if data.get("selected", True) else "Card")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(92)

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 10, 12, 10)
        row.setSpacing(12)

        cover = QLabel()
        cover.setFixedSize(96, 54)
        cover.setStyleSheet(f"background:#0a0d13; border-radius:8px; border:1px solid {theme.BORDER};")
        cover.setAlignment(Qt.AlignCenter)
        img = data.get("cover") or ""
        if img and Path(img).exists():
            pix = QPixmap(img).scaled(96, 54, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            cover.setPixmap(pix)
        else:
            cover.setText("🎞")
        row.addWidget(cover)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        title = QLabel(data.get("title") or data.get("name") or "Момент")
        title.setObjectName("H2")
        title.setWordWrap(True)
        meta = QLabel(self._meta_text(data))
        meta.setObjectName("Muted")
        reason = QLabel((data.get("reason") or "")[:160])
        reason.setObjectName("Muted")
        reason.setWordWrap(True)
        text_col.addWidget(title)
        text_col.addWidget(meta)
        if data.get("reason"):
            text_col.addWidget(reason)
        row.addLayout(text_col, 1)

        self.pill = QLabel("")
        self._set_pill(data)
        row.addWidget(self.pill, 0, Qt.AlignTop)

    @staticmethod
    def _meta_text(data: dict) -> str:
        start = float(data.get("start", 0))
        end = float(data.get("end", 0))
        return f"{_ts(start)} → {_ts(end)} · {end - start:.0f} с"

    def _set_pill(self, data: dict) -> None:
        checks = data.get("checks") or []
        bad = [c for c in checks if c.get("ok") is False]
        if bad:
            self.pill.setObjectName("BadgeBad")
            self.pill.setText("есть замечания")
        elif checks:
            self.pill.setObjectName("BadgeGood")
            self.pill.setText("проверен")
        elif data.get("source"):
            self.pill.setObjectName("Badge")
            self.pill.setText(str(data["source"])[:14])
        else:
            self.pill.setObjectName("Badge")
            self.pill.setText(f"{data.get('duration', 0):.0f} с")
        self.pill.style().unpolish(self.pill)
        self.pill.style().polish(self.pill)

    def update_data(self, data: dict) -> None:
        self.data = data
        self._set_pill(data)


def _ts(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


class StatusRow(QWidget):
    """Строка «что сейчас происходит» + полоса прогресса."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.label = QLabel("Готов к работе")
        self.label.setObjectName("Muted")
        self.label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout.addWidget(self.label, 1)

    def set_text(self, text: str) -> None:
        self.label.setText(text)


def badge(text: str, kind: str = "normal") -> QLabel:
    label = QLabel(text)
    label.setObjectName({"good": "BadgeGood", "bad": "BadgeBad"}.get(kind, "Badge"))
    return label


def monospace(text: str) -> QLabel:
    label = QLabel(text)
    font = QFont("Cascadia Mono")
    font.setStyleHint(QFont.Monospace)
    label.setFont(font)
    return label
