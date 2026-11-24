"""Кэш по файлу: второй запуск на той же записи не пересчитывает ничего заново.

Ключ кэша — имя файла, размер и время изменения: если запись не менялась, значит и профиль
громкости, и расшифровка, и найденные моменты те же. Лежит в `%LOCALAPPDATA%\\ShortsForge\\cache`.

Почему по файлу, а не по проекту: рабочие папки чистят, а запись остаётся. Кэш переживает
удаление проекта и делает повторный прогон мгновенным.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path


def cache_root() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home())
    root = base / "ShortsForge" / "cache"
    root.mkdir(parents=True, exist_ok=True)
    return root


def file_key(path: str | Path) -> str:
    """Отпечаток файла: путь + размер + время изменения (меняется — кэш недействителен)."""
    p = Path(path).resolve()
    try:
        st = p.stat()
        raw = f"{p}|{st.st_size}|{int(st.st_mtime)}"
    except OSError:
        raw = str(p)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


class FileCache:
    """Хранилище промежуточных результатов для одной записи."""

    def __init__(self, video: str | Path):
        self.video = Path(video)
        self.key = file_key(self.video)
        self.dir = cache_root() / self.key
        self.dir.mkdir(parents=True, exist_ok=True)
        self.meta_path = self.dir / "meta.json"

    # --- служебное ---
    def save_meta(self, **extra) -> None:
        data = {"video": str(self.video), "key": self.key}
        data.update(extra)
        try:
            self.meta_path.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                                      encoding="utf-8")
        except OSError:
            pass

    def describe(self) -> str:
        """Что уже посчитано — для подсказки в интерфейсе."""
        parts = []
        for name, label in (("loudness.json", "громкость"), ("words.json", "расшифровка"),
                            ("candidates.json", "моменты"), ("webcam.json", "окно вебки"),
                            ("chat.json", "чат")):
            if (self.dir / name).exists():
                parts.append(label)
        if not any(p.endswith("расшифровка") for p in parts) and list(self.dir.glob("words_*.json")):
            parts.append("расшифровка")
        return (", ".join(parts)) if parts else "пусто"

    def size_mb(self) -> float:
        total = sum(f.stat().st_size for f in self.dir.glob("*") if f.is_file())
        return total / (1024 * 1024)

    # --- чтение и запись ---
    def get(self, name: str):
        path = self.dir / name
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def put(self, name: str, data) -> None:
        try:
            (self.dir / name).write_text(json.dumps(data, ensure_ascii=False),
                                         encoding="utf-8")
        except OSError:
            pass

    # --- конкретные данные ---
    def get_words(self, mode: str = "fast") -> list | None:
        data = self.get(f"words_{mode}.json")
        if data is None and mode == "fast":
            data = self.get("words.json")
        return data

    def put_words(self, words: list, mode: str = "fast") -> None:
        self.put(f"words_{mode}.json", [[round(w.start, 2), round(w.end, 2), w.text] for w in words])

    def get_loudness(self) -> list | None:
        return self.get("loudness.json")

    def put_loudness(self, levels: list) -> None:
        self.put("loudness.json", levels)

    def clear(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)


def forget_all() -> int:
    """Удаляет весь кэш. Возвращает, сколько папок удалено."""
    root = cache_root()
    count = 0
    for child in root.iterdir():
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
            count += 1
    return count
