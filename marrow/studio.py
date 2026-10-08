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


def make_strip(src, workdir):
    """Thumbnail strip for the scan panel (fast tile filter)."""
    w = Path(workdir)
    run_ffmpeg(["-i", src, "-vf", "fps=1/3,scale=160:-2,tile=8x1",
                "-frames:v", "1", w / "strip.jpg"])


def make_proxy(src, workdir, duration):
    """480p seek-friendly proxy + thumbnail strip for the Live Analysis panel."""
    w = Path(workdir)
    run_ffmpeg(["-i", src, "-vf", "scale=-2:480,fps=24", "-an", "-c:v", "libx264",
                "-preset", "ultrafast", "-crf", "30", "-g", "24",
                "-movflags", "+faststart", w / "proxy.mp4"])
    step = max(1, duration / 24)
    run_ffmpeg(["-i", src, "-vf", f"fps=1/{step:.3f},scale=160:-2,tile=24x1",
                "-frames:v", "1", w / "strip.jpg"])


def load_words(workdir):
    from .captioner import clean_words

    raw = json.loads((Path(workdir) / "words.json").read_text(encoding="utf-8"))
    words = clean_words([Word(s, e, t) for s, e, t in raw["words"]])
    raw["words"] = [[w.start, w.end, w.text] for w in words]
    return words, raw


def words_in_range(raw, start, end):
    """Indices + data of cached words overlapping [start, end]."""
    out = []
    for i, (s, e, t) in enumerate(raw["words"]):
        if e > start and s < end:
            out.append({"i": i, "t": t, "s": round(s, 2), "e": round(e, 2)})
    return out


def apply_edits(workdir, raw, edits, timings=None):
    """Persist corrected caption text / deletions / timing tweaks into the cached
    transcript. Text updates apply first (original indices), then deletions
    (descending, so indices stay valid). Returns number changed."""
    n = len(raw["words"])
    changed = 0
    for key, value in (edits or {}).items():
        try:
            i = int(key)
        except (TypeError, ValueError):
            continue
        text = str(value).strip()
        if not (0 <= i < n) or not text:
            continue  # deletions handled below
        if len(text) > 40 or raw["words"][i][2] == text:
            continue
        raw["words"][i][2] = text
        changed += 1
    dels = sorted({int(k) for k, v in (edits or {}).items()
                   if str(v).strip() == "" and str(k).lstrip("-").isdigit()}, reverse=True)
    for i in dels:
        if 0 <= i < len(raw["words"]):
            del raw["words"][i]
            changed += 1
    for key, value in (timings or {}).items():
        try:
            i = int(key)
        except (TypeError, ValueError):
            continue
        if not (0 <= i < len(raw["words"])):
            continue
        try:
            s, e = float(value[0]), float(value[1])
        except (TypeError, ValueError, IndexError):
            continue
        if e - s < 0.05 or s < 0:
            continue
        raw["words"][i][0], raw["words"][i][1] = round(s, 3), round(e, 3)
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


def normalize_shots(shots, start, end, default="crop"):
    """Clip shot list to [start, end] (source-absolute in, out), filling gaps."""
    segs = []
    for sh in shots or []:
        s, e = max(start, float(sh["start"])), min(end, float(sh["end"]))
        if e > s:
            segs.append({"start": s, "end": e, "layout": sh.get("layout") or default,
                         **{k: v for k, v in sh.items() if k not in ("start", "end", "layout")}})
    segs.sort(key=lambda s: s["start"])
    out, cur = [], start
    for s in segs:
        if s["start"] > cur + 0.01:
            out.append({"start": cur, "end": s["start"], "layout": default})
        out.append(s)
        cur = max(cur, s["end"])
    if cur < end - 0.01:
        out.append({"start": cur, "end": end, "layout": default})
    return out


def needs_segmented_render(shots):
    return any((s.get("layout") in ("stacked", "face")) for s in (shots or []))


def apply_shot_overrides(shots, overrides):
    """Replace per-shot layouts with user overrides {index: layout}."""
    if not overrides:
        return shots
    out = []
    for i, sh in enumerate(shots or []):
        sh = dict(sh)
        lay = overrides.get(str(i), overrides.get(i))
        if lay in ("auto", "crop", "blur_fit", "stacked", "face"):
            if lay != "auto":
                sh["layout"] = lay
        out.append(sh)
    return out


def render_clip_shots(cfg, media, workdir, words, rank, start, end, plats, out_dir,
                      captions_on, shots, on_progress=None):
    """Render one clip whose shots use different layouts. Per-segment ASS +
    renders, concatenated per platform. Returns {platform: final_path}."""
    from .captioner import generate_ass
    from .renderer import render_clip

    workdir, out_dir = Path(workdir), Path(out_dir)
    ass_dir = workdir / "ass"
    ass_dir.mkdir(parents=True, exist_ok=True)
    segs = normalize_shots(shots, start, end, cfg["render"]["layout"])
    total_dur = max(0.1, end - start)
    done = [0.0]

    def seg_prog(frac, seg_s, seg_e):
        if on_progress:
            on_progress(min(1.0, (done[0] + frac * (seg_e - seg_s)) / total_dur))

    produced = {}
    for plat in plats:
        pcfg = cfg["platforms"][plat]
        parts = []
        tmpdir = workdir / f"seg_{rank:02d}_{plat}"
        tmpdir.mkdir(parents=True, exist_ok=True)
        for i, sg in enumerate(segs):
            seg_dur = round(sg["end"] - sg["start"], 3)
            ass_path = None
            if captions_on:
                ass_path = ass_dir / f"clip_{rank:02d}_{plat}_s{i}.ass"
                rel = [{"s": 0.0, "e": seg_dur, "layout": sg["layout"]}]
                generate_ass(words, sg["start"], sg["end"], ass_path, cfg["captions"],
                             pcfg["res_x"], pcfg["res_y"], pcfg["caption_margin_v"],
                             shots=rel)
            seg_out = tmpdir / f"s{i}.mp4"
            seg_shot = dict(sg, start=0.0, end=seg_dur)
            render_clip(media, sg["start"], sg["end"], ass_path, seg_out, cfg, plat,
                        on_progress=lambda f, _s=sg["start"], _e=sg["end"]: seg_prog(f, _s, _e),
                        layout=sg["layout"] if sg["layout"] in ("stacked", "face") else None,
                        shot=seg_shot if sg["layout"] in ("stacked", "face") else None)
            parts.append(seg_out)
        final = out_dir / f"clip_{rank:02d}_{plat}.mp4"
        tmp = final.with_name(final.stem + ".part.mp4")
        lst = tmpdir / "list.txt"
        lst.write_text("".join(f"file '{p.resolve()}'\n" for p in parts), encoding="utf-8")
        run_ffmpeg(["-f", "concat", "-safe", "0", "-i", lst, "-c", "copy",
                    "-movflags", "+faststart", tmp])
        os.replace(tmp, final)
        produced[plat] = final
    return produced


def render_clip_files(cfg, source, workdir, words, rank, start, end, platforms, out_dir,
                      captions_on, shots=None):
    """Re-render one clip for each platform. Writes to a temp file, then swaps atomically."""
    from .captioner import generate_ass
    from .caption_styles import ensure_fonts
    from .renderer import render_clip

    if needs_segmented_render(shots):
        return render_clip_shots(cfg, source, workdir, words, rank, start, end,
                                 platforms, out_dir, captions_on, shots)

    ass_dir = Path(workdir) / "ass"
    ass_dir.mkdir(parents=True, exist_ok=True)
    ensure_fonts(ass_dir)
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


EXPORT_QUALITIES = {
    "480p": {"h": 480, "crf": 26},
    "720p": {"h": 720, "crf": 23},
    "1080p": {"h": 1080, "crf": 21},
    "1440p": {"h": 1440, "crf": 20},
    "source": {"h": 0, "crf": 18},
}

_hevc_ok = None


def pick_export_encoder(height, cfg_enc):
    """hevc_nvenc for 1440p+ when supported, else the normal render pick."""
    from .renderer import pick_encoder

    if height and height > 1080:
        global _hevc_ok
        if _hevc_ok is None:
            try:
                run_ffmpeg(["-f", "lavfi", "-i", "color=c=black:s=256x256:d=0.1",
                            "-c:v", "hevc_nvenc", "-f", "null", "-"])
                _hevc_ok = True
            except Exception:
                _hevc_ok = False
        if _hevc_ok:
            return "hevc_nvenc"
        return "libx264"
    return pick_encoder(cfg_enc)


def export_clip(cfg, media, workdir, words, rank, start, end, spec, out_path,
                on_progress=None, shots=None, overrides=None):
    """One-off export render: quality scale, captions on/off, style + framing
    overrides, container remux. Segments per shot when stacked/face layouts
    are present. Returns (final_path, encoder_used)."""
    from .caption_styles import ensure_fonts
    from .captioner import generate_ass
    from .renderer import build_filter_graph

    spec = spec or {}
    plat = spec.get("platform", "shorts")
    pcfg = cfg["platforms"][plat]
    rx, ry = pcfg["res_x"], pcfg["res_y"]
    fr = spec.get("framing") or "auto"
    quality = spec.get("quality") if spec.get("quality") in EXPORT_QUALITIES else "1080p"
    q = EXPORT_QUALITIES[quality]
    adv = spec.get("advanced") if isinstance(spec.get("advanced"), dict) else {}
    try:
        fps_cap = int(adv.get("fps") or 0)
    except (TypeError, ValueError):
        fps_cap = 0

    if fr in ("auto", "stacked", "face"):
        if shots is None:
            from . import layout as _layout

            shots = _layout.analyze(media, start, end, workdir=workdir)
        shots = apply_shot_overrides(shots, overrides)
        segmented = needs_segmented_render(shots)
    else:
        segmented = False

    d = Path(workdir) / "ass_export"
    d.mkdir(parents=True, exist_ok=True)
    ensure_fonts(d)
    _st = spec.get("style") if isinstance(spec.get("style"), dict) else {}
    style = {"preset": _st.get("preset"),
             "overrides": _st.get("overrides") if isinstance(_st.get("overrides"), dict) else {},
             "font": cfg["captions"].get("font", "Arial")}
    enc = pick_export_encoder(q["h"], cfg["render"].get("encoder", "auto"))
    crf = q["crf"]
    try:
        crf = int(adv.get("crf", crf))
    except (TypeError, ValueError):
        pass
    crf = max(16, min(32, crf))
    if enc == "h264_nvenc":
        venc = ["-c:v", "h264_nvenc", "-preset", "p5", "-tune", "hq",
                "-rc", "vbr", "-cq", str(crf), "-b:v", "0"]
    elif enc == "hevc_nvenc":
        venc = ["-c:v", "hevc_nvenc", "-preset", "p5", "-tune", "hq",
                "-rc", "vbr", "-cq", str(crf), "-b:v", "0"]
    else:
        venc = ["-c:v", "libx264", "-preset", cfg["render"].get("preset", "fast"),
                "-crf", str(crf)]
    try:
        mbps = float(adv.get("video_mbps") or 0)
    except (TypeError, ValueError):
        mbps = 0
    if mbps > 0:
        venc += ["-maxrate", f"{mbps}M", "-bufsize", f"{2 * mbps}M"]
    try:
        ab = int(adv.get("audio_kbps") or 0)
    except (TypeError, ValueError):
        ab = 0

    def make_args(a_path, lay, shot, s, e, out):
        graph = build_filter_graph(lay, rx, ry, cfg["render"]["fps"], {"enabled": False},
                                   a_path.name if a_path else None, shot=shot)
        vlabel = "[v]"
        if q["h"]:
            graph += f";[v]scale=-2:{q['h']}[x]"
            vlabel = "[x]"
        if fps_cap in (30, 60):
            graph += f";[{vlabel[1:-1]}]fps={fps_cap}[y]"
            vlabel = "[y]"
        args = ["-ss", f"{s:.3f}", "-i", str(Path(media).resolve()),
                "-t", f"{e - s:.3f}", "-filter_complex", graph,
                "-map", vlabel, "-map", "0:a?", *venc,
                "-c:a", "aac", "-b:a", f"{ab}k" if ab > 0 else "160k"]
        if cfg["render"].get("loudnorm", True):
            args += ["-af", "loudnorm=I=-16:TP=-1.5:LRA=11"]
        args += ["-r", str(fps_cap if fps_cap in (30, 60) else cfg["render"]["fps"]),
                 "-threads", "0", "-pix_fmt", "yuv420p", "-movflags", "+faststart", out]
        return args

    def run_args(args, total, frac0=0.0, span=1.0):
        if on_progress is None:
            run_ffmpeg(args, cwd=str(d))
        else:
            from .utils import run_ffmpeg_progress

            run_ffmpeg_progress(args, total,
                                lambda f: on_progress(min(1.0, frac0 + f * span)),
                                cwd=str(d))

    total_dur = max(0.1, end - start)
    if segmented:
        segs = normalize_shots(shots, start, end, cfg["render"]["layout"])
        tmpdir = Path(workdir) / f"exp_{rank:02d}"
        tmpdir.mkdir(parents=True, exist_ok=True)
        parts, done = [], 0.0
        for i, sg in enumerate(segs):
            ass_path = None
            if spec.get("captions", True):
                ass_path = d / f"export_{rank:02d}_s{i}.ass"
                rel = [{"s": 0.0, "e": round(sg["end"] - sg["start"], 3), "layout": sg["layout"]}]
                generate_ass(words, sg["start"], sg["end"], ass_path, style,
                             rx, ry, pcfg["caption_margin_v"], shots=rel)
            seg_out = tmpdir / f"s{i}.mp4"
            seg_shot = dict(sg, start=0.0, end=round(sg["end"] - sg["start"], 3))
            lay = sg["layout"] if sg["layout"] in ("stacked", "face") else cfg["render"]["layout"]
            run_args(make_args(ass_path, lay,
                               seg_shot if sg["layout"] in ("stacked", "face") else None,
                               sg["start"], sg["end"], seg_out),
                     sg["end"] - sg["start"],
                     done / total_dur, (sg["end"] - sg["start"]) / total_dur)
            parts.append(seg_out)
            done += sg["end"] - sg["start"]
        tmp = Path(out_path).with_name(Path(out_path).stem + ".part.mp4")
        lst = tmpdir / "list.txt"
        lst.write_text("".join(f"file '{p.resolve()}'\n" for p in parts), encoding="utf-8")
        run_ffmpeg(["-f", "concat", "-safe", "0", "-i", lst, "-c", "copy",
                    "-movflags", "+faststart", tmp])
    else:
        layout = fr if fr in ("crop", "blur_fit") else cfg["render"]["layout"]
        ass_path = None
        if spec.get("captions", True):
            ass_path = d / f"export_{rank:02d}.ass"
            generate_ass(words, start, end, ass_path, style, rx, ry, pcfg["caption_margin_v"])
        tmp = Path(out_path).with_name(Path(out_path).stem + ".part.mp4")
        run_args(make_args(ass_path, layout, None, start, end, tmp), total_dur)
    final = Path(out_path)
    container = spec.get("format", "mp4")
    if container == "mov":
        final = final.with_suffix(".mov")
        run_ffmpeg(["-i", tmp, "-c", "copy", final], cwd=str(d))
        tmp.unlink(missing_ok=True)
    else:
        os.replace(tmp, final)
    return str(final), enc


def waveform(workdir, buckets=600):
    """Downsampled peak envelope for the timeline (cached as peaks.json)."""
    import numpy as np

    w = Path(workdir)
    cache = w / "peaks.json"
    if cache.exists():
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except Exception:
            pass
    audio = w / "audio.wav"
    if not audio.exists():
        return {"peaks": [], "duration": 0}
    import soundfile as sf

    y, sr = sf.read(str(audio), always_2d=True)
    y = y.mean(axis=1)
    n = max(1, len(y) // buckets)
    peaks = [float(np.abs(y[i:i + n]).max()) if len(y[i:i + n]) else 0.0
             for i in range(0, len(y), n)]
    mx = max(peaks) or 1.0
    out = {"peaks": [round(p / mx, 3) for p in peaks], "duration": round(len(y) / sr, 2)}
    try:
        cache.write_text(json.dumps(out), encoding="utf-8")
    except OSError:
        pass
    return out


def make_clip_thumb(source, start, jpg_path):
    """9:16 first frame of a clip window (for progress tiles). Best effort."""
    try:
        run_ffmpeg(["-ss", f"{start:.3f}", "-i", source, "-frames:v", "1",
                    "-vf", "crop=ih*9/16:ih,scale=270:480,format=yuv420p", jpg_path])
        return True
    except Exception:
        return False


def make_thumb(video_path, jpg_path):
    try:
        run_ffmpeg(["-ss", "0.6", "-i", video_path, "-frames:v", "1",
                    "-vf", "scale=360:-2,format=yuv420p", jpg_path])
        return True
    except Exception:
        return False


def render_caption_preview(cfg, source, workdir, words, t, style, platform="shorts", layout="crop",
                             shots=None, clip_start=0.0):
    """Render ONE frame (~1 s) so the UI can preview a caption style on the real video."""
    import base64

    from .caption_styles import ensure_fonts
    from .captioner import generate_ass
    from .renderer import build_filter_graph

    p = cfg["platforms"][platform]
    rx, ry = p["res_x"], p["res_y"]
    source = str(Path(source).resolve())  # cwd below is the ass folder; keep the input reachable
    t0 = max(0.0, t - 1.0)                              # include the words just before t
    d = Path(workdir) / "ass_preview"
    d.mkdir(parents=True, exist_ok=True)
    ensure_fonts(d)
    ass = d / "preview.ass"
    rel = [{"s": max(0.0, s.get("start", 0) - t0), "e": s.get("end", 0) - t0,
            "layout": s.get("layout", "crop")}
           for s in (shots or []) if s.get("end", 0) > t0 and s.get("start", 0) < t0 + 4]
    generate_ass(words, t0, t0 + 4, ass, style, rx, ry, p["caption_margin_v"],
                 shots=rel or None)
    use_layout, use_shot = layout, None
    if shots:
        cur = next((s for s in shots if s.get("start", 0) <= t <= s.get("end", 0)), None)
        if cur and cur.get("layout") in ("stacked", "face"):
            use_layout, use_shot = cur["layout"], dict(cur, start=0.0, end=4.0)
    graph = build_filter_graph(use_layout, rx, ry, 30, {"enabled": False}, ass.name,
                               shot=use_shot) + ";[v]scale=360:-2,format=yuv420p[p]"
    jpg = (d / "preview.jpg").resolve()  # absolute: cwd below is d itself
    run_ffmpeg(["-ss", f"{t0:.3f}", "-i", source, "-ss", f"{t - t0:.3f}",
                "-filter_complex", graph, "-map", "[p]", "-frames:v", "1", "-q:v", "3", jpg],
               cwd=str(d))
    return "data:image/jpeg;base64," + base64.b64encode(jpg.read_bytes()).decode()
