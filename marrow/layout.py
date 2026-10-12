"""Smart layout: shot detection + face tracking -> per-shot render layout.

Layouts: "stacked" (2 people, captions on the seam), "face" (1 person,
face-tracked crop), "blur_fit" (no faces). Falls back to the configured
crop/blur_fit when OpenCV or the model is unavailable (one warning only).
"""
import base64
import hashlib
import json
import math
import os
import re
import statistics
import subprocess
import threading
from pathlib import Path

from .utils import log, run_ffmpeg

MODEL_PATH = Path(__file__).parent / "assets" / "models" / "yunet_2023mar.onnx"
MODEL_REV = "47534e27c9851bb1128ccc0102f1145e27f23f98"
MODEL_SHA256 = "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"
MODEL_API_URL = ("https://api.github.com/repos/opencv/opencv_zoo/contents/models/"
                 f"face_detection_yunet/face_detection_yunet_2023mar.onnx?ref={MODEL_REV}")
MODEL_URL = ("https://github.com/opencv/opencv_zoo/raw/" + MODEL_REV + "/models/"
             "face_detection_yunet/face_detection_yunet_2023mar.onnx")
SAMPLE_FPS = 2.5
DETECT_MAX_WIDTH = 1280  # downscale 4K frames before YuNet; preserve original coordinates
MIN_FACE_W = 0.06      # fraction of frame width
MIN_SCORE = 0.6
PERSIST_FRAC = 0.60
SEPARATION = 0.20      # face-center distance (fraction of width) for "two people"
MIN_COEXISTENCE = 0.50 # both faces must be visible in the same frame for half the samples
MIN_STACK_SECONDS = 2.5 # skip fleeting detections and shot/reverse-shot transitions
CACHE_VERSION = 3
HOLD_MIN = 1.0         # hysteresis: a layout holds this long except at real cuts
EMA_ALPHA = 0.3
DEADBAND = 0.02
MAX_PAN = 0.20         # max crop-center travel, fraction of width per second

# Active-speaker focus (stacked layout): mouth motion + audio energy decide who
# is talking, so the renderer can push in on the right panel at the right time.
SPEAK_MOTION_FLOOR = 0.018   # normalized mouth motion needed to count as speech
SPEAK_MOTION_RATIO = 1.40    # the winner must out-move the other face by this ratio
SPEAK_ENERGY = 0.10          # normalized RMS below this counts as silence
SPEAK_MIN = 0.6              # focus intervals shorter than this are dropped
SPEAK_GAP = 0.45             # intervals separated by less than this are merged
ENERGY_FPS = 16000 / 512     # frames/sec of the cached energy.npy (audio_features.HOP)

_lock = threading.Lock()
_detector = {"det": None, "size": None, "warned": False, "tried_dl": False}


def _warn_once(msg, *args):
    with _lock:
        if not _detector["warned"]:
            _detector["warned"] = True
            log.warning(msg, *args)


def download_model():
    """One-time, best-effort fetch of the ~230 KB YuNet model. True on success."""
    import urllib.request

    try:
        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        log.debug("Face model directory is not writable: %s", e)
        return False

    data, expected_size = None, None
    try:
        req = urllib.request.Request(
            MODEL_API_URL,
            headers={"User-Agent": "marrow", "Accept": "application/vnd.github+json"},
        )
        with urllib.request.urlopen(req, timeout=45) as r:
            payload = json.loads(r.read().decode("utf-8"))
        expected_size = int(payload.get("size") or 0) or None
        if payload.get("encoding") != "base64" or not payload.get("content"):
            raise ValueError("GitHub API did not return the model contents")
        candidate = base64.b64decode(payload["content"])
        # OpenCV Zoo stores this model in Git LFS. The Contents API may return
        # the tiny LFS pointer instead of the ONNX bytes; don't mistake it for a
        # successful model, and fall through to the raw-file URL.
        if (len(candidate) < 100_000 or
                (expected_size is not None and len(candidate) != expected_size)):
            raise ValueError(f"GitHub API returned {len(candidate)} bytes, expected {expected_size}")
        if hashlib.sha256(candidate).hexdigest() != MODEL_SHA256:
            raise ValueError("GitHub API model checksum did not match the pinned YuNet file")
        data = candidate
    except Exception as api_error:
        log.debug("Face model API download failed: %s", api_error)

    if data is None:
        try:
            req = urllib.request.Request(MODEL_URL, headers={"User-Agent": "marrow"})
            with urllib.request.urlopen(req, timeout=45) as r:
                candidate = r.read()
            if len(candidate) < 100_000:
                raise ValueError(f"unexpected model size {len(candidate)}")
            if expected_size is not None and len(candidate) != expected_size:
                raise ValueError(f"expected {expected_size} model bytes, got {len(candidate)}")
            if hashlib.sha256(candidate).hexdigest() != MODEL_SHA256:
                raise ValueError("downloaded model checksum did not match the pinned YuNet file")
            data = candidate
        except Exception as e:
            log.debug("Face model download failed: %s", e)
            return False

    tmp = MODEL_PATH.with_name(MODEL_PATH.name + ".part")
    try:
        tmp.write_bytes(data)
        tmp.replace(MODEL_PATH)
        log.info("Downloaded the face-detection model (%d KB).", len(data) // 1024)
        return True
    except OSError as e:
        log.debug("Could not save the face-detection model: %s", e)
        return False
    finally:
        tmp.unlink(missing_ok=True)


def get_detector():
    """YuNet face detector, or None (with a one-time warning)."""
    with _lock:
        if _detector["det"] is not None:
            return _detector["det"]
    try:
        import cv2  # installed with Marrow; kept lazy to preserve fast server startup
    except ImportError:
        _warn_once("OpenCV is not installed; smart layout falls back to crop/blur_fit. "
                   "Install with: pip install opencv-python-headless")
        return None
    if not MODEL_PATH.exists() and not _detector["tried_dl"]:
        with _lock:
            _detector["tried_dl"] = True
        download_model()
    if not MODEL_PATH.exists():
        _warn_once("Face model %s is missing (auto-download failed); smart layout falls "
                   "back to crop/blur_fit.", MODEL_PATH)
        return None
    try:
        import cv2

        det = cv2.FaceDetectorYN.create(str(MODEL_PATH), "", (320, 320))
        with _lock:
            _detector["det"] = det
        return det
    except Exception as e:
        _warn_once("Face detector failed to load (%s); using crop/blur_fit.", e)
        return None


def detect_shots(src, start=0.0, end=None):
    """Scene cuts via ffmpeg select/scene. Returns sorted cut times (seconds)."""
    args = ["-ss", f"{max(0.0, start):.3f}", "-i", str(src)]
    if end is not None:
        args += ["-t", f"{max(0.1, end - start):.3f}"]
    args += ["-vf", "select='gte(scene,0.35)',showinfo", "-f", "null", "-"]
    cmd = ["ffmpeg", "-y", "-hide_banner", "-v", "info"] + [str(a) for a in args]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=600)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []
    cuts = []
    for m in re.finditer(r"pts_time:([0-9.]+)", p.stderr):
        try:
            cuts.append(start + float(m.group(1)))
        except ValueError:
            pass
    return sorted(cuts)


def sample_frames(src, start, end, fps=SAMPLE_FPS):
    """(t, bgr frame) samples via one forward decode (no repeated random seeks)."""
    try:
        import cv2
    except ImportError:
        return []
    cap = cv2.VideoCapture(str(src))
    if not cap.isOpened():
        cap.release()
        return []
    fps_src = cap.get(cv2.CAP_PROP_FPS) or 30.0
    if not math.isfinite(fps_src) or fps_src <= 0:
        fps_src = 30.0
    cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, start) * 1000.0)
    step = 1.0 / max(float(fps), 0.1)
    target, out = max(0.0, float(start)), []
    tolerance = 0.5 / fps_src
    last_t = -1.0
    try:
        while target < end:
            ok, frame = cap.read()
            if not ok or frame is None:
                break
            pos_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
            frame_no = cap.get(cv2.CAP_PROP_POS_FRAMES)
            t = (pos_ms / 1000.0 - 1.0 / fps_src) if pos_ms > 0 else (frame_no - 1) / fps_src
            if not math.isfinite(t) or t <= last_t:
                t = max(last_t + 1.0 / fps_src, (frame_no - 1) / fps_src)
            if t + tolerance >= target and t < end:
                out.append((max(0.0, t), frame))
                last_t = t
                target += step
                while target <= t + tolerance:
                    target += step
    finally:
        cap.release()
    return out


def detect_faces(frame, det):
    """[(x, y, w, h, score)] in original-frame pixels."""
    import cv2

    h, w = frame.shape[:2]
    input_frame = frame
    sx = sy = 1.0
    if w > DETECT_MAX_WIDTH:
        input_w = DETECT_MAX_WIDTH
        input_h = max(2, int(round(h * input_w / w)))
        input_frame = cv2.resize(frame, (input_w, input_h), interpolation=cv2.INTER_AREA)
        sx, sy = w / input_w, h / input_h
    ih, iw = input_frame.shape[:2]
    if _detector["size"] != (iw, ih):
        try:
            det.setInputSize((iw, ih))
        except Exception:
            pass
        with _lock:
            _detector["size"] = (iw, ih)
    try:
        _, faces = det.detect(input_frame)
    except Exception:
        return []
    if faces is None:
        return []
    out = []
    for f in faces:
        x, y, ww, hh, score = (float(v) for v in f[:5])
        x, ww = x * sx, ww * sx
        y, hh = y * sy, hh * sy
        if score >= MIN_SCORE and ww >= w * MIN_FACE_W:
            out.append((x, y, ww, hh, score))
    return out


def track(samples, frame_w):
    """Group per-sample detections into persistent tracks. Returns tracks as
    lists of (t, cx, cy, w, h)."""
    if not frame_w or frame_w <= 0:
        return []
    tracks = []
    for t, boxes in samples:
        used = set()
        for (x, y, w, h, _s) in boxes:
            cx, cy = x + w / 2, y + h / 2
            best, best_d = None, frame_w * 0.10
            for i, tr in enumerate(tracks):
                if i in used:
                    continue
                lx, ly = tr[-1][1], tr[-1][2]
                d = ((cx - lx) ** 2 + (cy - ly) ** 2) ** 0.5
                if d < best_d:
                    best, best_d = i, d
            if best is None:
                tracks.append([(t, cx, cy, w, h)])
            else:
                tracks[best].append((t, cx, cy, w, h))
                used.add(best)
    n = max(1, len(samples))
    return [tr for tr in tracks if len(tr) >= PERSIST_FRAC * n]


def smooth_centers(pts, frame_w):
    """EMA smoothing with deadband and max pan speed. pts: [(t, cx)]."""
    out = []
    cur = None
    for t, cx in pts:
        if cur is None:
            cur = cx
        else:
            target = cx if abs(cx - cur) > DEADBAND * frame_w else cur
            cur = EMA_ALPHA * target + (1 - EMA_ALPHA) * cur
            if out:
                dt = max(0.01, t - out[-1][0])
                max_step = MAX_PAN * frame_w * dt
                cur = min(max(cur, out[-1][1] - max_step), out[-1][1] + max_step)
        out.append((t, cur))
    return out


def decide(faces, frame_w, allow_split=True):
    """Choose a layout from persistent face centres and sizes.

    The automatic split is only a candidate here; ``analyze`` also requires the
    same pair to coexist in at least half the sampled frames before rendering it.
    """
    if len(faces) == 1:
        return "face"
    if len(faces) >= 2:
        separated = any(
            math.hypot(a[0] - b[0], a[1] - b[1]) >= SEPARATION * frame_w
            for i, a in enumerate(faces) for b in faces[i + 1:]
        )
        if separated:
            return "stacked" if allow_split else "face"
    return "blur_fit"


def _panel_order(faces, frame_w):
    """Stable top/bottom order: left then right, or top then bottom for vertical layouts."""
    faces = list(faces)
    if len(faces) < 2:
        return faces
    a, b = faces[:2]
    dx, dy = abs(a[0] - b[0]), abs(a[1] - b[1])
    axis = 0 if dx >= dy and dx >= SEPARATION * frame_w else 1
    return sorted(faces, key=lambda f: (f[axis], f[1 - axis]))


def _coexistence(track_a, track_b, sample_count):
    if sample_count <= 0:
        return 0.0
    a = {round(p[0], 3) for p in track_a}
    b = {round(p[0], 3) for p in track_b}
    return len(a & b) / float(sample_count)


def _select_split_pair(faces, frame_w, sample_count):
    """Best persistent, well-separated face pair that is genuinely on screen together."""
    best, best_score = None, None
    for i, a in enumerate(faces):
        for b in faces[i + 1:]:
            if math.hypot(a[0] - b[0], a[1] - b[1]) < SEPARATION * frame_w:
                continue
            together = _coexistence(a[3], b[3], sample_count)
            if together < MIN_COEXISTENCE:
                continue
            score = (together, min(len(a[3]), len(b[3])), a[2] + b[2])
            if best_score is None or score > best_score:
                best, best_score = (a, b), score
    return _panel_order(best, frame_w) if best else None


def _mouth_box(cx, cy, w, h):
    """Mouth region of a face box: middle-lower third, slightly narrowed."""
    return (int(cx - 0.28 * w), int(cy + 0.10 * h), int(cx + 0.28 * w), int(cy + 0.48 * h))


def _mouth_motion_frames(f0, f1, box, cv2):
    """Compare only the two tiny mouth patches instead of grayscaling full frames."""
    H, W = f0.shape[:2]
    x0, y0, x1, y1 = box
    x0 = max(0, min(x0, W - 2)); x1 = max(x0 + 1, min(x1, W))
    y0 = max(0, min(y0, H - 2)); y1 = max(y0 + 1, min(y1, H))
    a = cv2.cvtColor(f0[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY).astype("float32")
    b = cv2.cvtColor(f1[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY).astype("float32")
    return float(abs(a - b).mean()) / 255.0


def speaker_activity(frames, tracks, rms=None, energy_fps=ENERGY_FPS):
    """Who talks when, for a two-face stacked shot.

    frames: [(t, bgr)] samples of the shot; tracks: the two persistent face
    tracks (lists of (t, cx, cy, w, h)); rms: optional normalized audio energy.
    Returns [[start, end, panel], ...] with panel 0 = left face (top panel),
    1 = right face (bottom panel). Empty list when nobody clearly speaks —
    the renderer then keeps the static stacked layout.
    """
    if len(tracks) != 2 or len(frames) < 4:
        return []
    try:
        import cv2
    except ImportError:
        return []
    # Match the stable panel order (left-to-right, or top-to-bottom in a vertical two-shot).
    frame_w = frames[0][1].shape[1]
    centres = [(sum(p[1] for p in tr) / len(tr),
                sum(p[2] for p in tr) / len(tr), i) for i, tr in enumerate(tracks)]
    order = [entry[2] for entry in _panel_order(centres, frame_w)]
    maps = [{round(p[0], 3): p for p in tracks[i]} for i in order]
    labels = []
    for k in range(len(frames) - 1):
        (t0, f0), (t1, f1) = frames[k], frames[k + 1]
        mid = (t0 + t1) / 2
        if rms is not None:
            idx = int(mid * energy_fps)
            if idx >= len(rms) or float(rms[idx]) < SPEAK_ENERGY:
                continue
        mot = []
        for m in maps:
            p0, p1 = m.get(round(t0, 3)), m.get(round(t1, 3))
            if p0 is None or p1 is None:
                mot.append(0.0)
                continue
            box = _mouth_box((p0[1] + p1[1]) / 2, (p0[2] + p1[2]) / 2,
                             (p0[3] + p1[3]) / 2, (p0[4] + p1[4]) / 2)
            mot.append(_mouth_motion_frames(f0, f1, box, cv2))
        win = 0 if mot[0] >= mot[1] else 1
        if mot[win] < SPEAK_MOTION_FLOOR or mot[win] < SPEAK_MOTION_RATIO * mot[1 - win]:
            continue
        labels.append((t0, t1, win))
    merged = []
    for t0, t1, p in labels:
        if merged and merged[-1][2] == p and t0 - merged[-1][1] <= SPEAK_GAP:
            merged[-1][1] = t1
        else:
            merged.append([t0, t1, p])
    return [[round(s, 2), round(e, 2), p] for s, e, p in merged if e - s >= SPEAK_MIN]



def _panels(faces, W, H):
    """Two 9:8 cover crops: source-left/top first, the other participant second."""
    ordered = _panel_order(faces[:2], W)
    panels = []
    for cx, cy, w, _h in ordered:
        cw = min(float(W), max(w * 4.0, W * 0.45))
        ch = cw * 8.0 / 9.0
        if ch > H:
            ch = float(H)
            cw = ch * 9.0 / 8.0
        cw, ch = max(2, int(cw) // 2 * 2), max(2, int(ch) // 2 * 2)
        x = int(min(max(cx - cw / 2, 0.0), max(0.0, W - cw)))
        y = int(min(max(cy - 0.40 * ch, 0.0), max(0.0, H - ch)))
        x, y = x - (x % 2), y - (y % 2)
        panels.append({"x": x, "y": y, "w": cw, "h": ch})
    while len(panels) < 2:
        panels.append({"x": 0, "y": 0, "w": W - W % 2, "h": H - H % 2})
    return panels


def analyze(src, start, end, prefer=None, workdir=None, split_screen=True,
            fallback="blur_fit"):
    """Per-shot layouts for [start, end]. Returns [{start, end, layout, ...}].

    SPLIT follows the conservative two-shot rule used by OpenShorts: both
    persistent faces must coexist in at least half the sampled frames. This
    avoids showing one person twice in shot/reverse-shot edits. ``fallback`` is
    used when detection is unavailable or no stable face can be tracked.
    """
    if prefer in ("crop", "blur_fit"):
        return [{"start": round(start, 2), "end": round(end, 2), "layout": prefer}]
    fallback = fallback if fallback in ("crop", "blur_fit") else "blur_fit"

    cache = meta = None
    cache_signature = None
    if workdir is not None:
        suffix = "" if split_screen else "_no_split"
        cache = Path(workdir) / f"shots_{start:.0f}_{end:.0f}{suffix}.json"
        meta = cache.with_name(cache.name + ".meta.json")
        try:
            st = Path(src).stat()
            source_key = {"path": str(Path(src).resolve()), "size": st.st_size,
                          "mtime_ns": st.st_mtime_ns}
        except OSError:
            source_key = {"path": str(src), "size": None, "mtime_ns": None}
        cache_signature = {"version": CACHE_VERSION, **source_key,
                           "start": round(float(start), 3), "end": round(float(end), 3),
                           "split_screen": bool(split_screen), "fallback": fallback}
        if cache.exists() and meta.exists():
            try:
                saved_signature = json.loads(meta.read_text(encoding="utf-8"))
                shots = json.loads(cache.read_text(encoding="utf-8"))
                if saved_signature == cache_signature and isinstance(shots, list) and shots:
                    return shots
            except (OSError, ValueError, TypeError):
                pass

    det = get_detector()
    if det is None:
        return [{"start": round(start, 2), "end": round(end, 2), "layout": fallback}]
    import cv2

    probe = cv2.VideoCapture(str(src))
    try:
        _w = probe.get(cv2.CAP_PROP_FRAME_WIDTH)
        _h = probe.get(cv2.CAP_PROP_FRAME_HEIGHT)
        W = int(_w) if _w and _w > 0 else 1280
        H = int(_h) if _h and _h > 0 else 720
    finally:
        probe.release()

    cuts = [c for c in detect_shots(src, start, end) if start < c < end]
    bounds = [start] + cuts + [end]
    samples = sample_frames(src, start, end)
    rms = None
    if workdir is not None:                       # cached audio energy gates the mouth motion
        try:
            import numpy as np

            ecache = Path(workdir) / "energy.npy"
            if ecache.exists():
                rms = np.load(ecache)
        except Exception:
            rms = None
    by_shot, si = {}, 0
    for t, frame in samples:
        while si + 1 < len(bounds) - 1 and t >= bounds[si + 1]:
            si += 1
        by_shot.setdefault(si, []).append((t, frame))

    shots = []
    for i in range(len(bounds) - 1):
        s0, s1 = bounds[i], bounds[i + 1]
        fr = by_shot.get(i, [])
        dets = [(t, detect_faces(frame, det)) for t, frame in fr]
        tracks = track(dets, W)
        faces = []
        for tr in tracks:
            xs = [p[1] for p in tr]
            ys = [p[2] for p in tr]
            ws = [p[3] for p in tr]
            faces.append((statistics.median(xs), statistics.median(ys),
                          statistics.median(ws), tr))
        layout = decide([(f[0], f[1], f[2]) for f in faces], W,
                        allow_split=bool(split_screen))
        pair = None
        if layout == "stacked":
            pair = _select_split_pair(faces, W, len(fr))
            if s1 - s0 < MIN_STACK_SECONDS or pair is None:
                # Not a stable, simultaneous two-shot: keep a single tracked face.
                layout = decide([(f[0], f[1], f[2]) for f in faces], W, allow_split=False)
        if layout == "blur_fit":
            layout = fallback
        shot = {"start": round(s0, 2), "end": round(s1, 2), "layout": layout,
                "faces": len(faces)}
        if layout == "stacked" and pair:
            shot["panels"] = _panels([(f[0], f[1], f[2], 0) for f in pair], W, H)
            try:
                act = speaker_activity(fr, [f[3] for f in pair], rms)
                if act:
                    shot["active"] = act
            except Exception:
                log.debug("active-speaker detection failed", exc_info=True)
        elif layout == "face":
            tr = max(faces, key=lambda f: len(f[3]))[3]
            sm = smooth_centers([(p[0], p[1]) for p in tr], W)
            cw = H * 9.0 / 16.0
            x0 = min(max(sm[0][1] - cw / 2, 0.0), max(0.0, W - cw))
            x1 = min(max(sm[-1][1] - cw / 2, 0.0), max(0.0, W - cw))
            shot.update(fx0=round(x0), fx1=round(x1), cw=round(cw), ch=H)
        shots.append(shot)

    # Hysteresis: very short cuts inherit the previous stable composition.
    merged = []
    for sh in shots:
        if merged and sh["end"] - sh["start"] < HOLD_MIN:
            merged[-1]["end"] = sh["end"]
        else:
            merged.append(sh)
    if cache is not None:
        try:
            Path(workdir).mkdir(parents=True, exist_ok=True)
            cache_tmp = cache.with_name(cache.name + ".part")
            meta_tmp = meta.with_name(meta.name + ".part")
            cache_tmp.write_text(json.dumps(merged), encoding="utf-8")
            meta_tmp.write_text(json.dumps(cache_signature), encoding="utf-8")
            os.replace(cache_tmp, cache)
            os.replace(meta_tmp, meta)
        except OSError:
            log.debug("Could not write shot cache", exc_info=True)
            for tmp in (cache.with_name(cache.name + ".part"),
                        meta.with_name(meta.name + ".part")):
                tmp.unlink(missing_ok=True)
    return merged
