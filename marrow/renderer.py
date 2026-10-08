from pathlib import Path

from .utils import run_ffmpeg


def build_filter_graph(layout, rx, ry, fps, zoom, ass_name=None):
    """Build the -filter_complex string. The final labeled output is [v]."""
    ratio = rx / ry
    if layout == "blur_fit":
        base = (
            f"[0:v]split=2[bg][fg];"
            f"[bg]scale={rx}:{ry}:force_original_aspect_ratio=increase,crop={rx}:{ry},boxblur=24:6[bgb];"
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

    tail = f"[base]ass={ass_name}[v]" if ass_name else "[base]null[v]"
    return base + ";" + tail


def render_clip(video_path, start, end, ass_path, output_path, config, platform="shorts"):
    plat = config["platforms"][platform]
    rx, ry = plat["res_x"], plat["res_y"]
    r = config["render"]

    video_path = Path(video_path).resolve()
    output_path = Path(output_path).resolve()
    ass = Path(ass_path).resolve() if ass_path else None

    graph = build_filter_graph(r["layout"], rx, ry, r["fps"], config["zoom"], ass.name if ass else None)

    if r["encoder"] == "h264_nvenc":
        venc = ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", r["crf"], "-b:v", "0"]
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
    args += ["-r", r["fps"], "-pix_fmt", "yuv420p", "-movflags", "+faststart", output_path]

    # Run inside the subtitle folder so `ass=clip.ass` is a bare filename. This avoids
    # Windows drive-letter colons (C:\...) which break FFmpeg filter syntax.
    run_ffmpeg(args, cwd=str(ass.parent) if ass else None)
    return str(output_path)
