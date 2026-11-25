"""Оформление: тёмная тема, свои скругления, градиентный акцент.

Стилизация сделана своим QSS, без сторонних тем: так приложение не зависит от чужих пакетов
и одинаково выглядит на любой машине. Палитра: глубокий графит, фиолетово-бирюзовый акцент.
"""

BG = "#0b0d12"
PANEL = "#121620"
CARD = "#171b26"
CARD_HI = "#1e2431"
BORDER = "#252c3a"
TEXT = "#e8ecf4"
MUTED = "#8b94a7"
ACCENT = "#7c5cff"
ACCENT2 = "#22d3a8"
DANGER = "#ff5d73"
WARN = "#ffc857"

FONT = "Inter"
FALLBACK_FONT = "Segoe UI"


def load_fonts() -> str:
    """Подключает шрифт Inter из assets/fonts. Возвращает имя семейства, которое реально есть."""
    from PySide6.QtGui import QFontDatabase

    from ..core import resources

    families = set(QFontDatabase.families())
    if FONT in families:
        return FONT
    fonts_dir = resources.asset("fonts")
    loaded = False
    if fonts_dir.exists():
        for ttf in sorted(fonts_dir.glob("*.ttf")):
            if QFontDatabase.addApplicationFont(str(ttf)) >= 0:
                loaded = True
    families = set(QFontDatabase.families())
    if loaded and FONT in families:
        return FONT
    return FALLBACK_FONT


def stylesheet(font: str | None = None) -> str:
    family = font or FONT
    return f"""
* {{
    font-family: "{family}", "{FALLBACK_FONT}", sans-serif;
    font-size: 14px;
    color: {TEXT};
}}
QWidget#Root {{
    background: {BG};
}}
QDialog {{
    background: {BG};
}}
QGroupBox {{
    border: 1px solid {BORDER};
    border-radius: 12px;
    margin-top: 16px;
    padding: 10px 12px 6px 12px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 14px;
    padding: 0 6px;
    color: {MUTED};
}}
QFrame#Sidebar {{
    background: {PANEL};
    border-right: 1px solid {BORDER};
}}
QFrame#Card {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 14px;
}}
QFrame#CardHi {{
    background: {CARD_HI};
    border: 1px solid {BORDER};
    border-radius: 14px;
}}
QFrame#DropArea {{
    background: {CARD};
    border: 2px dashed #33405a;
    border-radius: 18px;
}}
QFrame#DropArea[drag="true"] {{
    border: 2px dashed {ACCENT2};
    background: #16202a;
}}
QLabel#Logo {{
    font-size: 24px;
    font-weight: 800;
    letter-spacing: 1px;
}}
QLabel#Tagline {{
    color: {MUTED};
    font-size: 12px;
    letter-spacing: 0.3px;
}}
QLabel#Section {{
    color: #5c6678;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1.4px;
}}
QLabel#Empty {{
    color: {MUTED};
    font-size: 15px;
    line-height: 1.5;
}}
QLabel#H1 {{
    font-size: 21px;
    font-weight: 700;
}}
QLabel#H2 {{
    font-size: 15px;
    font-weight: 600;
}}
QLabel#Muted {{
    color: {MUTED};
}}
QLabel#Badge {{
    background: {CARD_HI};
    border: 1px solid {BORDER};
    border-radius: 9px;
    padding: 3px 9px;
    color: {MUTED};
    font-size: 12px;
}}
QLabel#BadgeGood {{
    background: #10312a;
    border: 1px solid #1d5f4d;
    border-radius: 9px;
    padding: 3px 9px;
    color: {ACCENT2};
    font-size: 12px;
}}
QLabel#BadgeBad {{
    background: #34141b;
    border: 1px solid #6b2233;
    border-radius: 9px;
    padding: 3px 9px;
    color: {DANGER};
    font-size: 12px;
}}
QPushButton {{
    background: {CARD_HI};
    border: 1px solid {BORDER};
    border-radius: 11px;
    padding: 10px 18px;
    font-weight: 600;
    min-height: 18px;
}}
QPushButton:hover {{
    background: #263041;
    border-color: #35415a;
}}
QPushButton:pressed {{
    background: #1b2230;
}}
QPushButton:disabled {{
    color: #5a6377;
    background: #141821;
    border-color: #1d2330;
}}
QPushButton#Primary {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                stop:0 {ACCENT}, stop:1 #4f7bff);
    border: none;
    color: white;
    padding: 12px 24px;
    font-weight: 700;
}}
QPushButton#Primary:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                stop:0 #8b6dff, stop:1 #6188ff);
}}
QPushButton#Primary:disabled {{
    background: #2a2f45;
    color: #6d7691;
}}
QPushButton#Ghost {{
    background: transparent;
    border: 1px solid {BORDER};
    color: {MUTED};
}}
QPushButton#Ghost:hover {{
    color: {TEXT};
    border-color: #3a4560;
}}
QPushButton#Nav {{
    background: transparent;
    border: none;
    border-left: 3px solid transparent;
    border-radius: 10px;
    padding: 11px 14px;
    text-align: left;
    color: {MUTED};
    font-weight: 600;
}}
QPushButton#Nav:hover {{
    background: #1a1f2b;
    color: {TEXT};
}}
QPushButton#Nav:checked {{
    background: #1d2434;
    color: {TEXT};
    border-left: 3px solid {ACCENT};
}}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTextEdit {{
    background: #0f131b;
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 8px 10px;
    selection-background-color: {ACCENT};
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus {{
    border-color: {ACCENT};
}}
QComboBox::drop-down {{
    border: none;
    width: 22px;
}}
QComboBox QAbstractItemView {{
    background: {CARD};
    border: 1px solid {BORDER};
    selection-background-color: #263041;
    outline: none;
}}
QCheckBox {{
    spacing: 8px;
}}
QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border-radius: 5px;
    border: 1px solid #38445c;
    background: #0f131b;
}}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
}}
QProgressBar {{
    background: #0f131b;
    border: 1px solid {BORDER};
    border-radius: 8px;
    height: 10px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    border-radius: 7px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                stop:0 {ACCENT2}, stop:1 {ACCENT});
}}
QListWidget, QTableWidget {{
    background: transparent;
    border: none;
    outline: none;
}}
QListWidget::item {{
    border-radius: 12px;
    margin: 4px 2px;
}}
QListWidget::item:selected {{
    background: #1d2434;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: #2c3546;
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: #3a4660;
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
}}
QScrollBar::handle:horizontal {{
    background: #2c3546;
    border-radius: 5px;
}}
QPlainTextEdit#Log {{
    font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: 12px;
    color: #9fb0c9;
    background: #0a0d13;
    border: 1px solid {BORDER};
    border-radius: 12px;
}}
QToolTip {{
    background: {CARD_HI};
    border: 1px solid {BORDER};
    color: {TEXT};
    padding: 6px;
    border-radius: 8px;
}}
QTabWidget::pane {{
    border: 1px solid {BORDER};
    border-radius: 14px;
    background: {CARD};
}}
QTabBar::tab {{
    background: transparent;
    color: {MUTED};
    padding: 9px 16px;
    margin-right: 4px;
    border-radius: 9px;
}}
QTabBar::tab:selected {{
    background: #1d2434;
    color: {TEXT};
}}
QSplitter::handle {{
    background: transparent;
    width: 10px;
}}
"""
