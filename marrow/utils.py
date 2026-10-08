import logging
import os
import re
import shutil
import subprocess
from pathlib import Path

log = logging.getLogger("marrow")


def ensure_dir(path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def part_path(dst) -> Path:
    """Temp name beside `dst` that keeps the extension (ffmpeg picks the muxer from it)."""
    dst = Path(dst)
    return dst.with_name(f"{dst.stem}.part{dst.suffix}")


def atomic_copy(src, dst) -> None:
    """Copy so that `dst` only appears once it is complete (readers never see a partial file)."""
    dst = Path(dst)
    tmp = part_path(dst)
    try:
        shutil.copyfile(src, tmp)
        os.replace(tmp, dst)
    finally:
        tmp.unlink(missing_ok=True)


def slugify(text: str) -> str:
    slug = re.sub(r"[^\w.\-]+", "_", text).strip("_")
    return slug[:80] or "video"


def format_ass_time(t: float) -> str:
    """Seconds -> ASS timestamp H:MM:SS.CC (rounded, never produces .100)."""
    total_cs = max(0, int(round(t * 100)))
    h, rem = divmod(total_cs, 360000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def require_ffmpeg():
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            raise RuntimeError(
                f"{tool} was not found on PATH. Install FFmpeg "
                "(Windows: `winget install ffmpeg`, macOS: `brew install ffmpeg`, "
                "Linux: your package manager) and open a new terminal."
            )


def run_ffmpeg(args, cwd=None):
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"] + [str(a) for a in args]
    try:
        return subprocess.run(cmd, check=True, capture_output=True, text=True, cwd=cwd,
                              encoding="utf-8", errors="replace")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffmpeg failed:\n{e.stderr}") from e


def run_ffmpeg_progress(args, total_sec, on_progress, cwd=None):
    """Like run_ffmpeg, but reports 0..1 fraction via ffmpeg's progress pipe."""
    import threading

    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
           "-progress", "pipe:1", "-nostats"] + [str(a) for a in args]
    p = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, encoding="utf-8", errors="replace")
    err = []

    def drain():
        try:
            err.append(p.stderr.read())
        except Exception:
            pass

    threading.Thread(target=drain, daemon=True).start()   # drain stderr (avoids deadlock)
    try:
        for line in p.stdout:
            if line.startswith("out_time_us="):
                try:
                    us = int(line.strip().split("=")[1])
                except ValueError:
                    continue
                if us >= 0 and total_sec > 0:
                    on_progress(max(0.0, min(1.0, us / 1e6 / total_sec)))
    finally:
        p.stdout.close()
    if p.wait() != 0:
        raise RuntimeError("ffmpeg failed:\n" + "".join(err)[-1500:])


def probe_duration(path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        check=True, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return float(out.stdout.strip())
