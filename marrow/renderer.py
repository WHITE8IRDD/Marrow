from pathlib import Path

from . import hw
from .caption_styles import ensure_fonts
from .utils import run_ffmpeg, run_ffmpeg_progress

_nvenc_ok = None


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


def build_filter_graph(layout, rx, ry, fps, zoom, ass_name=None):
    """Build the -filter_complex string. The final labeled output is [v]."""
    ratio = rx / ry
    if layout == "blur_fit":
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
                f"scale={rx * 2}:{ry * 2}:flags=lanczos,"
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
                on_progress=None):
    plat = config["platforms"][platform]
    rx, ry = plat["res_x"], plat["res_y"]
    r = config["render"]
    enc = pick_encoder(r.get("encoder", "auto"))
    hw.set_engine("render", device="gpu" if enc == "h264_nvenc" else "cpu",
                  encoder=enc, label="NVENC" if enc == "h264_nvenc" else "libx264")

    video_path = Path(video_path).resolve()
    output_path = Path(output_path).resolve()
    ass = Path(ass_path).resolve() if ass_path else None
    if ass:
        ensure_fonts(ass.parent)  # bundled fonts next to the .ass; relative fontsdir avoids C: colons

    graph = build_filter_graph(r["layout"], rx, ry, r["fps"], config["zoom"], ass.name if ass else None)

    if enc == "h264_nvenc":
        venc = ["-c:v", "h264_nvenc", "-preset", "p5", "-tune", "hq",
                "-rc", "vbr", "-cq", "21", "-b:v", "0"]
    else:
        venc = ["-c:v", "libx264", "-preset", r["preset"], "-crf", r["crf"]]

    args = [
        "-ss", f"{start:.3f}", "-i", video_path, "-t", f"{end - start:.3f}",
        "-filter_complex", graph, "-map", "[v]", "-map", "0:a?",
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
