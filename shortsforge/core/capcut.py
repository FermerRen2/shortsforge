"""Экспорт в редактируемый проект CapCut.

Схема черновика CapCut — обычный JSON, но придумывать её с нуля нельзя: редактор молча не
открывает проект, если чего-то не хватает. Поэтому берём шаблон, снятый с проекта, который
CapCut 8.1.1 создал сам (`assets/capcut_template.json`), и наполняем его.

Главное правило, проверенное на практике: каждый слой — ОТДЕЛЬНАЯ дорожка. Если положить игру
и вебку двумя кусками в одну дорожку, CapCut видит мусор, а не два слоя.
"""
from __future__ import annotations

import copy
import json
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

def template_path() -> Path:
    """Шаблон черновика: внутри собранного .exe лежит в распакованных данных."""
    from . import resources

    return resources.asset("capcut_template.json")
US = 1_000_000  # CapCut хранит время в микросекундах


def drafts_root() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft"


def available() -> bool:
    return (drafts_root() / "root_meta_info.json").exists() or drafts_root().exists()


def capcut_running() -> bool:
    import subprocess

    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq CapCut.exe"], capture_output=True,
                         text=True, encoding="cp866", errors="replace")
    return "CapCut.exe" in (out.stdout or "")


def _nid() -> str:
    return str(uuid.uuid4()).upper()


@dataclass
class ClipSpec:
    name: str
    duration: float
    folder: Path                      # где лежат game.mp4 / face.mp4
    captions: list[dict]              # [{start,end,text,highlight}]
    pops: list[dict]                  # [{start,end,text}]
    face_height: int = 608
    canvas_w: int = 1080
    canvas_h: int = 1920
    fps: int = 30


def _text_content(text: str, highlight: str | None, size: float, font_path: str,
                  color: tuple, hl_color: tuple) -> str:
    base = {
        "fill": {"alpha": 1.0, "content": {"render_type": "solid",
                                           "solid": {"alpha": 1.0, "color": list(color)}}},
        "font": {"id": "", "path": font_path},
        "range": [0, len(text)],
        "size": size,
        "strokes": [{"alpha": 1.0, "content": {"render_type": "solid",
                                               "solid": {"alpha": 1.0, "color": [0.0, 0.0, 0.0]}},
                     "width": 0.06}],
        "useLetterColor": True,
    }
    styles = [base]
    if highlight:
        pos = text.find(highlight)
        if pos >= 0:
            hl = copy.deepcopy(base)
            hl["fill"]["content"]["solid"]["color"] = list(hl_color)
            hl["range"] = [pos, pos + len(highlight)]
            styles.append(hl)
    return json.dumps({"styles": styles, "text": text}, ensure_ascii=False)


def build(spec: ClipSpec, override_dir: str | Path | None = None) -> Path:
    """Собирает черновик и регистрирует его в CapCut. Возвращает папку проекта."""
    template = template_path()
    if not template.exists():
        raise RuntimeError("не найден шаблон проекта CapCut (assets/capcut_template.json)")
    root = Path(override_dir) if override_dir else drafts_root()
    draft = json.loads(template.read_text(encoding="utf-8"))

    dur_us = int(round(spec.duration * US))
    font_path = "C:/Windows/Fonts/arialbd.ttf"
    cap_size = 9.0
    pop_size = 22.0
    caption_y = 0.56
    face_y = -((spec.canvas_h / 2 - spec.face_height / 2) / (spec.canvas_h / 2))
    game_h = spec.canvas_h - spec.face_height
    game_y = (game_h / 2) / (spec.canvas_h / 2)

    def video_material(path: Path, w: int, h: int, has_audio: bool) -> str:
        mid = _nid()
        draft["materials"]["videos"].append({
            "id": mid, "type": "video", "path": str(path).replace("\\", "/"),
            "material_name": path.name, "duration": dur_us,
            "width": w, "height": h, "has_audio": has_audio,
            "reverse_path": "", "crop": {"lower_left_x": 0.0, "lower_left_y": 1.0,
                                         "lower_right_x": 1.0, "lower_right_y": 1.0,
                                         "upper_left_x": 0.0, "upper_left_y": 0.0,
                                         "upper_right_x": 1.0, "upper_right_y": 0.0},
            "crop_ratio": "free", "crop_scale": 1.0, "sound_channel_mapping": 0,
            "is_unified_beauty_mode": False, "source": "segmentsourcenormal",
            "source_platform": 0, "video_algorithm": "", "team_id": "",
        })
        return mid

    def video_segment(material_id: str, y: float, render_index: int) -> dict:
        return {
            "id": _nid(), "material_id": material_id,
            "source_timerange": {"start": 0, "duration": dur_us},
            "target_timerange": {"start": 0, "duration": dur_us},
            "render_timerange": {"start": 0, "duration": 0},
            "desc": "", "state": 0, "speed": 1.0, "is_loop": False, "reverse": False,
            "intensifies_audio": False, "cartoon": False, "volume": 1.0,
            "last_nonzero_volume": 1.0,
            "clip": {"scale": {"x": 1.0, "y": 1.0}, "rotation": 0.0,
                     "transform": {"x": 0.0, "y": y}, "flip": {"vertical": False, "horizontal": False},
                     "alpha": 1.0},
            "uniform_scale": {"on": True, "value": 1.0},
            "extra_material_refs": [], "render_index": render_index,
            "keyframe_refs": [], "visible": True, "track_render_index": 0,
            "enable_adjust": False, "enable_color_curves": True, "enable_hsl_curves": True,
            "enable_color_wheels": True, "enable_lut": False, "enable_hsl": False,
            "common_keyframes": [], "source": "segmentsourcenormal",
        }

    def text_material(text: str, size: float, highlight: str | None = None) -> str:
        mid = _nid()
        draft["materials"]["texts"].append({
            "id": mid, "type": "text",
            "content": _text_content(text, highlight, size, font_path,
                                     (1.0, 1.0, 1.0), (0.941, 1.0, 0.0)),
            "font_size": size, "text_size": int(size * 2),
            "text_color": "#FFFFFF", "font_path": font_path,
            "alignment": 1, "line_max_width": 0.82, "line_spacing": 0.02,
            "has_shadow": False, "border_color": "#000000", "border_width": 0.06,
            "words": {"start_time": [], "end_time": [], "text": []},
            "current_words": {"start_time": [], "end_time": [], "text": []},
            "combo_info": {"text_templates": []}, "fonts": [], "language": "",
            "style_name": "", "font_title": "none", "is_rich_text": False,
            "original_size": [], "fixed_width": -1.0, "fixed_height": -1.0,
        })
        return mid

    def text_segment(material_id: str, start: float, dur: float, y: float,
                     render_index: int = 14000) -> dict:
        t0 = int(round(start * US))
        td = max(1, int(round(dur * US)))
        return {
            "id": _nid(), "material_id": material_id,
            "source_timerange": None,
            "target_timerange": {"start": t0, "duration": td},
            "render_timerange": {"start": 0, "duration": 0},
            "desc": "", "state": 0, "speed": 1.0, "is_loop": False, "reverse": False,
            "intensifies_audio": False, "cartoon": False, "volume": 1.0,
            "last_nonzero_volume": 1.0,
            "clip": {"scale": {"x": 1.0, "y": 1.0}, "rotation": 0.0,
                     "transform": {"x": 0.0, "y": y}, "flip": {"vertical": False, "horizontal": False},
                     "alpha": 1.0},
            "uniform_scale": {"on": True, "value": 1.0},
            "extra_material_refs": [], "render_index": render_index,
            "keyframe_refs": [], "visible": True, "track_render_index": 1,
            "enable_adjust": False, "enable_color_curves": True, "enable_hsl_curves": True,
            "enable_color_wheels": True, "common_keyframes": [],
            "source": "segmentsourcenormal",
        }

    game_mat = video_material(spec.folder / "game.mp4", spec.canvas_w, game_h, True)
    face_mat = video_material(spec.folder / "face.mp4", spec.canvas_w, spec.face_height, False)
    draft["tracks"] = [
        {"id": _nid(), "type": "video", "attribute": 0, "flag": 0,
         "is_default_name": True, "name": "основа",
         "segments": [video_segment(game_mat, game_y, 0)]},
        {"id": _nid(), "type": "video", "attribute": 0, "flag": 0,
         "is_default_name": True, "name": "вебка",
         "segments": [video_segment(face_mat, face_y, 1)]},
    ]
    if spec.pops:
        segs = []
        for p in [x for x in spec.pops if x["start"] < spec.duration - 0.2]:
            size = min(pop_size, round(100.0 / max(4, len(p["text"])), 1))
            mat = text_material(p["text"].upper(), size)
            segs.append(text_segment(mat, p["start"], max(0.2, p["end"] - p["start"]), 0.0))
        draft["tracks"].append({"id": _nid(), "type": "text", "attribute": 0, "flag": 0,
                                "is_default_name": True, "name": "выкрики", "segments": segs})
    if spec.captions:
        segs = []
        for c in [x for x in spec.captions if x["start"] < spec.duration - 0.1]:
            mat = text_material(c["text"], cap_size, c.get("highlight"))
            segs.append(text_segment(mat, c["start"], max(0.05, c["end"] - c["start"]), caption_y))
        draft["tracks"].append({"id": _nid(), "type": "text", "attribute": 0, "flag": 0,
                                "is_default_name": True, "name": "субтитры", "segments": segs})

    draft["duration"] = dur_us
    draft["name"] = spec.name
    draft["canvas_config"] = {"width": spec.canvas_w, "height": spec.canvas_h, "ratio": "9:16"}
    draft["fps"] = float(spec.fps)
    draft["create_time"] = int(time.time())
    draft["update_time"] = int(time.time())
    draft["path"] = ""
    draft["id"] = ""

    dst = root / spec.name
    if dst.exists():
        import shutil
        shutil.rmtree(dst)
    dst.mkdir(parents=True, exist_ok=True)
    (dst / "draft_content.json").write_text(
        json.dumps(draft, ensure_ascii=False), encoding="utf-8")

    meta = {
        "draft_name": spec.name, "draft_id": _nid(),
        "draft_fold_path": str(dst).replace("\\", "/"),
        "draft_root_path": str(root).replace("\\", "/"),
        "tm_duration": dur_us, "tm_draft_create": int(time.time() * US),
        "tm_draft_modified": int(time.time() * US), "draft_removable_storage_device": "",
        "draft_materials": [{"type": 0, "value": []}, {"type": 1, "value": []},
                            {"type": 2, "value": []}, {"type": 6, "value": []},
                            {"type": 7, "value": []}, {"type": 8, "value": []}],
        "draft_materials_copied_info": [], "draft_cloud_package_id": "",
        "draft_cloud_last_action_download": False, "draft_cloud_purchase_info": "",
        "draft_cloud_template_id": "", "draft_cloud_tutorial_info": "",
        "draft_cloud_videocut_purchase_info": "", "draft_is_ai_shorts": False,
        "draft_is_invisible": False, "draft_new_version": "",
        "draft_timeline_materials_size": 0, "draft_type": "",
        "draft_cloud_draft_id": "",
    }
    (dst / "draft_meta_info.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                                             encoding="utf-8")

    reg_path = root / "root_meta_info.json"
    reg = {"all_draft_store": [], "draft_ids": 0, "root_path": str(root).replace("\\", "/")}
    if reg_path.exists():
        try:
            reg = json.loads(reg_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    reg["all_draft_store"] = [d for d in reg.get("all_draft_store", [])
                              if d.get("draft_name") != spec.name]
    reg["all_draft_store"].insert(0, {
        "draft_name": spec.name, "draft_id": meta["draft_id"],
        "draft_fold_path": str(dst).replace("\\", "/"),
        "draft_root_path": str(root), "draft_json_file": str(dst / "draft_content.json").replace("\\", "/"),
        "draft_cover": "", "draft_new_version": "", "draft_type": "",
        "draft_is_ai_shorts": False, "draft_is_invisible": False,
        "draft_timeline_materials_size": 0, "streaming_edit_draft_ready": True,
        "tm_draft_create": meta["tm_draft_create"], "tm_draft_modified": meta["tm_draft_modified"],
        "tm_draft_removed": 0, "tm_duration": dur_us,
    })
    reg["draft_ids"] = len(reg["all_draft_store"])
    reg_path.write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")
    return dst


def validate(draft_path: str | Path) -> list[str]:
    """Проверка собранного проекта: целостность ссылок, дорожки, времена."""
    path = Path(draft_path)
    if path.is_dir():
        path = path / "draft_content.json"
    problems: list[str] = []
    try:
        c = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return [f"проект не читается: {e}"]

    ids = {}
    for key, items in c.get("materials", {}).items():
        if isinstance(items, list):
            for m in items:
                if isinstance(m, dict) and "id" in m:
                    ids[m["id"]] = key
    for t in c.get("tracks", []):
        if t.get("type") == "video" and len(t.get("segments", [])) > 1:
            problems.append(f"дорожка «{t.get('name')}»: два куска в одной дорожке")
        prev_end = -1
        for s in t.get("segments", []):
            if s.get("material_id") not in ids:
                problems.append("сегмент ссылается на несуществующий материал")
            for r in s.get("extra_material_refs") or []:
                if r not in ids:
                    problems.append("битая ссылка в extra_material_refs")
            tr = s.get("target_timerange") or {}
            st, du = tr.get("start", 0), tr.get("duration", 0)
            if st < prev_end - 1:
                problems.append("сегменты пересекаются по времени")
            prev_end = st + du
            if st + du > c.get("duration", 0) + 1000:
                problems.append("сегмент выходит за длительность проекта")
    return problems
