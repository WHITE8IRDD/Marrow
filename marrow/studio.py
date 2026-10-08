"""Helpers for re-rendering a single clip (trim, caption edits) from cached pipeline data.

Kept free of heavy imports (no librosa/faster-whisper) so the UI server starts fast.
"""
import json
import os
from pathlib import Path

import numpy as np

from .models import Word
from .utils import run_ffmpeg

ENERGY_FPS = 16000 / 512  # must match audio_features.HOP / sample rate


def load_words(workdir):
    raw = json.loads((Path(workdir) / "words.json").read_text(encoding="utf-8"))
    return [Word(s, e, t) for s, e, t in raw["words"]], raw


def words_in_range(raw, start, end):
    """Indices + data of cached words overlapping [start, end]."""
    out = []
    for i, (s, e, t) in enumerate(raw["words"]):
        if e > start and s < end:
            out.append({"i": i, "t": t, "s": round(s, 2), "e": round(e, 2)})
    return out


def apply_edits(workdir, raw, edits):
    """Persist corrected caption text into the cached transcript. Returns number changed."""
    n = len(raw["words"])
    changed = 0
    for key, value in (edits or {}).items():
        try:
            i = int(key)
        except (TypeError, ValueError):
            continue
        text = str(value).strip()
        if not (0 <= i < n) or not text or len(text) > 40 or raw["words"][i][2] == text:
            continue
        raw["words"][i][2] = text
        changed += 1
    if changed:
        (Path(workdir) / "words.json").write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return changed


def attach_energy(workdir, words):
    """Fill Word.score from cached (or freshly computed) audio energy; no-op if unavailable."""
    workdir = Path(workdir)
    cache = workdir / "energy.npy"
    fps = ENERGY_FPS
    if cache.exists():
        rms = np.load(cache)
    else:
        audio = workdir / "audio.wav"
        if not audio.exists():
            return words
        from .audio_features import compute_energy  # lazy: imports librosa

        rms, fps = compute_energy(audio)
        np.save(cache, rms)
    for w in words:
        a = int(w.start * fps)
        b = max(a + 1, int(w.end * fps))
        chunk = rms[a:b]
        w.score = float(chunk.mean()) if len(chunk) else 0.0
    return words


def render_clip_files(cfg, source, workdir, words, rank, start, end, platforms, out_dir, captions_on):
    """Re-render one clip for each platform. Writes to a temp file, then swaps atomically."""
    from .captioner import generate_ass
    from .renderer import render_clip

    ass_dir = Path(workdir) / "ass"
    ass_dir.mkdir(parents=True, exist_ok=True)
    produced = {}
    for plat in platforms:
        pcfg = cfg["platforms"][plat]
        ass_path = None
        if captions_on:
            ass_path = ass_dir / f"clip_{rank:02d}_{plat}.ass"
            generate_ass(words, start, end, ass_path, cfg["captions"],
                         pcfg["res_x"], pcfg["res_y"], pcfg["caption_margin_v"])
        final = Path(out_dir) / f"clip_{rank:02d}_{plat}.mp4"
        tmp = final.with_name(final.stem + ".part.mp4")
        render_clip(source, start, end, ass_path, tmp, cfg, plat)
        os.replace(tmp, final)
        produced[plat] = final
    return produced


def make_thumb(video_path, jpg_path):
    try:
        run_ffmpeg(["-ss", "0.6", "-i", video_path, "-frames:v", "1", "-vf", "scale=360:-2", jpg_path])
        return True
    except Exception:
        return False
