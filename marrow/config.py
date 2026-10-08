import copy
import os
from pathlib import Path

import yaml

DEFAULTS = {
    "whisper": {
        "model": "auto",
        "device": "auto",
        "compute_type": "int8_float16",
        "language": None,
        "beam_size": 1,
        "batch_size": 8,
        "quality": "fast",
    },
    "llm": {
        "enabled": True,
        "model": "llama3.1:8b",
        "host": "http://localhost:11434",
        "timeout": 120,
        "max_candidates": 24,
        "weight": 0.65,
    },
    "diarization": {"enabled": False, "hf_token": ""},
    "cookies": {"from_browser": "", "cookiefile": ""},
    "clip": {
        "min_duration": 20,
        "max_duration": 60,
        "target_count": 5,
        "pad_start": 0.15,
        "pad_end": 0.35,
    },
    "render": {
        "layout": "crop",
        "encoder": "auto",
        "preset": "fast",
        "crf": 20,
        "fps": 30,
        "loudnorm": True,
    },
    "captions": {
        "enabled": True,
        "preset": "bold-pop",
        "min_gap": 0.22,
        "font": "Arial",
        "bold": True,
        "font_size": 72,
        "uppercase": True,
        "max_words_per_line": 4,
        "max_chars_per_line": 22,
        "text_color": "#FFFFFF",
        "highlight_color": "#FFE600",
        "outline_color": "#000000",
        "outline": 4,
        "shadow": 2,
        "active_scale": 110,
        "emphasis_scale": 125,
        "emphasis_percentile": 85,
    },
    "zoom": {"enabled": False, "max_zoom": 1.12, "speed": 0.0004},
    "platforms": {
        "shorts": {"res_x": 1080, "res_y": 1920, "max_duration": 180, "caption_margin_v": 420},
        "reels": {"res_x": 1080, "res_y": 1920, "max_duration": 90, "caption_margin_v": 460},
    },
    "cache_dir": "work",
}


def deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _load_dotenv(path=".env"):
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_config(path="config.yaml", overrides=None) -> dict:
    _load_dotenv()
    cfg = copy.deepcopy(DEFAULTS)
    p = Path(path)
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            cfg = deep_merge(cfg, yaml.safe_load(f) or {})
    if overrides:
        cfg = deep_merge(cfg, overrides)
    token = os.environ.get("HF_TOKEN")
    if token and not cfg["diarization"].get("hf_token"):
        cfg["diarization"]["hf_token"] = token
    return cfg
