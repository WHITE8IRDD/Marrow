"""Find-a-video probes: metadata + 480p preview download in a background thread.

Every yt-dlp call uses the same cookie settings as the real download
(downloader.ydl_opts), and walks a short list of player clients and formats
before giving up, so one blocked format no longer ends the preview.
"""
import os
import threading
import time
import uuid
from pathlib import Path

from .downloader import (PLAYER_CLIENT_CHAIN, _browser_name, _has_browser_cookies,
                         _without_browser_cookies, give_up, is_blocked_error,
                         is_missing_browser_db)
from .utils import log

PROBES = {}                      # id -> dict(state, info, progress, error, dir)
_LOCK = threading.Lock()
MAX_AGE = 24 * 3600

PREVIEW_EXTS = (".mp4", ".mkv", ".webm", ".mov", ".m4v")
PREVIEW_FORMATS = (
    "bv*[height<=480]+ba/b[height<=480]/b",   # 480p video + audio, merged to mp4
    "b[height<=480]/b",                       # one file, 480p or smaller
    "b",                                      # anything playable
)
# Same chain as the real download (downloader.PLAYER_CLIENT_CHAIN), so the preview and the
# download can never disagree about which clients are tried.
PLAYER_CLIENTS = PLAYER_CLIENT_CHAIN


def _opts(cfg, extra=None, client=None):
    from .downloader import ydl_opts

    o = ydl_opts(cfg, {"quiet": True, "no_warnings": True, "noplaylist": True,
                       "socket_timeout": 15, **(extra or {})})
    o["retries"] = 2            # fail fast here; the pipeline has its own, longer retry ladder
    o["fragment_retries"] = 2
    if client:
        o["extractor_args"] = {"youtube": {"player_client": client}}
    return o


def _preview_result(i, url):
    return {"title": i.get("title"), "channel": i.get("channel") or i.get("uploader"),
            "duration": i.get("duration"), "thumbnail": i.get("thumbnail"),
            "live": bool(i.get("is_live")), "url": i.get("webpage_url") or url,
            "video_id": i.get("id")}


def _note_missing_browser_db(eff, err):
    """Drop cookies-from-browser after a missing-database error. Returns the new cfg."""
    browser = _browser_name(eff) or "saved browser"
    log.warning("Browser cookies unavailable (%s is not installed or has no profile); "
                "retrying without browser cookies: %s", browser, err)
    return _without_browser_cookies(eff)


def probe(url, cfg=None):
    """Metadata only. Raises the last error when every player client fails.

    If the saved browser is not installed, the same client is retried once without
    cookies-from-browser, and the rest of the chain stays on the no-browser path.
    """
    import yt_dlp

    errors = []
    eff = cfg
    for client in PLAYER_CLIENTS:
        try:
            with yt_dlp.YoutubeDL(_opts(eff, {"skip_download": True}, client)) as y:
                i = y.extract_info(url, download=False)
            return _preview_result(i, url)
        except Exception as e:
            if is_missing_browser_db(e) and _has_browser_cookies(eff):
                eff = _note_missing_browser_db(eff, e)
                try:
                    with yt_dlp.YoutubeDL(_opts(eff, {"skip_download": True}, client)) as y:
                        i = y.extract_info(url, download=False)
                    return _preview_result(i, url)
                except Exception as e2:  # try the next player client, still without browser cookies
                    errors.append(e2)
                continue
            errors.append(e)  # try the next player client
    raise give_up(errors, "Reading the video", cfg, url=url)


def preview_file(d):
    """The finished preview in `d`: never a .part file or a single-stream leftover."""
    d = Path(d)
    for ext in PREVIEW_EXTS:
        f = d / f"preview{ext}"
        if f.is_file() and f.stat().st_size > 0:
            return f
    return None


def _clear_intermediates(d):
    d = Path(d)
    keep = preview_file(d)
    for f in d.glob("preview.*"):
        if f != keep and f.is_file():
            f.unlink(missing_ok=True)


def fetch_preview(pid, url, out_dir, cfg=None):
    """Small 480p file (audio included) so the page can play it within seconds."""
    import yt_dlp

    def hook(d):
        if d["status"] == "downloading":
            tot = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            with _LOCK:
                if pid in PROBES:
                    PROBES[pid]["progress"] = round(d.get("downloaded_bytes", 0) / tot, 3) if tot else 0

    errors = []
    eff = cfg
    for client in PLAYER_CLIENTS:
        for fmt in PREVIEW_FORMATS:
            def _preview_opts(browser_cfg):
                return _opts(browser_cfg, {"format": fmt, "merge_output_format": "mp4",
                                           "progress_hooks": [hook],
                                           "outtmpl": str(Path(out_dir) / "preview.%(ext)s"),
                                           "concurrent_fragment_downloads": 4}, client)

            try:
                with yt_dlp.YoutubeDL(_preview_opts(eff)) as y:
                    y.download([url])
                if preview_file(out_dir):
                    _clear_intermediates(out_dir)
                    return
                errors.append(RuntimeError("the preview file was not written"))
            except Exception as e:  # next format / client
                if is_missing_browser_db(e) and _has_browser_cookies(eff):
                    eff = _note_missing_browser_db(eff, e)
                    try:
                        with yt_dlp.YoutubeDL(_preview_opts(eff)) as y:
                            y.download([url])
                        if preview_file(out_dir):
                            _clear_intermediates(out_dir)
                            return
                        errors.append(RuntimeError("the preview file was not written"))
                    except Exception as e2:
                        errors.append(e2)
                        if is_blocked_error(e2):
                            break  # this client is refused; other formats from it won't help
                        continue
                    continue
                errors.append(e)
                if is_blocked_error(e):
                    break  # this client is refused; other formats from it won't help
    _clear_intermediates(out_dir)
    last = errors[-1] if errors else RuntimeError("no preview was attempted")
    raise give_up(errors, "The preview", cfg, url=url,
                  fallback=f"no playable preview ({type(last).__name__}: {str(last)[:200]})")


def _strip_preview(out_dir):
    from .studio import make_strip

    src = preview_file(out_dir)
    if src is None:
        return
    try:
        make_strip(src, out_dir)
    except Exception:
        pass


def _save_thumb(url, d):
    if not url:
        return
    try:
        import requests

        data = requests.get(url, timeout=8).content
        if data:
            tmp = Path(d) / "thumb.part.jpg"
            tmp.write_bytes(data)
            os.replace(tmp, Path(d) / "thumb.jpg")
    except Exception:
        pass


def start(url, base_dir, cfg=None):
    sweep()
    pid = uuid.uuid4().hex[:12]
    d = Path(base_dir) / pid
    d.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        PROBES[pid] = {"state": "fetching", "info": None, "progress": 0,
                       "dir": str(d), "error": None, "born": time.time()}

    def run():
        try:
            info = probe(url, cfg)
            if info.get("live"):
                raise ValueError("Live streams are not supported.")
            if not info.get("title"):
                raise ValueError("Could not read video info from this link.")
            with _LOCK:
                PROBES[pid].update(info=info, state="found")
            _save_thumb(info.get("thumbnail"), d)
            with _LOCK:
                PROBES[pid]["state"] = "preview"
            fetch_preview(pid, url, d, cfg)
            _strip_preview(d)
            with _LOCK:
                PROBES[pid].update(state="ready", progress=1.0)
        except Exception as e:
            # User-facing messages (sign-in checks, 403s) are shown as written; anything else keeps its type.
            text = str(e)[:300] if getattr(e, "user_facing", False) else f"{type(e).__name__}: {str(e)[:300]}"
            with _LOCK:
                if pid in PROBES:
                    PROBES[pid].update(state="error", error=text)

    threading.Thread(target=run, daemon=True, name=f"marrow-probe-{pid}").start()
    return pid


def get(pid):
    with _LOCK:
        p = PROBES.get(pid)
        return dict(p) if p else None


def sweep():
    import shutil

    now = time.time()
    dead = []
    with _LOCK:
        for k, v in list(PROBES.items()):
            if now - v.get("born", now) > MAX_AGE:
                dead.append((k, v.get("dir")))
                del PROBES[k]
    for k, d in dead:
        if d:
            shutil.rmtree(d, ignore_errors=True)
