from dataclasses import dataclass
from pathlib import Path

from .utils import ensure_dir, log, slugify

VIDEO_SUFFIXES = {".mp4", ".mkv", ".webm", ".mov"}


@dataclass
class Source:
    path: Path
    video_id: str
    title: str
    workdir: Path


def _find_source(workdir: Path):
    for p in sorted(workdir.glob("source.*")):
        if p.suffix.lower() in VIDEO_SUFFIXES:
            return p
    return None


def prepare_source(source: str, cache_dir) -> Source:
    """Accept a local file path or a URL. Downloads are cached per video id."""
    cache_dir = Path(cache_dir)
    local = Path(source).expanduser()
    if local.exists():
        video_id = slugify(local.stem)
        return Source(local.resolve(), video_id, local.stem, ensure_dir(cache_dir / video_id))

    import yt_dlp

    with yt_dlp.YoutubeDL({"quiet": True, "noplaylist": True, "skip_download": True}) as ydl:
        info = ydl.extract_info(source, download=False)
    video_id = slugify(info["id"])
    title = info.get("title") or video_id
    workdir = ensure_dir(cache_dir / video_id)

    existing = _find_source(workdir)
    if existing:
        log.info("Using cached download: %s", existing)
        return Source(existing.resolve(), video_id, title, workdir)

    opts = {
        "format": "bv*[height<=1080]+ba/b[height<=1080]/b",
        "merge_output_format": "mp4",
        "outtmpl": str(workdir / "source.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "noprogress": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.extract_info(source, download=True)

    path = _find_source(workdir)
    if path is None:
        raise RuntimeError("Download finished but no video file was found in " + str(workdir))
    return Source(path.resolve(), video_id, title, workdir)
