from dataclasses import dataclass, field
from pathlib import Path

from .utils import ensure_dir, log, slugify

VIDEO_SUFFIXES = {".mp4", ".mkv", ".webm", ".mov"}
AUDIO_SUFFIXES = {".m4a", ".mp3", ".opus", ".ogg", ".wav", ".webm"}

# Full-quality ladder first, then smaller, then audio-only as a last resort.
FORMAT_LADDER = [
    "bv*[height<=1080]+ba/b[height<=1080]/b",
    "best[height<=1080]/best",
]
AUDIO_FALLBACK = "bestaudio/best"
PLAYER_CLIENTS = ["web", "android"]


@dataclass
class Source:
    path: Path | None
    video_id: str
    title: str
    workdir: Path
    audio_only: bool = False
    info: dict = field(default_factory=dict)


def ydl_opts(cfg, base=None):
    """Shared yt-dlp options: cookies, retries with backoff, resume."""
    o = dict(base or {})
    o.update({
        "quiet": True,
        "noplaylist": True,
        "noprogress": True,
        "retries": 10,
        "fragment_retries": 10,
        "file_access_retries": 5,
        "extractor_retries": 5,
        "retry_sleep_functions": {"http": lambda n: min(2 ** n, 30)},
        "continuedl": True,
    })
    ck = (cfg or {}).get("cookies", {}) if isinstance(cfg, dict) else {}
    log.info("Using cookies from browser: %s", ck.get("from_browser", "None"))
    if ck.get("from_browser"):
        o["cookiesfrombrowser"] = (ck["from_browser"],)
    if ck.get("cookiefile"):
        o["cookiefile"] = ck["cookiefile"]
    return o


def _is_403(e) -> bool:
    s = str(e)
    return "403" in s or "Forbidden" in s


def extract_info(url, cfg=None):
    import yt_dlp

    with yt_dlp.YoutubeDL(ydl_opts(cfg, {"skip_download": True})) as ydl:
        return ydl.extract_info(url, download=False)


def download_with_fallback(url, outtmpl, cfg=None, duration=None, formats=None):
    """Download trying player clients x format ladder. Returns True if a video
    track was fetched, False if only audio succeeded. Raises on total failure."""
    import yt_dlp

    fmts = list(formats or FORMAT_LADDER)
    last_err = None
    for client in PLAYER_CLIENTS:
        for fmt in fmts:
            opts = ydl_opts(cfg, {
                "format": fmt,
                "merge_output_format": "mp4",
                "outtmpl": outtmpl,
                "extractor_args": {"youtube": {"player_client": [client]}},
            })
            if duration and duration > 45 * 60:
                opts["http_chunk_size"] = 10 * 1024 * 1024
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([url])
                return True
            except Exception as e:
                last_err = e
                log.warning("Download failed (client=%s, format=%s): %s", client, fmt, e)
    # Last resort: audio-only so transcription can still proceed.
    try:
        opts = ydl_opts(cfg, {"format": AUDIO_FALLBACK, "outtmpl": outtmpl,
                              "extractor_args": {"youtube": {"player_client": ["android"]}}})
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
        return False
    except Exception as e:
        last_err = e
    raise RuntimeError(
        "Download failed (YouTube blocked this request). "
        "Sign in to YouTube in your browser, then enable 'Use browser cookies' "
        f"in Settings → Advanced → Cookies. Last error: {last_err}")


def _find_source(workdir: Path):
    for p in sorted(workdir.glob("source.*")):
        if p.suffix.lower() in VIDEO_SUFFIXES:
            return p, False
    for p in sorted(workdir.glob("source.*")):
        if p.suffix.lower() in AUDIO_SUFFIXES:
            return p, True
    return None, False


def resolve_source(source: str, cache_dir, cfg=None) -> Source:
    """Identify the source (local file or URL info) WITHOUT downloading."""
    cache_dir = Path(cache_dir)
    local = Path(source).expanduser()
    if local.exists():
        video_id = slugify(local.stem)
        return Source(local.resolve(), video_id, local.stem,
                      ensure_dir(cache_dir / video_id))

    info = extract_info(source, cfg)
    video_id = slugify(info["id"])
    title = info.get("title") or video_id
    workdir = ensure_dir(cache_dir / video_id)
    existing, audio_only = _find_source(workdir)
    if existing:
        log.info("Using cached download: %s", existing)
        return Source(existing.resolve(), video_id, title, workdir, audio_only, info)
    return Source(None, video_id, title, workdir, False, info)


def fetch_source(src: Source, url: str, cfg=None) -> Source:
    """Download the (already resolved) source. Returns it with path set."""
    if src.path is not None:
        return src
    duration = (src.info or {}).get("duration")
    download_with_fallback(url, str(src.workdir / "source.%(ext)s"), cfg, duration)
    path, audio_only = _find_source(src.workdir)
    if path is None:
        raise RuntimeError("Download finished but no media file was found in " + str(src.workdir))
    src.path = path.resolve()
    src.audio_only = audio_only
    return src


def prepare_source(source: str, cache_dir, cfg=None, download=True) -> Source:
    """Accept a local file path or a URL. Downloads are cached per video id."""
    src = resolve_source(source, cache_dir, cfg)
    if download and src.path is None:
        fetch_source(src, source, cfg)
    return src
