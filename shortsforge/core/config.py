"""Настройки приложения и хранение ключа DeepSeek.

Ключ не лежит в открытом виде: он шифруется средствами Windows (DPAPI, CryptProtectData) и
привязан к учётной записи, под которой работает приложение. Скопировать файл настроек на другую
машину и воспользоваться ключом не получится. Токен DeepSeek, взятый из переменной окружения
`DEEPSEEK_API_KEY`, имеет приоритет — так удобно для запуска из консоли.
"""
from __future__ import annotations

import base64
import ctypes
import ctypes.wintypes as wt
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

APP_NAME = "ShortsForge"


def app_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    d = Path(base) / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


# --- DPAPI ------------------------------------------------------------------
class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _protect(data: bytes) -> bytes:
    if os.name != "nt":
        return b"plain:" + data
    blob_in = _Blob(len(data), ctypes.cast(ctypes.create_string_buffer(data), ctypes.POINTER(ctypes.c_char)))
    blob_out = _Blob()
    ok = ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(blob_in), f"{APP_NAME} key", None, None, None, 0, ctypes.byref(blob_out)
    )
    if not ok:
        raise OSError("CryptProtectData failed")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def _unprotect(data: bytes) -> bytes:
    if os.name != "nt":
        return data.replace(b"plain:", b"", 1)
    blob_in = _Blob(len(data), ctypes.cast(ctypes.create_string_buffer(data), ctypes.POINTER(ctypes.c_char)))
    blob_out = _Blob()
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
    )
    if not ok:
        raise OSError("CryptUnprotectData failed")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


# --- настройки --------------------------------------------------------------
@dataclass
class Settings:
    """Всё, что можно менять в окне настроек."""

    output_dir: str = field(default_factory=lambda: str(Path.home() / "Videos" / "ShortsForge"))
    caps_dir: str = ""

    # ИИ
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com"
    ai_clips: int = 12
    ai_language: str = "ru"

    # распознавание
    whisper_model: str = "large-v3-turbo"
    whisper_device: str = "auto"          # auto | cuda | cpu
    whisper_language: str = "ru"

    # кадр
    canvas_w: int = 1080
    canvas_h: int = 1920
    fps: int = 30
    face_height: int = 608                # высота слоя вебки на холсте
    caption_font: str = "Arial"
    caption_size: int = 72
    caption_color: str = "#FFFFFF"
    caption_highlight: str = "#F0FF00"
    pop_size: int = 230
    mute_profanity: bool = True
    censor_titles: bool = True

    # вывод
    make_preview: bool = True
    make_capcut: bool = True
    recent_files: list = field(default_factory=list)
    segment_seconds: int = 3600

    _path: str = ""

    # --- хранение ---
    @classmethod
    def load(cls, path: str | Path | None = None) -> "Settings":
        path = Path(path) if path else app_dir() / "config.json"
        data = {}
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                data = {}
        key_blob = data.pop("_api_key", "")
        obj = cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        obj._path = str(path)
        if key_blob:
            try:
                obj._api_key = _unprotect(base64.b64decode(key_blob)).decode("utf-8")
            except Exception:
                obj._api_key = ""
        else:
            obj._api_key = ""
        return obj

    _api_key: str = ""

    def save(self) -> None:
        data = {k: v for k, v in asdict(self).items() if not k.startswith("_")}
        if self._api_key:
            data["_api_key"] = base64.b64encode(_protect(self._api_key.encode("utf-8"))).decode()
        path = Path(self._path) if self._path else app_dir() / "config.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        self._path = str(path)

    # --- ключ ---
    @property
    def api_key(self) -> str:
        return (os.environ.get("DEEPSEEK_API_KEY") or self._api_key).strip()

    @api_key.setter
    def api_key(self, value: str) -> None:
        self._api_key = (value or "").strip()

    def has_key(self) -> bool:
        return bool(self.api_key)

    def masked_key(self) -> str:
        k = self.api_key
        if not k:
            return "не задан"
        return f"{k[:6]}…{k[-4:]}" if len(k) > 12 else "задан"


settings: Settings | None = None


def get() -> Settings:
    """Единственный экземпляр настроек."""
    global settings
    if settings is None:
        settings = Settings.load()
    return settings
