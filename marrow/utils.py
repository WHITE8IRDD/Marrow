import logging
import re
import shutil
import subprocess
from pathlib import Path

log = logging.getLogger("marrow")


def ensure_dir(path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def slugify(text: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("_")
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
        return subprocess.run(cmd, check=True, capture_output=True, text=True, cwd=cwd)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffmpeg failed:\n{e.stderr}") from e


def probe_duration(path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        check=True, capture_output=True, text=True,
    )
    return float(out.stdout.strip())
