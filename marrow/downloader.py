import re
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

# Player clients tried in this order whenever YouTube refuses a request.
#
# None is yt-dlp's own default and goes first: it already picks clients by what is
# available (cookies, JavaScript runtime), and with cookies it uses the signed-in
# defaults, which pull full-quality formats.
#
# web and android come next. This restores the V2/V3 client rotation (the V3 release
# specifically added 403 recovery, cookies, client rotation and a format ladder). Which
# formats they return depends on YouTube's current PO-token/auth policy; some videos
# still expose the pre-merged itag 18 when adaptive formats are unavailable. Keep
# trying the rest of the chain and format ladder rather than treating either client
# as a guaranteed success.
#
# The trailing clients are fallbacks whose formats do not need a GVS PO token in
# yt-dlp 2026.8.x (web, web_safari, android, android_vr, ios and mweb need one for
# adaptive formats). They help when the legacy clients return no formats; keeping
# both sets lets the fallback logic cover old and current YouTube behavior.
PLAYER_CLIENT_CHAIN = [None, ["web"], ["android"], ["tv_downgraded"], ["web_embedded"], ["visionos"]]
PLAYER_CLIENTS = PLAYER_CLIENT_CHAIN  # old name, kept for callers

# Deno is the recommended runtime (`pip install "yt-dlp[deno]"` installs it). Node and Bun are
# enabled as well, so a machine that only has Node.js works too. yt-dlp ignores the ones that
# are not installed.
JS_RUNTIMES = {"deno": {}, "node": {}, "bun": {}}

_SIGN_IN_RE = re.compile(r"sign in to confirm|not a bot|login[ _]required|sign in to youtube", re.I)
_BLOCKED_RE = re.compile(r"sign in to confirm|not a bot|login[ _]required|sign in to youtube|\b403\b|forbidden", re.I)
# yt-dlp raises FileNotFoundError("could not find <browser> cookies database in ...") when the
# saved browser is not installed (or has no profile), wrapped in CookieLoadError("failed to
# load cookies"). Match the inner message through the exception chain.
_MISSING_BROWSER_DB_RE = re.compile(r"could not find .*cookies database|cookies database not found", re.I)


class YouTubeBlockedError(RuntimeError):
    """YouTube refused every player client. The message is written for the user."""

    user_facing = True


@dataclass
class Source:
    path: Path | None
    video_id: str
    title: str
    workdir: Path
    audio_only: bool = False
    info: dict = field(default_factory=dict)
    client: list | None = None  # the player client that answered the metadata request


def is_blocked_error(err) -> bool:
    """True when this client is refused (sign-in check or 403). Other formats won't help."""
    return bool(_BLOCKED_RE.search(str(err)))


def is_missing_browser_db(err) -> bool:
    """True when yt-dlp could not find the saved browser's cookie database.

    This happens when the setting names a browser that is not installed (or has no
    profile yet), e.g. Chrome is selected but only Chromium/Firefox exist. yt-dlp wraps
    the FileNotFoundError in CookieLoadError, so the whole __cause__/__context__ chain
    is searched. A locked database ("could not copy ...") is NOT a miss and returns False.
    """
    seen = set()
    stack = [err]
    while stack:
        e = stack.pop()
        if e is None or id(e) in seen:
            continue
        seen.add(id(e))
        try:
            if _MISSING_BROWSER_DB_RE.search(str(e)):
                return True
        except Exception:
            pass
        for nxt in (getattr(e, "__cause__", None), getattr(e, "__context__", None)):
            if nxt is not None and id(nxt) not in seen:
                stack.append(nxt)
    return False


def _has_browser_cookies(cfg) -> bool:
    try:
        ck = (cfg or {}).get("cookies") if isinstance(cfg, dict) else {}
        return bool(isinstance(ck, dict) and ck.get("from_browser"))
    except Exception:
        return False


def _browser_name(cfg) -> str:
    try:
        ck = (cfg or {}).get("cookies") if isinstance(cfg, dict) else {}
        return str(ck.get("from_browser") or "") if isinstance(ck, dict) else ""
    except Exception:
        return ""


def _without_browser_cookies(cfg):
    """Copy of cfg with cookies-from-browser disabled. A cookies.txt file is kept."""
    if not isinstance(cfg, dict):
        return cfg
    new = dict(cfg)
    ck = cfg.get("cookies")
    if isinstance(ck, dict):
        new_ck = dict(ck)
        new_ck["from_browser"] = ""
        new["cookies"] = new_ck
    return new


_YOUTUBE_RE = re.compile(r"youtube\.com|youtu\.be", re.I)


def give_up(errors, action, cfg=None, fallback=None, url=None):
    """The exception to raise after every attempt failed.

    A YouTube sign-in check or 403 gets the steps that fix it. Anything else (private, removed,
    region-blocked, other sites...) keeps its own message, so the UI can explain it.
    """
    from .diagnostics import summary

    last = errors[-1] if errors else RuntimeError(f"{action} failed")
    not_youtube = url is not None and not _YOUTUBE_RE.search(str(url))
    if not_youtube or not any(is_blocked_error(e) for e in errors):
        return RuntimeError(fallback) if fallback else last
    checked = summary(cfg.get("cookies") if isinstance(cfg, dict) else None)
    if any(_SIGN_IN_RE.search(str(e)) for e in errors):
        head = "YouTube asked to confirm you're not a bot, and every player client was refused."
        steps = ("Fix it, then press Retry:\n"
                 "1. Update yt-dlp with its JavaScript and solver extras: pip install -U \"yt-dlp[default,deno]\"\n"
                 "2. (Optional — most videos work without cookies.) Settings → YouTube cookies: sign in to YouTube "
                 "in Firefox or Chromium (or in Chrome/Edge with that browser closed), then pick that browser, "
                 "or choose a cookies.txt file exported while signed in (works with any browser).")
    else:
        head = "YouTube refused every player client with 403 Forbidden."
        steps = ("Fix it, then press Retry:\n"
                 "1. Update yt-dlp: pip install -U \"yt-dlp[default,deno]\"\n"
                 "2. Settings → YouTube cookies (optional): pick a browser you are signed in to "
                 "(Firefox or Chromium work well), or a cookies.txt file.\n"
                 "3. If it still fails, try again later or from another network.")
    return YouTubeBlockedError(f"{head}\n{steps}\nChecked: {checked}.\nLast error: {last}")


def ydl_opts(cfg, base=None):
    """Shared yt-dlp options: cookies, JavaScript runtimes, retries with backoff, resume."""
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
        # A fresh dict each time: yt-dlp edits this mapping in place.
        "js_runtimes": {name: {} for name in JS_RUNTIMES},
    })
    ck = (cfg or {}).get("cookies", {}) if isinstance(cfg, dict) else {}
    if not isinstance(ck, dict):
        ck = {}
    if ck.get("from_browser"):
        o["cookiesfrombrowser"] = (ck["from_browser"],)
    if ck.get("cookiefile"):
        o["cookiefile"] = ck["cookiefile"]
    log.info("YouTube cookies: %s", ck.get("from_browser") or ("file" if ck.get("cookiefile") else "none"))
    return o


def _client_args(client):
    if not client:
        return {}
    return {"extractor_args": {"youtube": {"player_client": list(client)}}}


def _client_label(client):
    return "default" if not client else "+".join(client)


def _clients_starting_with(first):
    """The client that already answered the metadata request goes first, then the rest."""
    if first is None:
        return list(PLAYER_CLIENT_CHAIN)
    return [first] + [c for c in PLAYER_CLIENT_CHAIN if c != first]


def _probe_metadata(url, cfg, clients):
    """Metadata from the first player client that answers. Returns (info, client).

    If the saved browser is not installed, the same client is retried once without
    cookies-from-browser, and the rest of the chain stays on the no-browser path so the
    missing database is not scanned again. A cookies.txt file is always kept.
    """
    import yt_dlp

    errors = []
    eff = cfg
    for client in clients:
        try:
            with yt_dlp.YoutubeDL(ydl_opts(eff, {"skip_download": True, **_client_args(client)})) as ydl:
                info = ydl.extract_info(url, download=False)
            if info:
                return info, client
            errors.append(RuntimeError("YouTube returned no video information"))
        except Exception as e:
            if is_missing_browser_db(e) and _has_browser_cookies(eff):
                browser = _browser_name(eff) or "saved browser"
                log.warning("Browser cookies unavailable (%s is not installed or has no profile); "
                            "retrying without browser cookies: %s", browser, e)
                eff = _without_browser_cookies(eff)
                try:
                    with yt_dlp.YoutubeDL(ydl_opts(eff, {"skip_download": True, **_client_args(client)})) as ydl:
                        info = ydl.extract_info(url, download=False)
                    if info:
                        return info, client
                    errors.append(RuntimeError("YouTube returned no video information"))
                except Exception as e2:  # next player client, still without browser cookies
                    errors.append(e2)
                    log.warning("Metadata failed (client=%s): %s", _client_label(client), e2)
                continue
            errors.append(e)
            log.warning("Metadata failed (client=%s): %s", _client_label(client), e)
    raise give_up(errors, "Reading the video", cfg, url=url)


def extract_info(url, cfg=None):
    """Metadata only, with the same player-client fallback as the download."""
    return _probe_metadata(url, cfg, PLAYER_CLIENT_CHAIN)[0]


def download_with_fallback(url, outtmpl, cfg=None, duration=None, formats=None, clients=None):
    """Download trying player clients x format ladder. Returns True if a video track was
    fetched, False if only audio succeeded. Raises when every client is refused.

    If the saved browser is not installed, the same client+format is retried once without
    cookies-from-browser, and the rest of the operation (including the audio fallback)
    stays on the no-browser path so the missing database is not scanned again. A
    cookies.txt file is always kept.
    """
    import yt_dlp

    fmts = list(formats or FORMAT_LADDER)
    clients = list(clients or PLAYER_CLIENT_CHAIN)
    errors = []
    eff = cfg

    def _disable_browser_cookies(err):
        nonlocal eff
        if is_missing_browser_db(err) and _has_browser_cookies(eff):
            browser = _browser_name(eff) or "saved browser"
            log.warning("Browser cookies unavailable (%s is not installed or has no profile); "
                        "retrying without browser cookies: %s", browser, err)
            eff = _without_browser_cookies(eff)
            return True
        return False

    def _video_opts(browser_cfg, client, fmt):
        opts = ydl_opts(browser_cfg, {
            "format": fmt,
            "merge_output_format": "mp4",
            "outtmpl": outtmpl,
            **_client_args(client),
        })
        if duration and duration > 45 * 60:
            opts["http_chunk_size"] = 10 * 1024 * 1024
        return opts

    for client in clients:
        for fmt in fmts:
            try:
                with yt_dlp.YoutubeDL(_video_opts(eff, client, fmt)) as ydl:
                    ydl.download([url])
                return True
            except Exception as e:
                if _disable_browser_cookies(e):
                    try:
                        with yt_dlp.YoutubeDL(_video_opts(eff, client, fmt)) as ydl:
                            ydl.download([url])
                        return True
                    except Exception as e2:
                        errors.append(e2)
                        log.warning("Download failed (client=%s, format=%s): %s", _client_label(client), fmt, e2)
                        if is_blocked_error(e2):
                            break  # this client is refused; another format from it won't help
                        continue
                errors.append(e)
                log.warning("Download failed (client=%s, format=%s): %s", _client_label(client), fmt, e)
                if is_blocked_error(e):
                    break  # this client is refused; another format from it won't help
    # Last resort: audio only, so transcription can still run.
    for client in clients:
        try:
            opts = ydl_opts(eff, {"format": AUDIO_FALLBACK, "outtmpl": outtmpl, **_client_args(client)})
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
            return False
        except Exception as e:
            if _disable_browser_cookies(e):
                try:
                    opts = ydl_opts(eff, {"format": AUDIO_FALLBACK, "outtmpl": outtmpl,
                                          **_client_args(client)})
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        ydl.download([url])
                    return False
                except Exception as e2:
                    errors.append(e2)
                    log.warning("Audio download failed (client=%s): %s", _client_label(client), e2)
                continue
            errors.append(e)
            log.warning("Audio download failed (client=%s): %s", _client_label(client), e)
    raise give_up(errors, "Downloading the video", cfg, url=url)


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

    info, client = _probe_metadata(source, cfg, PLAYER_CLIENT_CHAIN)
    video_id = slugify(info["id"])
    title = info.get("title") or video_id
    workdir = ensure_dir(cache_dir / video_id)
    existing, audio_only = _find_source(workdir)
    if existing:
        log.info("Using cached download: %s", existing)
        return Source(existing.resolve(), video_id, title, workdir, audio_only, info, client)
    return Source(None, video_id, title, workdir, False, info, client)


def fetch_source(src: Source, url: str, cfg=None) -> Source:
    """Download the (already resolved) source. Returns it with path set."""
    if src.path is not None:
        return src
    duration = (src.info or {}).get("duration")
    download_with_fallback(url, str(src.workdir / "source.%(ext)s"), cfg, duration,
                           clients=_clients_starting_with(src.client))
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
