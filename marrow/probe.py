"""Find-a-video probes: metadata + 480p preview download in a background thread."""
import threading
import time
import uuid
from pathlib import Path

PROBES = {}                      # id -> dict(state, info, progress, error, dir)
_LOCK = threading.Lock()
MAX_AGE = 24 * 3600


def probe(url):
    import yt_dlp
    opts = {"quiet": True, "no_warnings": True, "skip_download": True, "noplaylist": True, "socket_timeout": 10}
    with yt_dlp.YoutubeDL(opts) as y:
        i = y.extract_info(url, download=False)
    return {"title": i.get("title"), "channel": i.get("channel") or i.get("uploader"),
            "duration": i.get("duration"), "thumbnail": i.get("thumbnail"),
            "live": bool(i.get("is_live")), "url": i.get("webpage_url") or url, "video_id": i.get("id")}


def fetch_preview(pid, url, out_dir):
    """Small 480p file (audio included) so the page can play it within seconds."""
    import yt_dlp

    def hook(d):
        if d["status"] == "downloading":
            tot = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            with _LOCK:
                if pid in PROBES:
                    PROBES[pid]["progress"] = round(d.get("downloaded_bytes", 0) / tot, 3) if tot else 0

    opts = {"quiet": True, "no_warnings": True, "noplaylist": True, "progress_hooks": [hook],
            "format": "bv*[height<=480]+ba/b[height<=480]/b", "merge_output_format": "mp4",
            "outtmpl": str(Path(out_dir) / "preview.%(ext)s"), "concurrent_fragment_downloads": 4}
    with yt_dlp.YoutubeDL(opts) as y:
        y.download([url])


def _strip_preview(out_dir):
    from .utils import run_ffmpeg

    d = Path(out_dir)
    src = d / "preview.mp4"
    if not src.exists():
        cands = sorted(d.glob("preview.*"))
        src = cands[0] if cands else None
    if not src:
        return
    try:
        run_ffmpeg(["-i", src, "-vf", "fps=1/3,scale=160:-2,tile=8x1",
                    "-frames:v", "1", d / "strip.jpg"])
    except Exception:
        pass


def start(url, base_dir):
    sweep()
    pid = uuid.uuid4().hex[:12]
    d = Path(base_dir) / pid
    d.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        PROBES[pid] = {"state": "fetching", "info": None, "progress": 0,
                       "dir": str(d), "error": None, "born": time.time()}

    def run():
        try:
            info = probe(url)
            if info.get("live"):
                raise ValueError("Live streams are not supported.")
            if not info.get("title"):
                raise ValueError("Could not read video info from this link.")
            with _LOCK:
                PROBES[pid].update(info=info, state="found")
            try:
                import requests
                thumb = info.get("thumbnail")
                if thumb:
                    (d / "thumb.jpg").write_bytes(requests.get(thumb, timeout=8).content)
            except Exception:
                pass
            with _LOCK:
                PROBES[pid]["state"] = "preview"
            fetch_preview(pid, url, d)
            _strip_preview(d)
            with _LOCK:
                PROBES[pid].update(state="ready", progress=1.0)
        except Exception as e:
            with _LOCK:
                if pid in PROBES:
                    PROBES[pid].update(state="error", error=f"{type(e).__name__}: {str(e)[:300]}")

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
