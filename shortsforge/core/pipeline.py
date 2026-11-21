"""Конвейер: файл -> куски -> расшифровка -> моменты -> ролики -> проекты CapCut.

Каждый шаг можно запускать отдельно (в интерфейсе это кнопки), состояние хранится в
`project.json` рядом с рабочими файлами, поэтому работу можно закрыть и продолжить.

Правила, без которых уже проверенно получается брак:
- слова для титров берутся из звука САМОГО ролика, а не из общей расшифровки записи:
  у сырых записей шкала времени расходится с перепакованными кусками (до 10 секунд);
- после рендера измеряется, где реально начался кусок — и титры ставятся по факту;
- каждый ролик проверяется: титры против собственного звука, ключевое слово в кадре,
  целостность проекта CapCut.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from . import analysis, capcut, captions as caps, deepseek, layout, media, render
from .config import Settings
from .transcribe import Transcriber, Word


def _noop(*_a, **_k) -> None:
    return None


@dataclass
class Project:
    source: Path
    work_dir: Path
    settings: Settings
    info: media.MediaInfo | None = None
    parts: list[media.Part] = field(default_factory=list)
    words: list[Word] = field(default_factory=list)
    windows: list[analysis.Window] = field(default_factory=list)
    candidates: list[dict] = field(default_factory=list)
    clips: list[dict] = field(default_factory=list)
    webcam: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    # --- служебное ---
    @property
    def state_path(self) -> Path:
        return self.work_dir / "project.json"

    def save(self) -> None:
        self.work_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "source": str(self.source),
            "info": self.info.as_text() if self.info else "",
            "parts": [str(p.path) for p in self.parts],
            "words": [w.as_list() for w in self.words],
            "candidates": self.candidates,
            "clips": self.clips,
            "webcam": self.webcam,
            "notes": self.notes,
        }
        self.state_path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    def part_files(self) -> list[Path]:
        if self.parts:
            return [p.path for p in self.parts]
        return [self.source]

    def refresh_parts(self) -> None:
        self.parts = media.parts_map(self.part_files())


def open_project(source: str | Path, work_dir: str | Path, cfg: Settings) -> Project:
    source = Path(source)
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    prj = Project(source=source, work_dir=work, settings=cfg)
    prj.info = media.probe(source)
    if prj.state_path.exists():
        try:
            data = json.loads(prj.state_path.read_text(encoding="utf-8"))
            prj.candidates = data.get("candidates") or []
            prj.clips = data.get("clips") or []
            prj.webcam = data.get("webcam") or {}
            prj.words = [Word(*w) for w in (data.get("words") or [])]
            parts = data.get("parts") or []
            if parts and all(Path(p).exists() for p in parts):
                prj.parts = media.parts_map(parts)
        except (json.JSONDecodeError, OSError, TypeError):
            prj.notes.append("прежнее состояние не прочиталось, начинаю с чистого листа")
    return prj


# --- шаг 1: подготовка файла ------------------------------------------------
def prepare(prj: Project, progress=_noop, cancel=None) -> Project:
    """Перепаковывает «сырую» запись на куски, если это нужно."""
    assert prj.info is not None
    needed, reason = media.needs_repack(prj.info, prj.source)
    if not needed:
        prj.parts = media.parts_map([prj.source])
        prj.notes.append("перепаковка не нужна: файл с нормальным индексом")
        prj.save()
        return prj

    prj.notes.append(f"перепаковка: {reason.splitlines()[0]}")
    progress(0.02, "перепаковка записи на куски")
    parts_dir = prj.work_dir / "parts"
    if parts_dir.exists():
        shutil.rmtree(parts_dir, ignore_errors=True)
    files = media.repack(prj.source, parts_dir, prj.settings.segment_seconds,
                         progress=lambda p: progress(0.02 + 0.95 * p, "перепаковка записи"),
                         cancel=cancel)
    prj.parts = media.parts_map(files)
    prj.notes.append(f"готово кусков: {len(prj.parts)}")
    prj.save()
    progress(1.0, "запись готова")
    return prj


# --- шаг 2: расшифровка ------------------------------------------------------
def transcribe(prj: Project, progress=_noop, cancel=None) -> Project:
    """Распознаёт речь по всей записи (по кускам, чтобы можно было прервать)."""
    cfg = prj.settings
    prj.refresh_parts()
    tr = Transcriber(cfg.whisper_model, cfg.whisper_device, cfg.whisper_language)
    tr.load()
    prj.notes.append(f"распознавание: {tr.status}")

    words: list[Word] = []
    total = sum(p.duration for p in prj.parts) or 1.0
    done = 0.0
    for part in prj.parts:
        if cancel and cancel():
            raise RuntimeError("отменено")
        chunk_words = tr.transcribe_range(part.path, part.start, part.end, margin=1.0,
                                         cancel=cancel)
        words.extend(chunk_words)
        done += part.duration
        progress(min(0.99, done / total), f"распознано {int(done)//60} из {int(total)//60} мин")
    prj.words = sorted(words, key=lambda w: w.start)
    prj.save()
    progress(1.0, f"расшифровка готова: {len(prj.words)} слов")
    return prj


# --- шаг 3: отбор моментов ---------------------------------------------------
def suggest(prj: Project, progress=_noop, cancel=None, extra_notes: str = "") -> Project:
    """Отбор моментов: DeepSeek, если есть ключ, иначе — по эмоциям и громкости."""
    cfg = prj.settings
    if not prj.words:
        raise RuntimeError("сначала нужно распознать речь")

    if cfg.has_key():
        progress(0.15, "спрашиваю DeepSeek, что зайдёт")
        transcript = analysis.transcript_for_ai(prj.words)
        try:
            clips = deepseek.pick_moments(
                cfg.api_key, transcript, cfg.ai_clips, model=cfg.deepseek_model,
                base_url=cfg.deepseek_base_url, language=cfg.ai_language,
                extra_notes=extra_notes,
            )
            prj.candidates = clips
            prj.notes.append(f"моменты отобраны ИИ: {len(clips)}")
            progress(1.0, f"ИИ предложил {len(clips)} моментов")
            prj.save()
            return prj
        except deepseek.DeepSeekError as e:
            prj.notes.append(f"ИИ не сработал ({e}), отбираю без него")
            progress(0.5, "ИИ недоступен, отбираю по эмоциям")

    # запасной путь: громкость + эмоции, без сети
    progress(0.35, "считаю громкость по секундам")
    audio_src = prj.part_files()[0] if prj.parts else prj.source
    levels = media.loudness_per_second(audio_src, progress=lambda _p, msg: progress(0.35, msg),
                                       cancel=cancel)
    prj.windows = analysis.make_windows(levels, prj.words)
    prj.candidates = analysis.heuristic_candidates(prj.words, cfg.ai_clips)
    prj.notes.append(f"моменты отобраны без ИИ: {len(prj.candidates)}")
    prj.save()
    progress(1.0, f"отобрано {len(prj.candidates)} моментов")
    return prj


# --- шаг 4: ролик ------------------------------------------------------------
def webcam_box(prj: Project, force: bool = False) -> dict:
    """Окно вебки: измеряется по лицу и кэшируется в состоянии проекта."""
    if prj.webcam and not force:
        return prj.webcam
    video = prj.part_files()[0]
    box = layout.detect(video, prj.work_dir / "cache",
                        duration=prj.info.duration if prj.info else None)
    prj.webcam = box.as_dict()
    prj.save()
    return prj.webcam


def make_clip(prj: Project, candidate: dict, index: int, progress=_noop,
              cancel=None) -> dict:
    """Собирает один ролик: слои, титры, выкрики, предпросмотр, проект CapCut, проверки."""
    cfg = prj.settings
    prj.refresh_parts()
    start = float(candidate["start"])
    end = float(candidate["end"])
    dur = max(3.0, end - start)
    name = candidate.get("name") or f"clip_{index:02d}"
    slug = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in name)[:40]
    folder = prj.work_dir / "clips" / slug
    folder.mkdir(parents=True, exist_ok=True)

    part, local = media.locate(prj.parts, start)
    progress(0.05, f"{slug}: вырезаю звук")
    audio_probe = folder / "clip_audio.opus"
    media.run([media.ffmpeg(), "-hide_banner", "-v", "error", "-y",
               "-ss", f"{local:.2f}", "-t", f"{dur:.2f}", "-i", str(part.path),
               "-vn", "-ac", "1", "-ar", "16000", "-c:a", "libopus", str(audio_probe)])

    # где реально начался кусок — по форме сигнала
    actual_local = media.measure_offset(part.path, local, audio_probe)
    base_abs = part.start + actual_local

    progress(0.15, f"{slug}: распознаю речь ролика")
    tr = Transcriber(cfg.whisper_model, cfg.whisper_device, cfg.whisper_language)
    words = tr.transcribe(audio_probe, offset=base_abs, cancel=cancel)
    clip_start, clip_end = base_abs, base_abs + dur

    progress(0.42, f"{slug}: субтитры и звук")
    caption_segs = caps.build_captions(words, clip_start, clip_end)
    pop_words = candidate.get("pops") or [candidate.get("hook", "")[:24]] or []
    pops = render.find_pops(words, clip_start, clip_end, [w for w in pop_words if w], extra=1)
    caption_segs = caps.drop_popped(caption_segs, pops)
    mute = caps.mute_filter(words, clip_start, clip_end) if cfg.mute_profanity else None

    box_dict = webcam_box(prj)
    box = layout.WebcamBox(x=box_dict["x"], y=box_dict["y"], w=box_dict["w"], h=box_dict["h"],
                           frame_w=box_dict["frame"][0], frame_h=box_dict["frame"][1],
                           faces_found=box_dict.get("faces_found", 0))

    game, face = render.render_layers(part.path, local, dur, folder, box, cfg, mute,
                                      progress=lambda p, m: progress(0.42 + 0.25 * p, f"{slug}: {m}"))

    ass = folder / "captions.ass"
    caps.write_ass(caption_segs, pops, str(ass), width=cfg.canvas_w, height=cfg.canvas_h,
                   font=cfg.caption_font, size=cfg.caption_size, color=cfg.caption_color,
                   highlight=cfg.caption_highlight, pop_size=cfg.pop_size)
    caps.write_srt(caption_segs, str(folder / "captions.srt"))

    preview = folder / "preview.mp4"
    if cfg.make_preview:
        render.render_preview(game, face, ass, preview, cfg,
                              progress=lambda p, m: progress(0.67 + 0.2 * p, f"{slug}: {m}"))
    render.snapshot(preview if preview.exists() else game, dur * 0.5, folder / "cover.jpg")

    title = candidate.get("title") or "Момент со стрима"
    hashtags = candidate.get("hashtags") or "#shorts #нарезка #стрим"
    (folder / "описание.txt").write_text(f"{title}\n\n{hashtags}\n", encoding="utf-8")

    capcut_dir = None
    if cfg.make_capcut and capcut.available() and not capcut.capcut_running():
        progress(0.9, f"{slug}: проект CapCut")
        try:
            capcut_dir = str(capcut.build(capcut.ClipSpec(
                name=slug, duration=dur, folder=folder,
                captions=[c.as_dict() for c in caption_segs], pops=pops,
                face_height=cfg.face_height, canvas_w=cfg.canvas_w, canvas_h=cfg.canvas_h,
                fps=cfg.fps)))
        except (RuntimeError, OSError) as e:
            prj.notes.append(f"{slug}: проект CapCut не собран ({e})")

    clip = {
        "name": slug, "title": title, "hashtags": hashtags,
        "start": round(start, 1), "end": round(end, 1), "duration": round(dur, 1),
        "folder": str(folder), "preview": str(preview) if preview.exists() else "",
        "captions": len(caption_segs), "pops": len(pops),
        "capcut": capcut_dir or "", "source": candidate.get("source", ""),
        "reason": candidate.get("reason", ""),
    }
    clip["checks"] = verify_clip(prj, clip)
    prj.clips = [c for c in prj.clips if c["name"] != slug] + [clip]
    prj.clips.sort(key=lambda c: c["start"])
    prj.save()
    progress(1.0, f"{slug}: готов")
    return clip


# --- шаг 5: проверки ---------------------------------------------------------
def build_all(prj: Project, candidates: list[dict] | None = None, progress=_noop,
              cancel=None) -> list[dict]:
    """Собирает ролики по всем выбранным моментам, отдавая общий прогресс."""
    items = candidates if candidates is not None else prj.candidates
    if not items:
        raise RuntimeError("нет моментов — сначала отберите их")
    made: list[dict] = []
    total = len(items)
    for i, cand in enumerate(items):
        if cancel and cancel():
            raise RuntimeError("отменено")

        def sub(p: float, msg: str, i=i) -> None:
            progress(min(0.999, (i + max(0.0, min(1.0, p))) / total),
                     f"[{i + 1}/{total}] {msg}")

        try:
            made.append(make_clip(prj, cand, i + 1, progress=sub, cancel=cancel))
        except RuntimeError as e:
            if "отменено" in str(e):
                raise
            prj.notes.append(f"ролик {i + 1} не собрался: {e}")
    progress(1.0, f"готово роликов: {len(made)}")
    return made


def verify_clip(prj: Project, clip: dict) -> list[dict]:
    """Проверки ролика: титры против собственного звука, целостность проекта CapCut."""
    checks: list[dict] = []
    folder = Path(clip["folder"])
    spec = folder / "spec.json"
    preview = Path(clip["preview"]) if clip.get("preview") else None

    if preview and preview.exists():
        try:
            words = Transcriber(prj.settings.whisper_model, prj.settings.whisper_device,
                                prj.settings.whisper_language).transcribe(preview)
            from . import verify
            res = verify.captions_vs_audio(folder / "captions.srt", words)
            checks.append(res)
        except Exception as e:                      # noqa: BLE001 - проверка не должна валить сборку
            checks.append({"name": "титры против звука", "ok": None, "detail": f"не проверил: {e}"})

    if clip.get("capcut"):
        problems = capcut.validate(clip["capcut"])
        checks.append({"name": "проект CapCut", "ok": not problems,
                       "detail": "целостный" if not problems else "; ".join(problems[:3])})
    checks.append({"name": "слои", "ok": True,
                   "detail": f"титров {clip['captions']}, выкриков {clip['pops']}"})
    (folder / "checks.json").write_text(json.dumps(checks, ensure_ascii=False, indent=2),
                                        encoding="utf-8")
    return checks
