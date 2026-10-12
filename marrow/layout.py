"""Smart layout: shot detection + face tracking -> per-shot render layout.

Layouts: "stacked" (2 people, captions on the seam), "face" (1 person,
face-tracked crop), "blur_fit" (no faces). Falls back to the configured
crop/blur_fit when OpenCV or the model is unavailable (one warning only).
"""
import json
import re
import subprocess
import threading
from pathlib import Path

from .utils import log, run_ffmpeg

MODEL_PATH = Path(__file__).parent / "assets" / "models" / "yunet_2023mar.onnx"
MODEL_URL = ("https://github.com/opencv/opencv_zoo/raw/main/models/"
             "face_detection_yunet/face_detection_yunet_2023mar.onnx")
SAMPLE_FPS = 2.5
MIN_FACE_W = 0.06      # fraction of frame width
MIN_SCORE = 0.6
PERSIST_FRAC = 0.60
SEPARATION = 0.20      # face-center distance (fraction of width) for "two people"
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
        req = urllib.request.Request(MODEL_URL, headers={"User-Agent": "marrow"})
        with urllib.request.urlopen(req, timeout=45) as r:
            data = r.read()
        if len(data) < 100_000:                     # redirects/blocks return tiny bodies
            raise ValueError(f"unexpected model size {len(data)}")
        tmp = MODEL_PATH.with_suffix(".part")
        tmp.write_bytes(data)
        tmp.replace(MODEL_PATH)
        log.info("Downloaded the face-detection model (%d KB).", len(data) // 1024)
        return True
    except Exception as e:
        log.debug("Face model download failed: %s", e)
        return False


def get_detector():
    """YuNet face detector, or None (with a one-time warning)."""
    with _lock:
        if _detector["det"] is not None:
            return _detector["det"]
    try:
        import cv2  # lazy: optional vision dependency
    except ImportError:
        _warn_once("OpenCV is not installed; smart layout falls back to crop/blur_fit. "
                   "Install with: pip install -e \".[vision]\"")
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
    """(t, bgr frame) samples via OpenCV. Empty list when unreadable."""
    try:
        import cv2
    except ImportError:
        return []
    cap = cv2.VideoCapture(str(src))
    if not cap.isOpened():
        return []
    fps_src = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    dur_src = total / fps_src if (total and fps_src) else (end - start)
    out, t, step = [], max(0.0, start), 1.0 / fps
    while t < end:
        fno = int((t * fps_src) + 0.5)
        if total and fno >= total:
            break
        cap.set(cv2.CAP_PROP_POS_FRAMES, fno)
        ok, frame = cap.read()
        if not ok or frame is None:
            t += step
            continue
        out.append((t, frame))
        t += step
    cap.release()
    return out


def detect_faces(frame, det):
    """[(x, y, w, h, score)] in pixels."""
    h, w = frame.shape[:2]
    if _detector["size"] != (w, h):
        try:
            det.setInputSize((w, h))
        except Exception:
            pass
        with _lock:
            _detector["size"] = (w, h)
    try:
        _, faces = det.detect(frame)
    except Exception:
        return []
    if faces is None:
        return []
    out = []
    for f in faces:
        x, y, ww, hh, score = (float(v) for v in f[:5])
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


def decide(faces, frame_w):
    """faces: [(cx, ...)] persistent in this shot -> layout name."""
    if len(faces) >= 2:
        xs = sorted(f[0] for f in faces)
        if xs[-1] - xs[0] >= SEPARATION * frame_w:
            return "stacked"
    if len(faces) == 1:
        return "face"
    if len(faces) > 2:
        return "stacked"
    return "blur_fit"


def _mouth_box(cx, cy, w, h):
    """Mouth region of a face box: middle-lower third, slightly narrowed."""
    return (int(cx - 0.28 * w), int(cy + 0.10 * h), int(cx + 0.28 * w), int(cy + 0.48 * h))


def mouth_motion(g0, g1, box):
    """Normalized mean absolute difference inside the mouth region (0..1-ish)."""
    H, W = g0.shape[:2]
    x0, y0, x1, y1 = box
    x0 = max(0, min(x0, W - 2)); x1 = max(x0 + 1, min(x1, W))
    y0 = max(0, min(y0, H - 2)); y1 = max(y0 + 1, min(y1, H))
    a = g0[y0:y1, x0:x1].astype("float32")
    b = g1[y0:y1, x0:x1].astype("float32")
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
    # panel order matches _panels(): faces sorted by center-x (left -> top)
    order = sorted(range(2), key=lambda i: sum(p[1] for p in tracks[i]) / len(tracks[i]))
    maps = [{round(p[0], 3): p for p in tracks[i]} for i in order]
    labels = []
    for k in range(len(frames) - 1):
        (t0, f0), (t1, f1) = frames[k], frames[k + 1]
        mid = (t0 + t1) / 2
        if rms is not None:
            idx = int(mid * energy_fps)
            if idx >= len(rms) or float(rms[idx]) < SPEAK_ENERGY:
                continue
        g0 = cv2.cvtColor(f0, cv2.COLOR_BGR2GRAY)
        g1 = cv2.cvtColor(f1, cv2.COLOR_BGR2GRAY)
        mot = []
        for m in maps:
            p0, p1 = m.get(round(t0, 3)), m.get(round(t1, 3))
            if p0 is None or p1 is None:
                mot.append(0.0)
                continue
            box = _mouth_box((p0[1] + p1[1]) / 2, (p0[2] + p1[2]) / 2,
                             (p0[3] + p1[3]) / 2, (p0[4] + p1[4]) / 2)
            mot.append(mouth_motion(g0, g1, box))
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
    """Two 9:8 cover crops (left person top, right person bottom)."""
    ordered = sorted(faces, key=lambda f: f[0])[:2]
    panels = []
    for cx, cy, w, _h in ordered:
        cw = min(float(W), max(w * 4.0, W * 0.45))
        ch = cw * 8.0 / 9.0
        if ch > H:
            ch = float(H)
            cw = ch * 9.0 / 8.0
        x = min(max(cx - cw / 2, 0.0), max(0.0, W - cw))
        y = min(max(cy - 0.40 * ch, 0.0), max(0.0, H - ch))  # face ~40% down the panel
        panels.append({"x": round(x), "y": round(y), "w": round(cw), "h": round(ch)})
    while len(panels) < 2:
        panels.append({"x": 0, "y": 0, "w": W, "h": H})
    return panels


def analyze(src, start, end, prefer=None, workdir=None):
    """Per-shot layouts for [start, end]. Returns [{start, end, layout, ...}].
    Falls back to a single blur_fit/crop shot when vision is unavailable."""
    if prefer in ("crop", "blur_fit"):
        return [{"start": round(start, 2), "end": round(end, 2), "layout": prefer}]
    cache = None
    if workdir is not None:
        cache = Path(workdir) / f"shots_{start:.0f}_{end:.0f}.json"
        if cache.exists():
            try:
                shots = json.loads(cache.read_text(encoding="utf-8"))
                if shots:
                    return shots
            except Exception:
                pass
    det = get_detector()
    if det is None:
        return [{"start": round(start, 2), "end": round(end, 2),
                 "layout": "blur_fit" if prefer != "crop" else "crop"}]
    import cv2

    probe = cv2.VideoCapture(str(src))
    _w = probe.get(cv2.CAP_PROP_FRAME_WIDTH)
    _h = probe.get(cv2.CAP_PROP_FRAME_HEIGHT)
    W = int(_w) if _w and _w > 0 else 1280
    H = int(_h) if _h and _h > 0 else 720
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
        dets = [(t, detect_faces(f, det)) for (t, f) in fr]
        tracks = track([(t, b) for (t, b) in dets], W)
        faces = []
        for tr in tracks:
            xs = [p[1] for p in tr]
            ys = [p[2] for p in tr]
            ws = [p[3] for p in tr]
            faces.append((sum(xs) / len(xs), sum(ys) / len(ys), sum(ws) / len(ws), tr))
        layout = decide([(f[0], f[1], f[2]) for f in faces], W)
        shot = {"start": round(s0, 2), "end": round(s1, 2), "layout": layout,
                "faces": len(faces)}
        if layout == "stacked":
            ordered = sorted(faces, key=lambda f: f[0])[:2]
            shot["panels"] = _panels([(f[0], f[1], f[2], 0) for f in ordered], W, H)
            try:
                act = speaker_activity(fr, [f[3] for f in ordered], rms)
                if act:
                    shot["active"] = act
            except Exception:
                log.debug("active-speaker detection failed", exc_info=True)
        elif layout == "face":
            tr = max(faces, key=lambda f: len(f[4]))[4]
            sm = smooth_centers([(p[0], p[1]) for p in tr], W)
            cw = H * 9.0 / 16.0
            x0 = min(max(sm[0][1] - cw / 2, 0.0), max(0.0, W - cw))
            x1 = min(max(sm[-1][1] - cw / 2, 0.0), max(0.0, W - cw))
            shot.update(fx0=round(x0), fx1=round(x1), cw=round(cw), ch=H)
        shots.append(shot)
    # hysteresis: merge runs shorter than HOLD_MIN into the previous shot
    merged = []
    for sh in shots:
        if merged and sh["end"] - sh["start"] < HOLD_MIN:
            merged[-1]["end"] = sh["end"]
        else:
            merged.append(sh)
    if cache is not None:
        try:
            cache.write_text(json.dumps(merged), encoding="utf-8")
        except OSError:
            pass
    return merged
