"""Marrow web UI: a local HTTP server (standard library only) with a REST API,
a single background worker, and a static single-page app in marrow/web/index.html.

Run:  marrow-ui   or   python -m marrow.server
"""
import argparse
import json
import logging
import mimetypes
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import webbrowser
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import __version__, hw, probe, studio
from .config import deep_merge, load_config
from .downloader import VIDEO_SUFFIXES, _find_source
from .utils import atomic_copy, ensure_dir, log, probe_duration, slugify

mimetypes.add_type("font/ttf", ".ttf")  # Windows registry often lacks this; @font-face needs it

WEB_DIR = Path(__file__).parent / "web"
STATIC_TYPES = {".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8"}
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "[::1]", "::1"}
ACTIVE = {"queued", "running"}

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]+$")
UPLOAD_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
WHISPER_MODELS = {"auto", "large-v3-turbo", "distil-large-v3", "large-v3", "medium", "small"}
WHISPER_QUALITIES = {"fast", "best"}


class ApiError(Exception):
    def __init__(self, msg, status=400):
        super().__init__(msg)
        self.msg, self.status = msg, status


class Cancelled(Exception):
    pass


# --------------------------------------------------------------------------- validation

def _int(value, lo, hi, default):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, value))


def _color(value, default):
    return value if isinstance(value, str) and HEX.match(value) else default


def clean_clip_style(raw):
    """Validate an edit/export style payload: {preset, overrides}, with backward
    compatibility for the old flat {highlight_color, text_color, uppercase} keys."""
    from .caption_styles import PRESETS

    bs = raw if isinstance(raw, dict) else {}
    preset = bs.get("preset") if bs.get("preset") in PRESETS else None
    overrides = clean_overrides(bs.get("overrides"))
    if preset is None:
        for key in ("highlight_color", "text_color"):
            if isinstance(bs.get(key), str) and HEX.match(bs[key]):
                overrides[key] = bs[key]
        if "uppercase" in bs:
            overrides["uppercase"] = bool(bs["uppercase"])
    return {"preset": preset, "overrides": overrides}


def _ov_int(v, lo, hi):
    try:
        v = int(v)
    except (TypeError, ValueError):
        return None
    return v if lo <= v <= hi else None


_OV_INT_RANGES = {"font_size": (30, 140), "size": (30, 140), "outline": (0, 20),
                  "shadow": (0, 10), "blur": (0, 5), "box_opacity": (0, 100),
                  "pill_pad": (0, 30), "active_scale": (80, 200), "emphasis_scale": (80, 250),
                  "max_words_per_line": (1, 10)}
_OV_COLORS = {"highlight_color", "text_color", "outline_color", "pill_color", "pill_text", "box_color"}
_OV_CHOICE = {"position": ("lower", "center", "top"), "anim": ("pop", "none"),
              "highlight_mode": ("color", "pill"), "display": ("line", "word")}
_OV_BOOL = {"uppercase", "bold", "italic", "box", "strip_punct"}


def _font_allow():
    from .caption_styles import PRESETS

    fams = {"Arial"}
    for p in PRESETS.values():
        if p.get("font"):
            fams.add(p["font"])
        if p.get("font_ar"):
            fams.add(p["font_ar"])
    return fams


def clean_overrides(ov):
    ov = ov if isinstance(ov, dict) else {}
    out = {}
    for k, v in ov.items():
        if k in _OV_COLORS:
            if isinstance(v, str) and HEX.match(v):
                out[k] = v
        elif k == "font":
            if v in _font_allow():
                out[k] = v
        elif k == "min_gap":
            try:
                fv = float(v)
            except (TypeError, ValueError):
                continue
            if fv in (0.28, 0.22, 0.16):
                out[k] = fv
        elif k == "word_colors":
            if isinstance(v, list):
                cols = [c for c in v if isinstance(c, str) and HEX.match(c)][:6]
                if cols:
                    out[k] = cols
        elif k in _OV_INT_RANGES:
            lo, hi = _OV_INT_RANGES[k]
            vv = _ov_int(v, lo, hi)
            if vv is not None:
                out[k] = vv
        elif k in _OV_CHOICE:
            if v in _OV_CHOICE[k]:
                out[k] = v
        elif k in _OV_BOOL:
            out[k] = bool(v)
    return out


def clean_job_settings(raw):
    from .caption_styles import PRESETS

    raw = raw if isinstance(raw, dict) else {}
    cs = raw.get("caption_style") if isinstance(raw.get("caption_style"), dict) else {}
    legacy_ov = {}
    if "highlight_color" in cs:
        legacy_ov["highlight_color"] = _color(cs.get("highlight_color"), "#FFE600")
    if "text_color" in cs:
        legacy_ov["text_color"] = _color(cs.get("text_color"), "#FFFFFF")
    if "font_size" in cs:
        legacy_ov["font_size"] = _int(cs.get("font_size"), 30, 140, 72)
    if "uppercase" in cs:
        legacy_ov["uppercase"] = bool(cs.get("uppercase"))
    merged_ov = {**legacy_ov, **clean_overrides(cs.get("overrides"))}
    return {
        "clips": _int(raw.get("clips"), 1, 20, 5),
        "duration": _int(raw.get("duration"), 15, 170, 45),
        "platform": raw.get("platform") if raw.get("platform") in ("shorts", "reels", "both") else "shorts",
        "layout": raw.get("layout") if raw.get("layout") in ("crop", "blur_fit") else "crop",
        "captions": bool(raw.get("captions", True)),
        "use_llm": bool(raw.get("use_llm", True)),
        "zoom": bool(raw.get("zoom", False)),
        "caption_style": {
            "preset": cs.get("preset") if cs.get("preset") in PRESETS else "bold-pop",
            "overrides": merged_ov,
        },
    }


def job_overrides(s):
    return {
        "captions": {"enabled": s["captions"], **s["caption_style"]},
        "zoom": {"enabled": s["zoom"]},
    }


def clean_global_settings(raw):
    raw = raw if isinstance(raw, dict) else {}
    w, l, r, c = (raw.get(k) if isinstance(raw.get(k), dict) else {} for k in ("whisper", "llm", "render", "captions"))
    ck = raw.get("cookies") if isinstance(raw.get("cookies"), dict) else {}
    lang = str(w.get("language") or "").strip().lower()
    host = str(l.get("host") or "").strip()
    browsers = ("chrome", "firefox", "edge", "brave", "safari")
    cfb = str(ck.get("from_browser") or "").strip().lower()
    cfile = str(ck.get("cookiefile") or "").strip()
    pace = c.get("min_gap", c.get("pace", 0.22))
    try:
        pace = float(pace)
    except (TypeError, ValueError):
        pace = 0.22
    if pace not in (0.28, 0.22, 0.16):
        pace = 0.22
    cleaned = {
        "cookies": {
            "from_browser": cfb if cfb in browsers else "",
            "cookiefile": cfile if cfile and Path(cfile).expanduser().exists() else "",
        },
        "whisper": {
            "model": w.get("model") if w.get("model") in WHISPER_MODELS else "auto",
            "device": w.get("device") if w.get("device") in ("auto", "cuda", "cpu") else "auto",
            "language": lang if re.fullmatch(r"[a-z]{2,3}", lang) else None,
            "quality": w.get("quality") if w.get("quality") in WHISPER_QUALITIES else "fast",
        },
        "llm": {
            "enabled": bool(l.get("enabled", True)),
            "model": (str(l.get("model") or "").strip()[:100] or "llama3.1:8b"),
            "host": host if re.match(r"^https?://", host) else "http://localhost:11434",
        },
        "render": {
            "encoder": r.get("encoder") if r.get("encoder") in ("auto", "libx264", "h264_nvenc") else "auto",
            "loudnorm": bool(r.get("loudnorm", True)),
        },
        "captions": {"font": (str(c.get("font") or "").strip()[:60] or "Arial"),
                     "min_gap": pace},
    }
    ex = raw.get("export") if isinstance(raw.get("export"), dict) else {}
    q = str(ex.get("default_quality") or "").strip()
    if q not in ("480p", "720p", "1080p", "1440p", "source"):
        q = "1080p"
    cleaned["export"] = {"default_quality": q}
    return cleaned


# --------------------------------------------------------------------------- app state

def error_text(e):
    """What a failed job shows: user-facing messages as written, anything else with its type."""
    if getattr(e, "user_facing", False):
        return str(e)[:1500]
    return f"{type(e).__name__}: {str(e)[:1500]}"


class App:
    def __init__(self, home):
        self.home = Path(home).resolve()
        self.out = self.home / "output"
        self.work = self.home / "work"
        self.uploads = self.home / "uploads"
        self.probes = self.home / "probes"
        for d in (self.home, self.out, self.work, self.uploads, self.probes):
            d.mkdir(parents=True, exist_ok=True)
        probe.sweep()
        self.lock = threading.RLock()
        self.cancel = set()
        self.queue = queue.Queue()
        self.projects = {}
        self.saved_settings = {}
        self.model_dl = {"running": False, "done": [], "error": None}
        self.exports = {}
        self._ff = {"ffmpeg": bool(shutil.which("ffmpeg") and shutil.which("ffprobe")), "libass": False}
        try:
            fr = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True,
                                text=True, timeout=20, encoding="utf-8", errors="replace")
            self._ff["libass"] = " ass " in fr.stdout
        except Exception:
            pass
        self._sys = None
        self._sys_at = 0
        self._load()
        threading.Thread(target=self._worker, daemon=True, name="marrow-worker").start()

    # ---- persistence
    def _load(self):
        path = self.home / "projects.json"
        if path.exists():
            try:
                for p in json.loads(path.read_text(encoding="utf-8")):
                    if p.get("status") in ACTIVE:
                        p["status"] = "error"
                        p["error"] = "Interrupted: the app was closed while this was running. Use Regenerate to retry."
                    for c in p.get("clips", []):
                        if c.get("status") == "rendering":
                            c["status"] = "ready"
                    self.projects[p["id"]] = p
            except Exception as e:
                log.warning("Could not read projects.json (%s); starting empty.", e)
        spath = self.home / "settings.json"
        if spath.exists():
            try:
                self.saved_settings = json.loads(spath.read_text(encoding="utf-8"))
            except Exception:
                self.saved_settings = {}
        if isinstance(self.saved_settings, dict) and self.saved_settings.get("settings_version", 0) < 1:
            w = self.saved_settings.get("whisper")
            if isinstance(w, dict) and w.get("model") == "small":
                w["model"] = "auto"  # v0.3 default persisted; auto picks the fast model per language
            self.saved_settings["settings_version"] = 1
            try:
                spath.write_text(json.dumps(self.saved_settings, indent=2), encoding="utf-8")
            except OSError:
                pass

    def _save(self):
        path = self.home / "projects.json"
        tmp = path.with_suffix(".tmp")
        with self.lock:
            clean = []
            for p in self.projects.values():
                p = dict(p)
                p.pop("log", None)       # live-only, never persisted
                p.pop("scan", None)
                p.pop("candidates", None)
                clean.append(p)
            tmp.write_text(json.dumps(clean, ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(tmp, path)

    def config_for(self, job_settings=None, extra=None):
        cfg = load_config(str(self.home / "config.yaml"), overrides=self.saved_settings)
        cfg["cache_dir"] = str(self.work)
        if job_settings:
            cfg = deep_merge(cfg, job_overrides(job_settings))
        if extra:
            cfg = deep_merge(cfg, extra)
        return cfg

    # ---- serialization
    def public(self, p):
        vid = p.get("video_id")
        clips = []
        for c in p.get("clips", []):
            rev = c.get("rev", 0)
            # Live (in-progress) clips store absolute paths; URLs must only carry the file name.
            files = {pl: Path(str(fn)).name for pl, fn in (c.get("files") or {}).items()}
            thumb = Path(str(c["thumb"])).name if c.get("thumb") else None
            clips.append({
                "rank": c["rank"], "start": c["start"], "end": c["end"],
                "duration": c.get("duration", round(c["end"] - c["start"], 2)),
                "score": c["score"], "title": c.get("title", ""), "reason": c.get("reason", ""),
                "hashtags": c.get("hashtags", []), "status": c.get("status", "ready"),
                "last_error": c.get("last_error"), "platforms": list(files),
                "style": c.get("style"),
                "render_pct": c.get("render_pct", 0.0), "render_eta": c.get("render_eta"),
                "urls": {pl: f"/media/{vid}/{fn}?v={rev}" for pl, fn in files.items()},
                "thumb": f"/media/{vid}/{thumb}?v={rev}" if thumb else None,
                "shots": c.get("shots"),
            })
        clips.sort(key=lambda c: c["rank"])
        thumb = next((c["thumb"] for c in clips if c["thumb"]), None)
        keys = ("id", "name", "source", "source_kind", "status", "stage", "progress", "created",
                "started", "finished", "error", "video_id", "settings", "engine", "eta_sec", "eta_at",
                "locked")
        out = {k: p.get(k) for k in keys}
        out.update(clips=clips, thumb=thumb,
                   scan=p.get("scan"), candidates=p.get("candidates", []),
                   counts=p.get("counts"),
                   proxy=bool(vid and (self.work / vid / "proxy.mp4").exists()),
                   strip=bool(vid and (self.work / vid / "strip.jpg").exists()))
        return out

    def get(self, pid):
        p = self.projects.get(pid)
        if not p:
            raise ApiError("Project not found", 404)
        return p

    def clip(self, p, rank):
        for c in p.get("clips", []):
            if c["rank"] == rank:
                return c
        raise ApiError("Clip not found", 404)

    def media_path(self, p):
        if p.get("source_kind") == "url":
            if not p.get("video_id"):
                return None
            found, _ = _find_source(self.work / p["video_id"])
            return found
        sp = Path(p["source"])
        return sp if sp.exists() else None

    # ---- project actions
    def create_project(self, body):
        text = str(body.get("url") or "").strip()
        upload = body.get("upload")
        probe_id = body.get("probe_id")
        settings = clean_job_settings(body.get("settings"))
        if probe_id:
            pr = probe.get(str(probe_id))
            if not pr or pr["state"] != "ready" or not pr.get("info"):
                raise ApiError("Video preview is not ready yet. Wait for it to finish loading.")
            info = pr["info"]
            source, kind, name = info["url"], "url", info.get("title") or "video"
            try:  # publish the preview as this project's proxy now, so the scan panel has video instantly
                vid0 = slugify(info.get("video_id") or info["url"])
                wd = ensure_dir(Path(self.config_for(settings)["cache_dir"]) / vid0)
                d = Path(pr["dir"])
                prev = probe.preview_file(d)
                if prev is not None and not (wd / "proxy.mp4").exists():
                    atomic_copy(prev, wd / "proxy.mp4")
                if (d / "strip.jpg").exists() and not (wd / "strip.jpg").exists():
                    atomic_copy(d / "strip.jpg", wd / "strip.jpg")
            except Exception:
                log.exception("Probe copy failed")
        elif upload:
            path = self.uploads / Path(str(upload)).name
            if not path.exists():
                raise ApiError("Uploaded file not found. Upload it again.")
            source, kind, name = str(path), "upload", re.sub(r"^[0-9a-f]{8}_", "", path.stem)
        elif re.match(r"^https?://", text, re.I):
            source, kind = text, "url"
            u = urlparse(text)
            name = (u.netloc + u.path)[:80]
        elif text and Path(text).expanduser().is_file():
            path = Path(text).expanduser().resolve()
            source, kind, name = str(path), "file", path.stem
        else:
            raise ApiError("Paste a valid http(s) video link, or upload a video file.")
        pid = uuid.uuid4().hex[:10]
        p = {"id": pid, "name": name, "source": source, "source_kind": kind, "status": "queued",
             "stage": "Waiting in queue", "progress": 0.0, "created": time.time(), "started": None,
             "finished": None, "error": None, "video_id": None, "settings": settings, "clips": [],
             "locked": False,
             "probe_id": str(probe_id) if probe_id else None}
        with self.lock:
            self.projects[pid] = p
            self._save()
        self.queue.put(("pipeline", pid, {}))
        return self.public(p)

    def regenerate(self, pid, body):
        with self.lock:
            p = self.get(pid)
            if p["status"] in ACTIVE or any(c.get("status") == "rendering" for c in p["clips"]):
                raise ApiError("This project is busy. Wait for it to finish or cancel it first.", 409)
            if body.get("settings") is not None:
                p["settings"] = clean_job_settings(body["settings"])
            self.cancel.discard(pid)
            p.update(status="queued", stage="Waiting in queue", progress=0.0, error=None, finished=None)
            self._save()
        self.queue.put(("pipeline", pid, {}))
        return self.public(p)

    def cancel_project(self, pid):
        with self.lock:
            p = self.get(pid)
            if p["status"] not in ACTIVE:
                raise ApiError("Nothing to cancel.", 409)
            self.cancel.add(pid)
            if p["status"] == "queued":
                p.update(status="cancelled", stage="Cancelled", error=None)
            else:
                p["stage"] = "Cancelling… (stops at the next step)"
            self._save()
        return self.public(p)

    def delete_project(self, pid, purge):
        with self.lock:
            p = self.get(pid)
            if p.get("locked"):
                raise ApiError("Project is locked. Unlock it before deleting.", 409)
            if p["status"] == "running":
                raise ApiError("Cancel the running job before deleting this project.", 409)
            self.cancel.add(pid)  # a queued task for this id will be skipped
            vid = p.get("video_id")
            others = [q for q in self.projects.values() if q["id"] != pid and q.get("video_id") == vid]
            del self.projects[pid]
            self._save()
        if vid and not others:
            shutil.rmtree(self.out / vid, ignore_errors=True)
            if purge:
                shutil.rmtree(self.work / vid, ignore_errors=True)
        if purge and p.get("source_kind") == "upload":
            Path(p["source"]).unlink(missing_ok=True)
        return {"ok": True}

    def rename(self, pid, body):
        name = str(body.get("name") or "").strip()[:120]
        if not name:
            raise ApiError("Name can't be empty.")
        with self.lock:
            p = self.get(pid)
            p["name"] = name
            self._save()
        return self.public(p)

    def set_locked(self, pid, body):
        with self.lock:
            p = self.get(pid)
            p["locked"] = bool((body or {}).get("locked", not p.get("locked")))
            self._save()
        return self.public(p)

    def update_clip(self, pid, rank, body):
        with self.lock:
            p = self.get(pid)
            c = self.clip(p, rank)
            if "title" in body:
                title = str(body["title"]).strip()[:120]
                if not title:
                    raise ApiError("Title can't be empty.")
                c["title"] = title
                c["custom_title"] = True
            if "hashtags" in body:
                tags = body["hashtags"]
                if isinstance(tags, str):
                    tags = re.findall(r"[\w]+", tags)
                c["hashtags"] = [str(t).lstrip("#").lower() for t in tags][:15]
                c["custom_tags"] = True
            if "style" in body and isinstance(body["style"], dict):
                from .caption_styles import PRESETS

                st = body["style"]
                c["style"] = {
                    "preset": st.get("preset") if st.get("preset") in PRESETS else None,
                    "overrides": clean_overrides(st.get("overrides")),
                }
                c["custom_style"] = True
            if "framing" in body:
                fr = body["framing"]
                if fr in ("auto", "crop", "blur_fit", "stacked", "face"):
                    c["framing"] = fr
                    c["custom_style"] = True
            if "shot_layouts" in body and isinstance(body["shot_layouts"], dict):
                sl = {str(k): v for k, v in body["shot_layouts"].items()
                      if v in ("auto", "crop", "blur_fit", "stacked", "face")}
                c["shot_layouts"] = sl
                c["custom_style"] = True
            if "words" in body and isinstance(body["words"], dict):
                try:
                    _, raw = studio.load_words(self.work / p["video_id"])
                    studio.apply_edits(self.work / p["video_id"], raw, body["words"])
                except FileNotFoundError:
                    pass
            self._sync_manifest(p)
            self._save()
        return self.public(p)

    def delete_clip(self, pid, rank):
        with self.lock:
            p = self.get(pid)
            c = self.clip(p, rank)
            if c.get("status") == "rendering":
                raise ApiError("This clip is rendering right now.", 409)
            for fn in list(c["files"].values()) + ([c["thumb"]] if c.get("thumb") else []):
                (self.out / p["video_id"] / fn).unlink(missing_ok=True)
            p["clips"] = [x for x in p["clips"] if x["rank"] != rank]
            self._sync_manifest(p)
            self._save()
        return self.public(p)

    def transcript(self, pid, rank, start, end):
        p = self.get(pid)
        self.clip(p, rank)
        try:
            _, raw = studio.load_words(self.work / p["video_id"])
        except FileNotFoundError:
            raise ApiError("Transcript cache not found. Use Regenerate to rebuild it.", 404)
        return {"words": studio.words_in_range(raw, start, end)}

    def caption_preview(self, pid, rank, body):
        from .caption_styles import PRESETS

        p = self.get(pid)
        c = self.clip(p, rank)
        try:
            t = float(body.get("t", c["start"]))
        except (TypeError, ValueError):
            raise ApiError("t must be a number (seconds).")
        media = self.media_path(p)
        if not media:
            raise ApiError("The source video is no longer available on disk.", 409)
        st = body.get("style") if isinstance(body.get("style"), dict) else {}
        preset = st.get("preset") if st.get("preset") in PRESETS else p["settings"]["caption_style"].get("preset", "bold-pop")
        style = {"preset": preset, "overrides": clean_overrides(st.get("overrides"))}
        try:
            words, _raw = studio.load_words(self.work / p["video_id"])
        except FileNotFoundError:
            raise ApiError("Transcript cache not found. Use Regenerate to rebuild it.", 404)
        studio.attach_energy(self.work / p["video_id"], words)
        cfg = self.config_for(p["settings"])
        plats = list(c.get("files") or [p["settings"]["platform"]])
        from . import layout as _layout

        clip_shots = _layout.analyze(media, c["start"], c["end"], workdir=self.work / p["video_id"])
        clip_shots = studio.apply_shot_overrides(clip_shots, c.get("shot_layouts"))
        image = studio.render_caption_preview(cfg, media, self.work / p["video_id"], words,
                                              t, style, plats[0], p["settings"]["layout"],
                                              shots=clip_shots, clip_start=c["start"])
        return {"image": image}

    def queue_rerender(self, pid, rank, body):
        with self.lock:
            p = self.get(pid)
            c = self.clip(p, rank)
            if p["status"] in ACTIVE or c.get("status") == "rendering":
                raise ApiError("This project is busy. Try again in a moment.", 409)
            media = self.media_path(p)
            if not media:
                raise ApiError("The source video is no longer available on disk. Use Regenerate to download it again.", 409)
            try:
                start, end = round(float(body["start"]), 2), round(float(body["end"]), 2)
            except (KeyError, TypeError, ValueError):
                raise ApiError("Start and end must be numbers (seconds).")
            total = probe_duration(media)
            cfg = self.config_for(p["settings"])
            cap = min(cfg["platforms"][pl]["max_duration"] for pl in c["files"])
            if start < 0 or end > total + 0.01 or end - start < 5:
                raise ApiError(f"Choose a range inside the video ({total:.1f}s) that is at least 5 seconds long.")
            if end - start > cap:
                raise ApiError(f"Clips for {', '.join(c['files'])} can be at most {cap} seconds.")
            bs = body.get("style") if isinstance(body.get("style"), dict) else {}
            style = clean_clip_style(bs)
            args = {
                "rank": rank, "start": start, "end": min(end, total),
                "captions": bool(body.get("captions", True)), "style": style,
                "edits": body.get("edits") if isinstance(body.get("edits"), dict) else {},
                "timings": body.get("timings") if isinstance(body.get("timings"), dict) else {},
            }
            c.update(status="rendering", last_error=None)
            self._save()
        self.queue.put(("rerender", pid, args))
        return self.public(p)

    # ---- worker
    def _worker(self):
        while True:
            kind, pid, args = self.queue.get()
            try:
                if kind == "pipeline":
                    self._run_pipeline(pid)
                else:
                    self._run_rerender(pid, **args)
            except Exception:  # never let the worker die
                log.exception("Worker task failed")
            finally:
                self.queue.task_done()

    def _run_pipeline(self, pid):
        hw.reset()
        hw.set_stage("starting")
        with self.lock:
            p = self.projects.get(pid)
            if p is None:
                self.cancel.discard(pid)
                return
            if pid in self.cancel:
                self.cancel.discard(pid)
                p.update(status="cancelled", stage="Cancelled")
                self._save()
                return
            p.update(status="running", stage="Starting", progress=0.0, error=None, started=time.time())
            self._save()
            settings, source = dict(p["settings"]), p["source"]

        def have_source(src, duration):
            with self.lock:
                if p.get("source_kind") == "url" and src.title:
                    p["name"] = src.title
                if src.video_id and not p.get("video_id"):
                    p["video_id"] = src.video_id  # early: scan/proxy routes work mid-run
            threading.Thread(target=self._build_proxy,
                             args=(pid, str(src.path), str(src.workdir), duration),
                             daemon=True, name="marrow-proxy").start()

        def progress(stage, frac, *, log=None, scan=None, candidates=None, clips=None, counts=None):
            if pid in self.cancel:
                raise Cancelled()
            with self.lock:
                p["stage"], p["progress"] = stage, round(float(frac), 3)
                hw.set_stage(stage)
                if log:
                    L = p.setdefault("log", [])
                    L.extend(log if isinstance(log, list) else [log])
                    del L[:-300]
                if scan is not None:
                    p["scan"] = scan
                if candidates is not None:
                    p["candidates"] = candidates
                if clips is not None:
                    p["clips"] = clips
                if counts is not None:
                    p["counts"] = counts
                e = eta_holder.get("eta")
                if e is not None:
                    p["eta_sec"] = round(e.remaining(), 1)
                    p["eta_at"] = time.time()

        try:
            from .pipeline import run_pipeline  # heavy imports happen here, not at server start

            cfg = self.config_for(settings)
            eta_holder = {}
            results = run_pipeline(
                source, output_dir=str(self.out), config=cfg, clip_count=settings["clips"],
                clip_duration=settings["duration"], platform=settings["platform"],
                layout=settings["layout"], use_llm=settings["use_llm"], progress=progress,
                on_source=have_source, eta_holder=eta_holder,
            )
            if "eta" in eta_holder:
                eta_holder["eta"].finish()
            if not results:
                raise RuntimeError("No clips were produced.")
            first_file = Path(next(iter(results[0]["files"].values())))
            vid = first_file.parent.name
            out_dir = self.out / vid
            title = p["name"]
            try:
                title = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8")).get("title") or title
            except Exception:
                pass
            clips = []
            for r in results:
                files = {pl: Path(fp).name for pl, fp in r["files"].items()}
                thumb = f"clip_{r['rank']:02d}.jpg"
                has_thumb = studio.make_thumb(next(iter(r["files"].values())), out_dir / thumb)
                clips.append({
                    "rank": r["rank"], "start": r["start"], "end": r["end"], "duration": r["duration"],
                    "score": r["score"], "title": r["title"], "reason": r["reason"],
                    "hashtags": r["hashtags"], "files": files, "thumb": thumb if has_thumb else None,
                    "shots": r.get("shots"),
                    "rev": int(time.time()), "status": "ready", "last_error": None,
                })
            keep = {fn for c in clips for fn in list(c["files"].values()) + ([c["thumb"]] if c["thumb"] else [])}
            keep.add("manifest.json")
            for f in out_dir.glob("clip_*"):
                if f.name not in keep:
                    f.unlink(missing_ok=True)
            with self.lock:
                old = list(p.get("clips", []))
                for c in clips:
                    best, best_ov = None, 0.0
                    for o in old:
                        try:
                            ov = min(c["end"], o["end"]) - max(c["start"], o["start"])
                        except (KeyError, TypeError):
                            continue
                        if ov > best_ov:
                            best, best_ov = o, ov
                    if best and best_ov > 0:
                        if best.get("custom_title"):
                            c["title"] = best["title"]
                            c["custom_title"] = True
                        if best.get("custom_tags"):
                            c["hashtags"] = best["hashtags"]
                            c["custom_tags"] = True
                        if best.get("custom_style") and best.get("style"):
                            c["style"] = best["style"]
                            c["custom_style"] = True
                p.update(status="done", stage="Done", progress=1.0, video_id=vid, name=title, clips=clips,
                         finished=time.time(), engine=hw.get_engine()["engines"])
                self._clear_live(p)
                self._sync_manifest(p)
                self._save()
        except Cancelled:
            with self.lock:
                self.cancel.discard(pid)
                p.update(status="cancelled", stage="Cancelled")
                self._save()
        except Exception as e:
            log.exception("Pipeline failed")
            with self.lock:
                p.update(status="error", stage="Failed", error=error_text(e))
                self._clear_live(p)
                self._save()

    def _run_rerender(self, pid, rank, start, end, captions, style, edits, timings=None):
        with self.lock:
            p = self.projects.get(pid)
            if p is None:
                return
            c = self.clip(p, rank)
            vid, files = p["video_id"], dict(c["files"])
        try:
            workdir, out_dir = self.work / vid, self.out / vid
            words, raw = studio.load_words(workdir)
            if (edits or timings) and studio.apply_edits(workdir, raw, edits, timings):
                words, raw = studio.load_words(workdir)
            studio.attach_energy(workdir, words)
            cfg = self.config_for(p["settings"])
            base_caps = dict(cfg["captions"])
            base_caps.update({"preset": style.get("preset") or cfg["captions"].get("preset"),
                              "overrides": style.get("overrides") or {}})
            cfg["captions"] = base_caps
            media = self.media_path(p)
            if not media:
                raise RuntimeError("Source video is missing on disk.")
            from . import layout as _layout

            shots = _layout.analyze(media, start, end, workdir=workdir)
            shots = studio.apply_shot_overrides(shots, c.get("shot_layouts"))
            produced = studio.render_clip_files(cfg, media, workdir, words, rank, start, end,
                                                list(files), out_dir, captions, shots)
            thumb = f"clip_{rank:02d}.jpg"
            has_thumb = studio.make_thumb(next(iter(produced.values())), out_dir / thumb)
            with self.lock:
                c.update(start=start, end=end, duration=round(end - start, 2), rev=int(time.time() * 1000),
                         status="ready", last_error=None, thumb=thumb if has_thumb else c.get("thumb"),
                         shots=shots,
                         style={"preset": style.get("preset"), "overrides": style.get("overrides", {})},
                         custom_style=True)
                self._sync_manifest(p)
                self._save()
        except Exception as e:
            log.exception("Re-render failed")
            with self.lock:
                c.update(status="ready", last_error=f"{type(e).__name__}: {str(e)[:800]}")
                self._save()

    def _sync_manifest(self, p):
        """Keep output/<id>/manifest.json in line with edits made in the UI."""
        vid = p.get("video_id")
        if not vid:
            return
        data = {"source": p["source"], "title": p["name"], "clips": [{
            "rank": c["rank"], "start": c["start"], "end": c["end"], "duration": c["duration"],
            "score": c["score"], "title": c["title"], "reason": c.get("reason", ""),
            "hashtags": c.get("hashtags", []), "shots": c.get("shots"),
            "files": {pl: str(self.out / vid / fn) for pl, fn in c["files"].items()},
        } for c in sorted(p["clips"], key=lambda c: c["rank"])]}
        try:
            (self.out / vid / "manifest.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    # ---- exports
    def clean_export_spec(self, raw):
        from .caption_styles import PRESETS

        raw = raw if isinstance(raw, dict) else {}
        st = raw.get("style") if isinstance(raw.get("style"), dict) else {}
        adv = raw.get("advanced") if isinstance(raw.get("advanced"), dict) else {}
        try:
            fps = int(adv.get("fps") or 0)
        except (TypeError, ValueError):
            fps = 0

        def _provided(v):
            return v is not None and (not isinstance(v, str) or v.strip() != "")

        def _num_strict(v, lo, hi, err):
            if not _provided(v):
                return None
            try:
                f = float(v)
            except (TypeError, ValueError):
                raise ApiError(err, 400)
            if not (lo <= f <= hi):
                raise ApiError(err, 400)
            return f

        crf = _num_strict(adv.get("crf"), 16, 32, "Invalid CRF value (16-32)")
        mbps = _num_strict(adv.get("video_mbps"), 1, 80, "Bitrate out of bounds (1-80 Mbps)")
        ab = _num_strict(adv.get("audio_kbps"), 64, 320, "Invalid audio bitrate (64-320 kbps)")

        def _num(v, lo, hi):
            try:
                v = float(v)
            except (TypeError, ValueError):
                return None
            return v if lo <= v <= hi else None

        return {
            "format": raw.get("format") if raw.get("format") in ("mp4", "mov") else "mp4",
            "quality": raw.get("quality") if raw.get("quality") in (
                "480p", "720p", "1080p", "1440p", "source") else "1080p",
            "captions": bool(raw.get("captions", True)),
            "style": {"preset": st.get("preset") if st.get("preset") in PRESETS else None,
                      "overrides": clean_overrides(st.get("overrides", {}))},
            "framing": raw.get("framing") if raw.get("framing") in (
                "auto", "crop", "blur_fit", "stacked", "face") else "auto",
            "advanced": {"fps": fps if fps in (30, 60) else 0,
                         "crf": crf,
                         "video_mbps": mbps,
                         "audio_kbps": ab},
        }

    def export_cache_key(self, c, spec, edits=None):
        import hashlib

        blob = json.dumps([c.get("rank"), round(c.get("start", 0), 2), round(c.get("end", 0), 2),
                           c.get("rev", 0), c.get("style"), spec, edits or {}],
                          sort_keys=True)
        return hashlib.sha1(blob.encode()).hexdigest()[:12]

    def _export_words(self, workdir, edits):
        """Words with export-scoped text edits applied in memory (never persisted)."""
        words, _raw = studio.load_words(workdir)
        if not edits:
            return words
        out = []
        for idx, w in enumerate(words):
            t = edits.get(str(idx), edits.get(idx))
            if t is None:
                out.append(w)
            elif str(t).strip():
                w.text = str(t).strip()[:40]
                out.append(w)
            # empty text -> word dropped from this export only
        return out

    def start_export(self, pid, rank, body):
        import uuid as _uuid

        with self.lock:
            p = self.get(pid)
            c = self.clip(p, rank)
            if not p.get("video_id"):
                raise ApiError("Nothing to export yet.", 409)
            spec = self.clean_export_spec(body)
            spec["platform"] = (c.get("platforms") or [p["settings"]["platform"]])[0]
            if not spec["style"]["preset"]:
                saved = c.get("style") or {}
                spec["style"] = {
                    "preset": saved.get("preset") or p["settings"]["caption_style"].get("preset", "bold-pop"),
                    "overrides": saved.get("overrides") or p["settings"]["caption_style"].get("overrides", {}),
                }
            if not spec["framing"] and c.get("framing") in ("auto", "crop", "blur_fit", "stacked", "face"):
                spec["framing"] = None if c["framing"] == "auto" else c["framing"]
            key = self.export_cache_key(
                c, spec, body.get("edits") if isinstance(body.get("edits"), dict) else {})
            ext = ".mov" if spec["format"] == "mov" else ".mp4"
            dest = ensure_dir(self.out / p["video_id"] / "exports") / f"clip_{rank:02d}_{key}{ext}"
            job = _uuid.uuid4().hex[:10]
            self.exports[job] = {"id": job, "pid": pid, "rank": rank, "state": "queued",
                                 "progress": 0.0, "file": None, "error": None, "encoder": None,
                                 "spec": spec, "key": key,
                                 "edits": body.get("edits") if isinstance(body.get("edits"), dict) else {}}
        if dest.exists():
            with self.lock:
                self.exports[job].update(state="done", progress=1.0, file=str(dest), encoder="cached")
            return self.exports[job]
        threading.Thread(target=self._run_export, args=(job,), daemon=True,
                         name=f"marrow-export-{job}").start()
        return self.exports[job]

    def _run_export(self, job):
        with self.lock:
            j = self.exports.get(job)
            if not j:
                return
            p = self.projects.get(j["pid"])
            c = self.clip(p, j["rank"]) if p else None
            if not p or not c:
                j.update(state="error", error="Project or clip is gone.")
                return
            j["state"] = "running"
            spec, vid = dict(j["spec"]), p["video_id"]
            edits = dict(j.get("edits") or {})
        try:
            workdir, out_dir = self.work / vid, self.out / vid
            words = self._export_words(workdir, edits)
            studio.attach_energy(workdir, words)
            cfg = self.config_for(p["settings"])
            media = self.media_path(p)
            if not media:
                raise RuntimeError("Source video is missing on disk.")
            ext = ".mov" if spec["format"] == "mov" else ".mp4"
            dest = ensure_dir(out_dir / "exports") / f"clip_{j['rank']:02d}_{j['key']}{ext}"
            t0 = time.time()

            def prog(frac):
                el = time.time() - t0
                left = el / frac * (1 - frac) if frac > 0.05 else None
                with self.lock:
                    j["progress"] = round(frac, 3)
                    j["eta"] = round(left, 1) if left else None

            fp, enc = studio.export_clip(cfg, media, workdir, words, j["rank"],
                                         c["start"], c["end"], spec, dest, prog,
                                         shots=c.get("shots"),
                                         overrides=c.get("shot_layouts"))
            with self.lock:
                j.update(state="done", progress=1.0, file=fp, encoder=enc, eta=None)
        except Exception as e:
            log.exception("Export failed")
            with self.lock:
                self.exports[job].update(state="error", error=f"{type(e).__name__}: {str(e)[:500]}")

    def start_batch_export(self, pid, body):
        import uuid as _uuid

        with self.lock:
            p = self.get(pid)
            if not p.get("clips"):
                raise ApiError("This project has no clips to export.", 409)
            spec = self.clean_export_spec(body)
            apply_all = bool(body.get("apply_to_all", True))
            wanted = body.get("clip_ids")
            ranks = [c["rank"] for c in p["clips"] if not wanted or c["rank"] in wanted]
            if not ranks:
                raise ApiError("No clips selected.", 400)
            job = _uuid.uuid4().hex[:10]
            self.exports[job] = {"id": job, "pid": pid, "rank": None, "state": "queued",
                                 "progress": 0.0, "file": None, "error": None,
                                 "encoder": None, "spec": spec, "batch": ranks,
                                 "apply_to_all": apply_all}
        threading.Thread(target=self._run_batch_export, args=(job,), daemon=True,
                         name=f"marrow-batch-{job}").start()
        return self.exports[job]

    def _run_batch_export(self, job):
        import zipfile as _zip

        with self.lock:
            j = self.exports.get(job)
            if not j:
                return
            p = self.projects.get(j["pid"])
            if not p:
                j.update(state="error", error="Project is gone.")
                return
            j["state"] = "running"
            spec, vid = dict(j["spec"]), p["video_id"]
            ranks, apply_all = list(j["batch"]), j["apply_to_all"]
        try:
            workdir, out_dir = self.work / vid, self.out / vid
            words, _raw = studio.load_words(workdir)
            studio.attach_energy(workdir, words)
            cfg = self.config_for(p["settings"])
            media = self.media_path(p)
            if not media:
                raise RuntimeError("Source video is missing on disk.")
            tmpdir = ensure_dir(out_dir / "exports" / f"batch_{job}")
            made = []
            for n, rank in enumerate(ranks):
                with self.lock:
                    c = self.clip(p, rank)
                one = dict(spec)
                if not apply_all:
                    saved = c.get("style") or {}
                    one["style"] = {"preset": saved.get("preset") or spec["style"]["preset"],
                                    "overrides": saved.get("overrides") or spec["style"]["overrides"]}
                one["platform"] = (c.get("platforms") or [p["settings"]["platform"]])[0]
                key = self.export_cache_key(c, one)
                ext = ".mov" if one["format"] == "mov" else ".mp4"
                dest = tmpdir / f"clip_{rank:02d}_{key}{ext}"
                if not dest.exists():
                    studio.export_clip(cfg, media, workdir, words, rank, c["start"], c["end"],
                                       one, dest, shots=c.get("shots"),
                                       overrides=c.get("shot_layouts"))
                made.append(dest)
                with self.lock:
                    self.exports[job]["progress"] = round((n + 1) / len(ranks), 3)
            zpath = out_dir / "exports" / f"batch_{job}.zip"
            with _zip.ZipFile(zpath, "w", _zip.ZIP_STORED) as z:
                for f in made:
                    z.write(f, f.name)
                mf = out_dir / "manifest.json"
                if mf.exists():
                    z.write(mf, "manifest.json")
            with self.lock:
                self.exports[job].update(state="done", progress=1.0, file=str(zpath))
        except Exception as e:
            log.exception("Batch export failed")
            with self.lock:
                self.exports[job].update(state="error", error=f"{type(e).__name__}: {str(e)[:500]}")

    # ---- misc
    MODELS_PRELOAD = ("tiny", "distil-large-v3", "large-v3-turbo")
    def _clear_live(self, p):
        """Drop live-only state on terminal transitions (error/done)."""
        for k in ("log", "scan", "candidates", "counts"):
            p.pop(k, None)

    def _build_proxy(self, pid, src_path, workdir, duration):
        try:
            wd = Path(workdir)
            proxy = wd / "proxy.mp4"
            if proxy.exists():
                if not _playable(proxy):  # e.g. left half-written by an older build
                    proxy.unlink(missing_ok=True)
                else:
                    if not (wd / "strip.jpg").exists():
                        studio.make_strip(proxy, wd)
                    return  # already have both (e.g. regenerate, or copied from a probe)
            with self.lock:
                p = self.projects.get(pid)
            if p and p.get("probe_id"):
                pr = probe.get(p["probe_id"])
                prev = probe.preview_file(Path(pr["dir"])) if pr else None
                if prev is not None:
                    atomic_copy(prev, proxy)
                    st = Path(pr["dir"]) / "strip.jpg"
                    if st.exists():
                        atomic_copy(st, wd / "strip.jpg")
                    return
            studio.make_proxy(src_path, workdir, duration)
        except Exception:
            log.exception("Proxy build failed")

    def start_model_download(self):
        with self.lock:
            if self.model_dl["running"]:
                raise ApiError("A model download is already running.", 409)
            self.model_dl.update(running=True, done=[], error=None)
        threading.Thread(target=self._download_models, daemon=True, name="marrow-models").start()
        return self.model_dl_status()

    def model_dl_status(self):
        with self.lock:
            return dict(self.model_dl)

    def _download_models(self):
        import gc as _gc

        try:
            from faster_whisper import WhisperModel

            from .transcriber import add_cuda_dll_dirs

            add_cuda_dll_dirs()
            total = len(self.MODELS_PRELOAD)
            for i, m in enumerate(self.MODELS_PRELOAD, 1):
                hw.set_stage(f"Downloading Whisper model {m} ({i}/{total})")
                model = WhisperModel(m, device="cpu", compute_type="int8")
                del model
                _gc.collect()
                with self.lock:
                    self.model_dl["done"].append(m)
        except Exception as e:
            log.exception("Model download failed")
            with self.lock:
                self.model_dl["error"] = f"{type(e).__name__}: {str(e)[:500]}"
        finally:
            with self.lock:
                self.model_dl["running"] = False

    def system(self, fresh=False):
        now = time.time()
        with self.lock:
            if self._sys and not fresh and now - self._sys_at < 10:
                return dict(self._sys)
        cfg = self.config_for()
        info = {
            "ffmpeg": self._ff["ffmpeg"],
            "libass": self._ff["libass"],
            "ollama": {"enabled": cfg["llm"]["enabled"], "host": cfg["llm"]["host"], "model": cfg["llm"]["model"],
                       "reachable": False, "model_ready": False, "models": []},
            "gpu": False,
            "gpu_error": None,
        }
        try:  # YouTube setup: yt-dlp version, JavaScript runtime, solver and cookies
            from . import diagnostics

            info["ytdlp"] = diagnostics.ytdlp_status()
            info["cookies"] = diagnostics.cookie_status(cfg["cookies"])
        except Exception as e:  # a broken check must never hide the rest of the status
            info["ytdlp"], info["cookies"] = {"error": f"{type(e).__name__}: {e}"}, {}
        try:
            from .transcriber import cuda_ready

            ok, why = cuda_ready()
            info["gpu"] = ok
            info["gpu_error"] = why or None
        except Exception as e:
            info["gpu_error"] = f"{type(e).__name__}: {e}"
        try:
            from .renderer import pick_encoder

            info["encoder"] = pick_encoder(cfg["render"].get("encoder", "auto"))
        except Exception:
            info["encoder"] = cfg["render"].get("encoder", "auto")
        try:
            import requests

            r = requests.get(cfg["llm"]["host"].rstrip("/") + "/api/tags", timeout=0.4)
            r.raise_for_status()
            names = [m.get("name", "") for m in r.json().get("models", [])]
            want = cfg["llm"]["model"]
            info["ollama"].update(reachable=True, models=names, model_ready=want in names or f"{want}:latest" in names)
        except Exception:
            pass
        with self.lock:
            self._sys, self._sys_at = info, time.time()
            return dict(info)

    def settings(self):
        cfg = self.config_for()
        return {
            "version": __version__, "home": str(self.home),
            "settings": {"whisper": {k: cfg["whisper"].get(k) for k in ("model", "device", "language", "quality")},
                         "llm": {k: cfg["llm"][k] for k in ("enabled", "model", "host")},
                         "render": {k: cfg["render"][k] for k in ("encoder", "loudnorm")},
                         "captions": {"font": cfg["captions"]["font"],
                                      "min_gap": cfg["captions"].get("min_gap", 0.22)},
                         "cookies": {"from_browser": cfg["cookies"].get("from_browser", ""),
                                     "cookiefile": cfg["cookies"].get("cookiefile", "")},
                         "export": {"default_quality": cfg.get("export", {}).get("default_quality", "1080p")}},
            "job_defaults": clean_job_settings({
                "clips": cfg["clip"]["target_count"], "duration": 45,
                "caption_style": {"preset": cfg["captions"].get("preset", "bold-pop"),
                                  "overrides": {}},
                "use_llm": cfg["llm"]["enabled"]}),
        }

    def save_settings(self, raw):
        cleaned = clean_global_settings(raw) if raw else {}
        with self.lock:
            self.saved_settings = cleaned
            (self.home / "settings.json").write_text(json.dumps(cleaned, indent=2), encoding="utf-8")
        return self.settings()

    def make_zip(self, pid):
        p = self.get(pid)
        if not p.get("clips"):
            raise ApiError("This project has no clips to export.", 409)
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
        tmp.close()
        with zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_STORED) as z:
            for c in p["clips"]:
                for fn in c["files"].values():
                    fp = self.out / p["video_id"] / fn
                    if fp.exists():
                        z.write(fp, fn)
            mf = self.out / p["video_id"] / "manifest.json"
            if mf.exists():
                z.write(mf, "manifest.json")
        return Path(tmp.name), slugify(p["name"]) + "_clips.zip"

    def open_folder(self, pid=None):
        target = self.home
        if pid:
            p = self.get(pid)
            if p.get("video_id"):
                target = self.out / p["video_id"]
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(target))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(target)])
            else:
                subprocess.Popen(["xdg-open", str(target)])
        except Exception as e:
            raise ApiError(f"Could not open the folder: {e}", 500)
        return {"ok": True, "path": str(target)}


# --------------------------------------------------------------------------- HTTP layer

ROUTES = []


def route(method, pattern):
    rx = re.compile(pattern)

    def deco(fn):
        ROUTES.append((method, rx, fn))
        return fn
    return deco


class Handler(BaseHTTPRequestHandler):
    app: App = None  # set in main()
    server_version = f"Marrow/{__version__}"

    def log_message(self, fmt, *args):  # keep the console readable
        pass

    # -- helpers
    def send_json(self, obj, status=200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def read_json(self, limit=5_000_000):
        n = int(self.headers.get("Content-Length") or 0)
        if n > limit:
            raise ApiError("Request too large", 413)
        if n == 0:
            return {}
        try:
            data = json.loads(self.rfile.read(n).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise ApiError("Invalid JSON body")
        return data if isinstance(data, dict) else {}

    def host_ok(self):
        bound = self.server.server_address[0]
        if bound not in ("127.0.0.1", "::1", "localhost"):
            return True  # user explicitly exposed the server; Host check doesn't apply
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
        return host in LOOPBACK_HOSTS

    def send_file(self, path, download_name=None, delete_after=False, ctype=None):
        size = path.stat().st_size
        ctype = ctype or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        start, end, status = 0, size - 1, 200
        rng = self.headers.get("Range")
        if rng:
            m = re.match(r"bytes=(\d*)-(\d*)$", rng.strip())
            if m and (m.group(1) or m.group(2)):
                if m.group(1):
                    start = int(m.group(1))
                    end = int(m.group(2)) if m.group(2) else size - 1
                else:  # suffix range: last N bytes
                    start = max(0, size - int(m.group(2)))
                end = min(end, size - 1)
                if start > end or start >= size:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                status = 206
        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-cache")
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        if download_name:
            safe = re.sub(r'[^A-Za-z0-9._-]+', "_", download_name)
            self.send_header("Content-Disposition", f'attachment; filename="{safe}"')
        self.end_headers()
        try:
            with open(path, "rb") as f:
                f.seek(start)
                left = length
                while left > 0:
                    chunk = f.read(min(1 << 20, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass
        finally:
            if delete_after:
                path.unlink(missing_ok=True)

    def dispatch(self, method):
        u = urlparse(self.path)
        path, q = unquote(u.path), parse_qs(u.query)
        try:
            if not self.host_ok():
                raise ApiError("Forbidden host", 403)
            if method != "GET" and self.headers.get("X-Marrow") != "1":
                raise ApiError("Missing X-Marrow header", 403)
            for m, rx, fn in ROUTES:
                if m == method:
                    mm = rx.fullmatch(path)
                    if mm:
                        return fn(self, q, *mm.groups())
            raise ApiError("Not found", 404)
        except ApiError as e:
            self._safe_json({"error": e.msg}, e.status)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass
        except Exception as e:
            log.exception("Unhandled error")
            self._safe_json({"error": f"{type(e).__name__}: {e}"}, 500)

    def _safe_json(self, obj, status):
        try:
            self.send_json(obj, status)
        except Exception:
            pass

    def do_GET(self):
        self.dispatch("GET")

    def do_POST(self):
        self.dispatch("POST")

    def do_PUT(self):
        self.dispatch("PUT")

    def do_PATCH(self):
        self.dispatch("PATCH")

    def do_DELETE(self):
        self.dispatch("DELETE")


@route("GET", r"/")
def r_index(h, q):
    html = (WEB_DIR / "index.html").read_bytes()
    h.send_response(200)
    h.send_header("Content-Type", "text/html; charset=utf-8")
    h.send_header("Content-Length", str(len(html)))
    h.send_header("Cache-Control", "no-store")
    h.end_headers()
    h.wfile.write(html)


@route("GET", r"/api/projects")
def r_list(h, q):
    with h.app.lock:
        items = sorted(h.app.projects.values(), key=lambda p: p["created"], reverse=True)
        h.send_json({"projects": [h.app.public(p) for p in items]})


@route("GET", r"/api/projects/([0-9a-f]+)")
def r_get(h, q, pid):
    with h.app.lock:
        pub = h.app.public(h.app.get(pid))
        full = h.app.projects[pid].get("log", [])
        try:
            n = int((q.get("log_from") or ["0"])[0])
        except ValueError:
            n = 0
        n = max(0, n)
        pub["log"] = full[n:]
        pub["log_total"] = len(full)
    h.send_json(pub)


@route("POST", r"/api/projects")
def r_create(h, q):
    h.send_json(h.app.create_project(h.read_json()), 201)


@route("POST", r"/api/upload")
def r_upload(h, q):
    name = Path(unquote((q.get("filename") or [""])[0])).name
    suffix = Path(name).suffix.lower()
    if suffix not in UPLOAD_SUFFIXES:
        raise ApiError("Unsupported file type. Use " + ", ".join(sorted(UPLOAD_SUFFIXES)) + ".")
    n = int(h.headers.get("Content-Length") or 0)
    if n <= 0:
        raise ApiError("Empty upload.")
    stored = f"{uuid.uuid4().hex[:8]}_{slugify(Path(name).stem)}{suffix}"
    dest = h.app.uploads / stored
    left = n
    try:
        with open(dest, "wb") as f:
            while left > 0:
                chunk = h.rfile.read(min(1 << 20, left))
                if not chunk:
                    break
                f.write(chunk)
                left -= len(chunk)
        if left:
            raise ApiError("Upload was interrupted.")
    except Exception:
        dest.unlink(missing_ok=True)
        raise
    h.send_json({"upload": stored, "size": n, "name": name}, 201)


@route("POST", r"/api/projects/([0-9a-f]+)/regenerate")
def r_regen(h, q, pid):
    h.send_json(h.app.regenerate(pid, h.read_json()))


@route("POST", r"/api/projects/([0-9a-f]+)/cancel")
def r_cancel(h, q, pid):
    h.send_json(h.app.cancel_project(pid))


@route("DELETE", r"/api/projects/([0-9a-f]+)")
def r_delete(h, q, pid):
    h.send_json(h.app.delete_project(pid, (q.get("purge") or ["0"])[0] == "1"))


@route("POST", r"/api/projects/([0-9a-f]+)/lock")
def r_lock(h, q, pid):
    h.send_json(h.app.set_locked(pid, h.read_json()))


@route("PATCH", r"/api/projects/([0-9a-f]+)")
def r_rename(h, q, pid):
    h.send_json(h.app.rename(pid, h.read_json()))


@route("PATCH", r"/api/projects/([0-9a-f]+)/clips/(\d+)")
def r_clip_patch(h, q, pid, rank):
    h.send_json(h.app.update_clip(pid, int(rank), h.read_json()))


@route("DELETE", r"/api/projects/([0-9a-f]+)/clips/(\d+)")
def r_clip_delete(h, q, pid, rank):
    h.send_json(h.app.delete_clip(pid, int(rank)))


@route("GET", r"/api/projects/([0-9a-f]+)/clips/(\d+)/pre.jpg")
def r_clip_pre(h, q, pid, rank):
    with h.app.lock:
        p = h.app.get(pid)
        vid = p.get("video_id")
    if not vid:
        raise ApiError("Not ready yet", 404)
    path = (h.app.work / vid / f"pre_{int(rank):02d}.jpg").resolve()
    if h.app.work.resolve() not in path.parents or not path.is_file():
        raise ApiError("Not ready yet", 404)
    h.send_file(path)


@route("GET", r"/api/projects/([0-9a-f]+)/waveform")
def r_waveform(h, q, pid):
    with h.app.lock:
        p = h.app.get(pid)
        vid = p.get("video_id")
    if not vid:
        raise ApiError("Not ready yet", 404)
    h.send_json(studio.waveform(h.app.work / vid))


@route("POST", r"/api/projects/([0-9a-f]+)/clips/(\d+)/export")
def r_export(h, q, pid, rank):
    h.send_json(h.app.start_export(pid, int(rank), h.read_json()), 202)


@route("GET", r"/api/projects/([0-9a-f]+)/exports/([0-9a-f]+)")
def r_export_status(h, q, pid, job):
    with h.app.lock:
        j = h.app.exports.get(job)
        if not j or j["pid"] != pid:
            raise ApiError("Export not found", 404)
        h.send_json({k: j.get(k) for k in ("id", "state", "progress", "eta", "error", "encoder")})


@route("GET", r"/api/projects/([0-9a-f]+)/exports/([0-9a-f]+)/file")
def r_export_file(h, q, pid, job):
    with h.app.lock:
        j = h.app.exports.get(job)
        if not j or j["pid"] != pid:
            raise ApiError("Export not found", 404)
        fp, state = j.get("file"), j.get("state")
    if state != "done" or not fp:
        raise ApiError("Export not ready yet", 409)
    path = Path(fp).resolve()
    if h.app.out.resolve() not in path.parents or not path.is_file():
        raise ApiError("File not found", 404)
    h.send_file(path, download_name=path.name)


@route("POST", r"/api/projects/([0-9a-f]+)/export")
def r_batch_export(h, q, pid):
    h.send_json(h.app.start_batch_export(pid, h.read_json()), 202)


@route("POST", r"/api/projects/([0-9a-f]+)/clips/(\d+)/rerender")
def r_rerender(h, q, pid, rank):
    h.send_json(h.app.queue_rerender(pid, int(rank), h.read_json()))


@route("GET", r"/api/projects/([0-9a-f]+)/clips/(\d+)/transcript")
def r_transcript(h, q, pid, rank):
    try:
        start, end = float(q["start"][0]), float(q["end"][0])
    except (KeyError, ValueError, IndexError):
        raise ApiError("start and end query parameters are required")
    h.send_json(h.app.transcript(pid, int(rank), start, end))


@route("GET", r"/api/projects/([0-9a-f]+)/zip")
def r_zip(h, q, pid):
    path, name = h.app.make_zip(pid)
    h.send_file(path, download_name=name, delete_after=True)


@route("POST", r"/api/open-folder")
def r_open(h, q):
    h.send_json(h.app.open_folder(h.read_json().get("project")))


@route("GET", r"/api/system")
def r_system(h, q):
    h.send_json(h.app.system((q.get("fresh") or ["0"])[0] == "1"))


@route("GET", r"/api/hardware")
def r_hw(h, q):
    from . import hw

    h.send_json(hw.snapshot())


@route("GET", r"/api/settings")
def r_settings(h, q):
    h.send_json(h.app.settings())


@route("PUT", r"/api/settings")
def r_settings_put(h, q):
    h.send_json(h.app.save_settings(h.read_json()))


@route("POST", r"/api/models/download")
def r_models_dl(h, q):
    h.send_json(h.app.start_model_download(), 202)


@route("GET", r"/api/models/download")
def r_models_dl_status(h, q):
    h.send_json(h.app.model_dl_status())


@route("GET", r"/api/caption-styles")
def r_styles(h, q):
    from .caption_styles import PRESETS, BASE

    h.send_json({"base": BASE, "presets": PRESETS})


@route("POST", r"/api/projects/([0-9a-f]+)/clips/(\d+)/caption-preview")
def r_cap_preview(h, q, pid, rank):
    h.send_json(h.app.caption_preview(pid, int(rank), h.read_json()))


@route("GET", r"/fonts/([A-Za-z0-9._-]+)")
def r_fonts(h, q, fname):
    from .caption_styles import FONTS_DIR, PRESETS

    allowed = {p.get("font_file") for p in PRESETS.values()} | {p.get("font_ar_file") for p in PRESETS.values()}
    if fname not in allowed:
        raise ApiError("File not found", 404)
    path = (FONTS_DIR / fname).resolve()
    if FONTS_DIR.resolve() not in path.parents or not path.is_file():
        raise ApiError("File not found", 404)
    h.send_file(path)


@route("POST", r"/api/probe")
def r_probe_start(h, q):
    url = str(h.read_json().get("url") or "").strip()
    if not re.match(r"^https?://", url, re.I):
        raise ApiError("Paste a valid http(s) video link.")
    h.send_json({"id": probe.start(url, h.app.probes, h.app.config_for())}, 202)


@route("GET", r"/api/probe/([0-9a-f]+)")
def r_probe_get(h, q, pid):
    pr = probe.get(pid)
    if not pr:
        raise ApiError("Probe not found", 404)
    info = pr.get("info") or {}
    thumb_local = (Path(pr["dir"]) / "thumb.jpg").exists()
    h.send_json({
        "state": pr["state"], "progress": pr.get("progress", 0), "error": pr.get("error"),
        "info": {k: info.get(k) for k in ("title", "channel", "duration", "live", "url", "video_id")} if info else None,
        "thumb": f"/api/probe/{pid}/thumb" if thumb_local else (info.get("thumbnail") if info else None),
        "preview": f"/api/probe/{pid}/preview" if pr["state"] == "ready" else None,
    })


@route("GET", r"/api/probe/([0-9a-f]+)/thumb")
def r_probe_thumb(h, q, pid):
    pr = probe.get(pid)
    if not pr:
        raise ApiError("Probe not found", 404)
    path = (Path(pr["dir"]) / "thumb.jpg").resolve()
    if h.app.probes.resolve() not in path.parents or not path.is_file():
        raise ApiError("Not ready yet", 404)
    h.send_file(path)


@route("GET", r"/api/probe/([0-9a-f]+)/preview")
def r_probe_preview(h, q, pid):
    pr = probe.get(pid)
    if not pr:
        raise ApiError("Probe not found", 404)
    found = probe.preview_file(Path(pr["dir"])) if pr["state"] == "ready" else None
    if found is None:
        raise ApiError("Not ready yet", 404)
    path = found.resolve()
    if h.app.probes.resolve() not in path.parents:
        raise ApiError("Not found", 404)
    h.send_file(path)


@route("GET", r"/api/projects/([0-9a-f]+)/proxy")
def r_proxy(h, q, pid):
    with h.app.lock:
        p = h.app.get(pid)
        vid = p.get("video_id")
    if not vid:
        raise ApiError("Not ready yet", 404)
    path = (h.app.work / vid / "proxy.mp4").resolve()
    if h.app.work.resolve() not in path.parents or not path.is_file():
        raise ApiError("Not ready yet", 404)
    h.send_file(path)


@route("GET", r"/api/projects/([0-9a-f]+)/strip")
def r_strip(h, q, pid):
    with h.app.lock:
        p = h.app.get(pid)
        vid = p.get("video_id")
    if not vid:
        raise ApiError("Not ready yet", 404)
    path = (h.app.work / vid / "strip.jpg").resolve()
    if h.app.work.resolve() not in path.parents or not path.is_file():
        raise ApiError("Not ready yet", 404)
    h.send_file(path)


@route("GET", r"/media/([\w.\-]+)/([\w.\-]+)")
def r_media(h, q, vid, fname):
    path = (h.app.out / vid / fname).resolve()
    if h.app.out not in path.parents or not path.is_file():
        raise ApiError("File not found", 404)
    dl = fname if (q.get("download") or ["0"])[0] == "1" else None
    h.send_file(path, download_name=dl)


@route("GET", r"/source/([\w.\-]+)")
def r_source(h, q, vid):
    with h.app.lock:
        p = next((x for x in h.app.projects.values() if x.get("video_id") == vid), None)
    media = h.app.media_path(p) if p else None
    if not media:
        raise ApiError("Source video not found", 404)
    h.send_file(media)


# --------------------------------------------------------------------------- entry point

def _playable(path):
    """True when ffprobe can read a duration from `path` (a finished, valid media file)."""
    try:
        return probe_duration(path) > 0
    except Exception:
        return False


@route("GET", r"/static/([\w.\-]+)")
def r_static(h, q, fname):
    ctype = STATIC_TYPES.get(Path(fname).suffix.lower())
    path = (WEB_DIR / fname).resolve()
    if not ctype or WEB_DIR.resolve() not in path.parents or not path.is_file():
        raise ApiError("File not found", 404)
    h.send_file(path, ctype=ctype)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="marrow-ui", description="Marrow web interface")
    ap.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1, local only)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--home", default=".", help="Folder for output/, work/, uploads/ and projects.json")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args(argv)

    os.environ.setdefault("PYTHONUTF8", "1")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        from .utils import require_ffmpeg

        require_ffmpeg()
    except RuntimeError as e:
        log.warning("WARNING: %s (the UI will start, but processing needs FFmpeg)", e)
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        log.warning("WARNING: bound to %s. This app has no login; anyone on your network can use it.", args.host)

    Handler.app = App(args.home)
    # Warm the real GPU probe once in the background so Settings opens instantly.
    def _warm():
        try:
            from .transcriber import cuda_ready, warm_models

            cuda_ready()
            warm_models()
        except Exception:
            pass
    threading.Thread(target=_warm, daemon=True, name="marrow-gpu-probe").start()
    server = None
    for port in range(args.port, args.port + 10):
        try:
            server = ThreadingHTTPServer((args.host, port), Handler)
            break
        except OSError:
            continue
    if server is None:
        sys.exit(f"Could not bind to ports {args.port}-{args.port + 9}.")
    shown = "localhost" if args.host in ("127.0.0.1", "0.0.0.0") else args.host
    url = f"http://{shown}:{server.server_address[1]}/"
    print(f"\n  Marrow is running at {url}\n  Data folder: {Handler.app.home}\n  Press Ctrl+C to stop.\n")
    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping…")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
