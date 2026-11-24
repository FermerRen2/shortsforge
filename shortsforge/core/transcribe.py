"""Распознавание речи: faster-whisper на видеокарте, с честным откатом на процессор.

Грабли, проверенные на GTX 1060 (compute 6.1): `int8` и `float16` ctranslate2 отвергает —
работает только `float32`. Поэтому режим подбирается сам: пробуем cuda+float32, при ошибке
идём на cpu+int8. Плюс DLL от CUDA-колёс pip не подхватываются сами — их нужно подключить
через `os.add_dll_directory`, иначе падение с `cublas64_12.dll is not found`.
"""
from __future__ import annotations

import os
import site
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


def add_cuda_dlls() -> list[str]:
    r"""Подключает DLL CUDA (Windows): рядом с приложением, в папке данных или из pip-колёс.

    Без этого faster-whisper падает с `cublas64_12.dll is not found`, даже когда библиотеки
    установлены: pip кладёт их в site-packages\nvidia\*, а загрузчик Windows туда не смотрит.
    """
    if sys.platform != "win32":
        return []
    from . import resources

    added: list[str] = []
    for d in resources.cuda_dirs():
        path = str(d)
        try:
            os.add_dll_directory(path)
        except OSError:
            pass
        os.environ["PATH"] = path + os.pathsep + os.environ.get("PATH", "")
        added.append(path)
    return added


@dataclass
class Word:
    start: float
    end: float
    text: str

    def as_list(self) -> list:
        return [round(self.start, 2), round(self.end, 2), self.text]


class Transcriber:
    """Обёртка над faster-whisper с автоподбором устройства."""

    def __init__(self, model_name: str = "large-v3-turbo", device: str = "auto",
                 language: str = "ru"):
        self.model_name = model_name
        self.device_pref = device
        self.language = language
        self._model = None
        self.device = ""
        self.compute_type = ""
        self._fallback_reason = ""

    # --- загрузка ---
    def load(self) -> None:
        if self._model is not None:
            return
        try:
            from faster_whisper import WhisperModel
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("не установлен faster-whisper: pip install faster-whisper") from e

        add_cuda_dlls()
        attempts: list[tuple[str, str]] = []
        if self.device_pref in ("auto", "cuda"):
            attempts.append(("cuda", "float32"))
        if self.device_pref in ("auto", "cpu"):
            attempts.append(("cpu", "int8"))
        last_error: Exception | None = None
        for device, ctype in attempts:
            try:
                self._model = WhisperModel(self.model_name, device=device, compute_type=ctype)
                self.device, self.compute_type = device, ctype
                return
            except Exception as e:                      # noqa: BLE001 - нужен любой отказ
                last_error = e
                self._fallback_reason = f"{device}/{ctype}: {e}"
        raise RuntimeError(f"не удалось загрузить модель распознавания: {last_error}")

    @property
    def status(self) -> str:
        if self._model is None:
            return "не загружена"
        return f"{self.model_name} · {self.device}/{self.compute_type}"

    # --- распознавание ---
    def transcribe(self, audio: str | Path, offset: float = 0.0, progress=None,
                   cancel=None) -> list[Word]:
        """Слова с таймкодами. `offset` добавляется к времени — так слова сразу в шкале записи."""
        self.load()
        assert self._model is not None
        segments, info = self._model.transcribe(
            str(audio),
            language=self.language or None,
            vad_filter=False,          # с VAD время «сжимается» и титры уезжают
            word_timestamps=True,
            beam_size=1,
            condition_on_previous_text=False,
        )
        words: list[Word] = []
        total = float(getattr(info, "duration", 0) or 0)
        for seg in segments:
            if cancel and cancel():
                raise RuntimeError("отменено")
            for w in seg.words or []:
                text = (w.word or "").strip()
                if text:
                    words.append(Word(w.start + offset, w.end + offset, text))
            if progress and total:
                progress(min(0.99, (seg.end or 0) / total))
        if progress:
            progress(1.0)
        return words

    def transcribe_range(self, video: str | Path, start: float, end: float,
                         margin: float = 6.0, progress=None, cancel=None) -> list[Word]:
        """Слова для отрезка [start, end] записи — со звука самого отрезка."""
        from . import media

        dur = max(0.5, end - start)
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td) / "slice.opus"
            media.run([media.ffmpeg(), "-hide_banner", "-v", "error", "-y",
                       "-ss", f"{max(0.0, start - margin):.2f}",
                       "-t", f"{dur + margin * 2:.2f}", "-i", str(video),
                       "-vn", "-ac", "1", "-ar", "16000", "-c:a", "libopus", str(tmp)])
            return self.transcribe(tmp, offset=max(0.0, start - margin),
                                   progress=progress, cancel=cancel)

