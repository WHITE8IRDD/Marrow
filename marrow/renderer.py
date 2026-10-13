from pathlib import Path

from . import hw
from .caption_styles import ensure_fonts
from .utils import run_ffmpeg, run_ffmpeg_progress

_nvenc_ok = None
NVENC_PRESETS = tuple(f"p{i}" for i in range(1, 8))
NVENC_TUNES = ("hq", "ll", "ull", "lossless")
DEFAULT_NVENC_PRESET = "p5"
DEFAULT_NVENC_TUNE = "hq"
DEFAULT_NVENC_CQ = 21


def pick_encoder(pref):
    """Resolve 'auto' by probing NVENC once (cached); explicit prefs are honored."""
    global _nvenc_ok
    if pref in ("libx264", "h264_nvenc"):
        return pref
    if _nvenc_ok is None:
        try:
            run_ffmpeg(["-f", "lavfi", "-i", "color=c=black:s=256x256:d=0.1",
                        "-c:v", "h264_nvenc", "-f", "null", "-"])
            _nvenc_ok = True
        except Exception:
            _nvenc_ok = False
    return "h264_nvenc" if _nvenc_ok else "libx264"


def nvenc_preset(render_cfg=None):
    """Configured NVENC preset ('p1' fastest .. 'p7' slowest), default p5."""
    value = str((render_cfg or {}).get("nvenc_preset") or "").strip().lower()
    return value if value in NVENC_PRESETS else DEFAULT_NVENC_PRESET


def nvenc_tune(render_cfg=None):
    value = str((render_cfg or {}).get("nvenc_tune") or "").strip().lower()
    return value if value in NVENC_TUNES else DEFAULT_NVENC_TUNE


def encoder_args(enc, render_cfg=None, crf=None):
    """Video encoder arguments, shared by normal renders and exports.

    NVENC gets the configured preset/tune and a constant-quality target so the
    Settings choice is applied identically everywhere; libx264 keeps using
    ``render.preset``/``render.crf``.
    """
    render_cfg = render_cfg or {}
    if enc in ("h264_nvenc", "hevc_nvenc"):
        try:
            cq = int(render_cfg.get("nvenc_cq", DEFAULT_NVENC_CQ))
        except (TypeError, ValueError):
            cq = DEFAULT_NVENC_CQ
        if crf is not None:
            cq = int(crf)
        return ["-c:v", enc, "-preset", nvenc_preset(render_cfg), "-tune", nvenc_tune(render_cfg),
                "-rc", "vbr", "-cq", str(max(15, min(35, cq))), "-b:v", "0"]
    try:
        crf = int(render_cfg.get("crf", 20) if crf is None else crf)
    except (TypeError, ValueError):
        crf = 20
    return ["-c:v", "libx264", "-preset", render_cfg.get("preset", "veryfast"),
            "-crf", str(max(0, min(51, crf)))]


def encoder_label(enc):
    """Human name for the hardware panel, so GPU vs CPU fallback is obvious."""
    return {"h264_nvenc": "NVENC H.264", "hevc_nvenc": "NVENC HEVC",
            "libx264": "libx264 (CPU)"}.get(enc, enc)


def _hermite(u):
    """Smoothstep-ish ease (3u²-2u³) written with ffmpeg expression primitives
    (zoompan's evaluator has no smoothstep function)."""
    return f"(pow({u},2)*(3-2*{u}))"


def _panel_zoom_expr(intervals, panel, fps, amp=0.07, ramp=0.30):
    """z(on) for one stacked panel: 1.0 at rest, up to 1+amp while that panel's
    person speaks, with `ramp`-second eased pushes and releases. `intervals`
    are [start, end, panel] in seconds relative to the rendered segment."""
    terms = []
    for iv in intervals:
        try:
            s, e, p = float(iv[0]), float(iv[1]), int(iv[2])
        except (TypeError, ValueError, IndexError):
            continue
        if p != panel:
            continue
        s, e = min(s, e), max(s, e)          # tolerate swapped bounds
        s = max(0.0, s)
        e = max(e, s + 0.05)
        R = max(1.0, ramp * fps)
        u_in = f"clip((on-{s * fps:.1f})/{R:.1f},0,1)"
        u_out = f"clip((on-{e * fps:.1f})/{R:.1f},0,1)"
        terms.append(f"({_hermite(u_in)}-{_hermite(u_out)})")
    if not terms:
        return None
    if len(terms) > 48:                      # keep the filtergraph sane on long clips
        terms = terms[:48]
    return f"min(1+{amp}*({'+'.join(terms)}),{1 + amp * 1.02:.4f})"


def _frame_view_base(rx, ry):
    """vstack of the frame's own two side-by-side views (two-up without a subject).

    Two equal crops centred on each half of the frame, cut down to the panel's 9:8
    shape. This is the last-resort two-up path, used only when nothing in the shot
    could be measured at all; the geometry every earlier render, test and manifest
    was written against, so it is left alone.
    """
    ph = ry // 2
    return (
        f"[0:v]split=2[ta][tb];"
        f"[ta]crop='min(ih*9/8,iw/2)':h='ow*8/9':x='iw/4-ow/2':y='(ih-oh)/2',"
        f"scale={rx}:{ph}:flags=lanczos[p0];"
        f"[tb]crop='min(ih*9/8,iw/2)':h='ow*8/9':x='3*iw/4-ow/2':y='(ih-oh)/2',"
        f"scale={rx}:{ph}:flags=lanczos[p1];"
        f"[p0][p1]vstack=inputs=2[base]"
    )


def build_filter_graph(layout, rx, ry, fps, zoom, ass_name=None, shot=None):
    """Build the -filter_complex string. The final labeled output is [v].

    shot: optional per-shot geometry. Two stacked variants exist:
    * ``panels`` present -> one crop per subject-anchored panel (auto two-shot,
      forced two-up, and the active-speaker push-ins). Layout analysis centres
      each panel on its own subject and gives both panels the same width, so the
      crop coordinates are used as given and both halves are framed alike.
    * no ``panels`` (``views: "frame"``, or a manual stacked override) -> the
      frame's own two side-by-side views are cropped and stacked. This is the
      last-resort two-up path, used when nothing could be measured at all; it
      never shows the same speaker twice because each panel is a different half
      of the frame.
    """
    ratio = rx / ry
    if layout == "face" and not (shot and shot.get("cw")):
        layout = "crop"          # manual override without track data: center crop
    if layout == "stacked" and not (shot and shot.get("panels")):
        base = _frame_view_base(rx, ry)
    elif layout == "stacked" and shot and shot.get("panels"):
        (a, b) = shot["panels"][:2]
        ph = ry // 2
        fps = float(fps or 30)
        act = shot.get("active") or []
        panels = []
        for idx, (tag, pan) in enumerate((("ta", a), ("tb", b))):
            crop = (f"[{tag}]crop={int(pan['w'])}:{int(pan['h'])}:"
                    f"{int(pan['x'])}:{int(pan['y'])}")
            # The analysis sizes panels to the output's half-frame; covering the
            # destination instead of scaling straight into it means an unexpected
            # panel shape is centred by a crop rather than stretched.
            fit = (f"scale={rx}:{ph}:flags=lanczos:force_original_aspect_ratio=increase,"
                   f"crop={rx}:{ph}")
            zexpr = _panel_zoom_expr(act, idx, fps) if act else None
            if zexpr:
                # push in on the speaker: supersample, then zoompan toward the panel center
                sw, sh = int(rx * 1.5) & ~1, int(ph * 1.5) & ~1
                panels.append(
                    f"{crop},scale={sw}:{sh}:flags=lanczos:force_original_aspect_ratio=increase,"
                    f"crop={sw}:{sh},"
                    f"zoompan=z='{zexpr}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                    f"d=1:s={rx}x{ph}:fps={fps},setsar=1[p{idx}]")
            else:
                extra = f",fps={fps}" if act else ""   # keep both panels frame-aligned
                panels.append(f"{crop},{fit}{extra},setsar=1[p{idx}]")
        # zoompan d=1 assigns a new timestamp to every input frame.
        # Resample BEFORE splitting so both panels keep source-time speed,
        # including when only one panel has active-speaker intervals.
        timing = f"fps={fps}," if act else ""
        base = (f"[0:v]{timing}split=2[ta][tb];" + ";".join(panels) +
                ";[p0][p1]vstack=inputs=2[base]")
    elif layout == "face" and shot and shot.get("cw"):
        cw, ch = int(shot["cw"]), int(shot.get("ch", ry))
        x0 = float(shot.get("fx0", 0))
        x1 = float(shot.get("fx1", x0))
        dur = max(float(shot.get("end", 0)) - float(shot.get("start", 0)), 0.01)
        t0 = float(shot.get("start", 0))
        if abs(x1 - x0) > 1.0:
            x_expr = f"lerp({x0:.1f},{x1:.1f},clip((t-{t0:.3f})/{dur:.3f},0,1))"
        else:
            x_expr = f"{x0:.1f}"
        crop = f"crop=min(iw\\,{cw}):{ch}:x='{x_expr}':y='(ih-{ch})/2'"
        scale = f"scale={rx}:{ry}:flags=lanczos"
        base = f"[0:v]{crop},{scale},setsar=1[base]"
    elif layout == "blur_fit":
        base = (
            f"[0:v]split=2[bg][fg];"
            # blur the small copy, then upscale: same look, ~1/16th the blur cost
            f"[bg]scale=iw/4:ih/4,boxblur=10:2,"
            f"scale={rx}:{ry}:force_original_aspect_ratio=increase,crop={rx}:{ry}[bgb];"
            f"[fg]scale={rx}:-2:flags=lanczos[fgs];"
            f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2,setsar=1[base]"
        )
    elif layout == "crop":
        crop = f"crop='min(iw,ih*{ratio:.6f})':'min(ih,iw/{ratio:.6f})'"
        if zoom.get("enabled"):
            # supersample 2x, then push in smoothly using the output frame index `on`
            scale = (
                f"fps={fps},scale={rx * 2}:{ry * 2}:flags=lanczos,"
                f"zoompan=z='min(1+{zoom.get('speed', 0.0004)}*on,{zoom.get('max_zoom', 1.12)})':"
                f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={rx}x{ry}:fps={fps}"
            )
        else:
            scale = f"scale={rx}:{ry}:flags=lanczos"
        base = f"[0:v]{crop},{scale},setsar=1[base]"
    else:
        raise ValueError(f"Unknown layout '{layout}' (use 'crop' or 'blur_fit')")

    tail = f"[base]ass={ass_name}:fontsdir=fonts[v]" if ass_name else "[base]null[v]"
    return base + ";" + tail


def render_clip(video_path, start, end, ass_path, output_path, config, platform="shorts",
                on_progress=None, layout=None, shot=None):
    plat = config["platforms"][platform]
    rx, ry = plat["res_x"], plat["res_y"]
    r = config["render"]
    requested = str(r.get("encoder", "auto")).lower()
    enc = pick_encoder(requested)
    # Report the encoder that will really run, so the hardware panel can tell a
    # GPU encode apart from a CPU fallback (and say why it fell back).
    cpu_fallback = None
    if enc == "libx264" and requested == "auto":
        cpu_fallback = "NVENC not available on this machine → libx264 on CPU"
    hw.set_engine("render", device="gpu" if enc in ("h264_nvenc", "hevc_nvenc") else "cpu",
                  encoder=enc, label=encoder_label(enc),
                  preset=nvenc_preset(r) if enc != "libx264" else r.get("preset"),
                  fallback=cpu_fallback)

    video_path = Path(video_path).resolve()
    output_path = Path(output_path).resolve()
    ass = Path(ass_path).resolve() if ass_path else None
    if ass:
        ensure_fonts(ass.parent)  # bundled fonts next to the .ass; relative fontsdir avoids C: colons

    graph = build_filter_graph(layout or r["layout"], rx, ry, r["fps"], config["zoom"],
                               ass.name if ass else None, shot=shot)

    venc = encoder_args(enc, r)

    args = [
        "-ss", f"{start:.3f}", "-i", video_path, "-t", f"{end - start:.3f}",
        "-filter_complex_threads", "4", "-filter_complex", graph, "-map", "[v]", "-map", "0:a?",
        *venc,
        "-c:a", "aac", "-b:a", "160k",
    ]
    if r.get("loudnorm", True):
        args += ["-af", "loudnorm=I=-16:TP=-1.5:LRA=11"]
    args += ["-r", r["fps"], "-threads", "0", "-filter_threads", "4",
             "-pix_fmt", "yuv420p", "-movflags", "+faststart", output_path]

    # Run inside the subtitle folder so `ass=clip.ass` is a bare filename. This avoids
    # Windows drive-letter colons (C:\...) which break FFmpeg filter syntax.
    cwd = str(ass.parent) if ass else None
    if on_progress is None:
        run_ffmpeg(args, cwd=cwd)
    else:
        run_ffmpeg_progress(args, max(0.1, end - start), on_progress, cwd=cwd)
    return str(output_path)
