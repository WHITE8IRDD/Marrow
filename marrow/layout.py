"""Smart layout: shot detection + face tracking -> per-shot render layout.

Layouts: "stacked" (2 people, captions on the seam), "face" (1 person,
face-tracked crop), "blur_fit" (no faces). Falls back to the configured
crop/blur_fit when OpenCV or the model is unavailable (one warning only).

Multi-speaker framing is chosen by ``speaker_mode``:

``auto``    stack a shot only when two *different* faces are genuinely visible
            together (they must coexist in most sampled frames). Footage cut as
            shot/reverse-shot therefore never duplicates one speaker.
``two_up``  force top/bottom panels for every shot. Each panel is anchored on
            its own subject — a detected face when there is one, otherwise the
            part of the frame that *moves* there, then the part with picture
            detail — so the two speakers sit in the middle of their panels at
            any spacing, from shoulder to shoulder to opposite edges. Only when
            nothing at all can be measured does it fall back to the frame's own
            left/right views. One person is never used for both panels.
``off``     never stack; every shot uses the fallback crop/blur_fit or a
            face-tracked crop.

With three or more visible speakers the two most reliable distinct faces are
used (genuine coexistence first, then the larger pair) — a third person is never
invented by re-using a panel.

**Auto-centering.** A stacked panel is a crop anchored on the person it belongs
to, and its width is derived from the subjects rather than from a fixed share of
the frame (``_panels``/``_panel_widths``): both panels get one width, narrowed
only as far as it takes to put *both* speakers on their own panel's centre line,
floored so an edge subject is clamped instead of the whole panel shrinking to a
stamp. A panel can therefore be a head-and-shoulders shot of its own speaker at
any spacing, from shoulder to shoulder to opposite edges of the frame.

Framing needs two *found* subjects, so two-up gives a shot that came up short a
second look before falling back (``_second_look``): the same frames re-detected
with a lower score threshold and a smaller minimum face, which recovers the
speaker YuNet's own 0.9 default drops (a head turned away to listen). If that
still leaves one subject, ``subject_columns`` anchors the other panel on what
moves in the part of the frame no subject occupies — a listener who turned away
still moves — and only when nothing at all can be measured does the shot fall
back to the frame's own two views. That last path is the one case that cannot be
centred (both speakers keep the frame halves they had).
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
SPLIT_PERSIST_FRAC = 0.25  # forced two-up also accepts a face seen in ~1/4 of a shot
# Face-centre distance (fraction of the frame width) that counts as "two people".
# Duplicate boxes on one head are merged first (see `distinct_faces`), so this only
# has to stay clear of that. A podcast pair sitting well inside the frame can be
# narrow — measured 0.18 W on a real two-shot — and refusing it (the old 0.20 bar)
# is what sent each speaker to the outer edge of a frame-half panel instead of the
# middle of a face-framed one.
SEPARATION = 0.13
SPLIT_SEPARATION = 0.10  # forced two-up: closer than this and it is one person twice
MIN_COEXISTENCE = 0.50 # both faces must be visible in the same frame for half the samples
MIN_STACK_SECONDS = 2.5 # skip fleeting detections and shot/reverse-shot transitions
CACHE_VERSION = 7      # bumped with the auto-centering panel geometry

# ---------------------------------------------------------------- panel framing
# How each half of a stacked two-up is framed. The goal is that the person a
# panel belongs to sits on the middle line of that panel, at a sane size, with
# the other speaker out of the way -- so the crop is anchored on the *subject*,
# never on a fixed quarter of the frame, and both halves are one composition.
#
# Each panel is one half of a 9:16 output, i.e. 1080x960 = 9:8. Both panels get
# the SAME width, so the two speakers are framed at the same scale; a split whose
# halves are zoomed differently reads as two mismatched shots.
PANEL_ASPECT = 9.0 / 8.0   # panel width / height
PANEL_TIGHTNESS = 0.92   # tallest crop that still fits the source (fraction of H)
FACE_FILL = 4.0          # *intended* panel width, in face widths (head + shoulders)
PANEL_MIN_WIDTH = 0.45     # ...never tighter than this share of the source frame
MIN_PANEL_FRACTION = 0.14  # ...nor is any panel narrower than this share, ever
PANEL_FACE_FLOOR = 2.2     # a panel is never below this many face widths
NEIGHBOUR_KEEP_OUT = 1.25  # panel width <= gap x this: the other speaker stays outside
PANEL_HEADROOM = 0.42    # face centre sits this far down the crop
# A half with no detected face is still framed on its subject when something
# there moves: a talking head, hands and a shifting weight move every second,
# walls, posters and light stands do not. This is what keeps a listener who
# turned away (the face a detector misses) centred instead of pushed aside.
MOTION_FLOOR = 0.0028    # mean per-pixel change (0..1) that counts as movement
DETAIL_FLOOR = 0.055     # edge energy fallback when the subject is standing still
MOTION_MIN_WIDTH = 0.06  # narrowest subject motion may stand in for (fraction of width)
MOTION_HEAD_RATIO = 1.7  # measured: a talking head moves across ~1.7x its face width
MOTION_MAX_FACE = 0.20   # widest face a motion blob is allowed to imply
LOOSE_PERSIST = 2        # a face seen in this many samples may anchor a panel
# Second look at a shot that yielded fewer than two faces: the same frames are
# re-detected with a lower score threshold and a smaller minimum face, because the
# marginal detection two-up needs is the second speaker (turned away to listen,
# backlit, small in the frame). YuNet's own default threshold is 0.9, so the strict
# pass drops exactly that face. Only shots short of two faces pay for the extra
# pass, and a blob small next to the known speaker is rejected (`_substantial`).
SECOND_LOOK_SCORE = 0.40
SECOND_LOOK_MIN_FACE_W = 0.045
# A second speaker is at least this share of the widest face's width: a partner
# sitting further from the camera is smaller (measured 0.4 on a real two-shot with
# one person closer to the lens), while a face on a poster or a background extra is
# a fraction of that. Deliberately generous — missing a real speaker costs a panel,
# and a small adjacent face is still a person.
SECOND_LOOK_SIZE_RATIO = 0.35
# Duplicate detections of the *same* face (a mirror, or two boxes on one head) are
# merged, so a single speaker can never fill both panels.
DUPLICATE_CENTRE = 0.35  # centre distance below this fraction of the face width = same face
SPEAKER_MODES = ("auto", "two_up", "off")
SPEAKER_MODE_LABELS = {"auto": "Auto", "two_up": "Force two-up", "off": "Off"}
_TWO_UP_ALIASES = {"two_up", "twoup", "force", "force_two_up", "forced", "split", "stack", "stacked"}
_ON_WORDS = {"on", "yes", "true", "1"}
_OFF_WORDS = {"off", "none", "no", "false", "0", "null"}
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
_second_detector = {"det": None, "size": None}


# ------------------------------------------------------------------ speaker modes

def normalize_speaker_mode(mode=None, split_screen=None) -> str:
    """Resolve the multi-speaker framing mode: 'auto', 'two_up' or 'off'.

    ``mode`` wins when it names one of the modes (or a two-up alias). Otherwise
    the legacy boolean ``split_screen`` setting decides: True -> 'auto',
    False -> 'off'. Configs, saved job settings and API payloads written before
    speaker modes existed therefore keep working unchanged.
    """
    if isinstance(mode, bool):
        return "auto" if mode else "off"
    if isinstance(mode, str):
        key = mode.strip().lower().replace("-", "_")
        if key in SPEAKER_MODES:
            return key
        if key in _TWO_UP_ALIASES:
            return "two_up"
    if isinstance(split_screen, bool):
        return "auto" if split_screen else "off"
    if isinstance(split_screen, str):
        # Older/other clients may store the mode (or a truthy word) here.
        key = split_screen.strip().lower().replace("-", "_")
        if key in SPEAKER_MODES:
            return key
        if key in _OFF_WORDS:
            return "off"
        if key in _ON_WORDS:
            return "auto"
        if key in _TWO_UP_ALIASES:
            return "two_up"
    return "auto"


def speaker_mode_for(render_cfg=None, override=None) -> str:
    """The mode for a render config dict, legacy ``split_screen`` included."""
    cfg = render_cfg or {}
    if override is not None:
        return normalize_speaker_mode(override, None)
    return normalize_speaker_mode(cfg.get("speaker_mode"), cfg.get("split_screen", True))


def split_screen_flag(mode) -> bool:
    """Legacy boolean view of a mode, for manifests and older callers."""
    return normalize_speaker_mode(mode, None) != "off"


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
    args += ["-an", "-sn", "-dn", "-vf", "scale=320:-2,select='gte(scene,0.35)',showinfo", "-f", "null", "-"]
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


def sample_frames(src, start, end, fps=SAMPLE_FPS, max_width=None):
    """(t, bgr frame) samples, via ONE forward decode (no repeated random seeks).

    Frames between two samples are stepped over with ``grab()`` and only the ones
    we keep are converted with ``retrieve()``: the decode is unavoidable, the BGR
    conversion of every dropped frame is not. Measured by ``scripts/bench.py`` (50
    samples over 20 s): 1.82 s -> 1.37 s on a 1080p clip, 0.21 s -> 0.14 s on the
    480p proxy. Backends that cannot grab fall back to a plain read loop.
    """
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
    tolerance = 0.5 / fps_src

    def collect(skip):
        """Walk the window. ``skip()`` steps one frame and returns (ok, frame|None)."""
        target, out, last_t = max(0.0, float(start)), [], -1.0
        while target < end:
            ok, frame = skip()
            if not ok:
                break
            pos_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
            frame_no = cap.get(cv2.CAP_PROP_POS_FRAMES)
            t = (pos_ms / 1000.0 - 1.0 / fps_src) if pos_ms > 0 else (frame_no - 1) / fps_src
            if not math.isfinite(t) or t <= last_t:
                t = max(last_t + 1.0 / fps_src, (frame_no - 1) / fps_src)
            # A seek can land beyond the window (VFR/keyframe rounding).
            # Never decode the rest of a multi-hour source waiting for target.
            if t >= end:
                break
            last_t = t
            if t + tolerance >= target:
                if frame is None:               # grabbed only: convert it now
                    ok, frame = cap.retrieve()
                    if not ok or frame is None:
                        break
                if max_width and frame.shape[1] > max_width:
                    h, w = frame.shape[:2]
                    frame = cv2.resize(frame, (max_width, max(2, round(h * max_width / w))),
                                       interpolation=cv2.INTER_AREA)
                out.append((max(0.0, t), frame))
                last_t = t
                target += step
                while target <= t + tolerance:
                    target += step
        return out

    try:
        samples = collect(lambda: (cap.grab(), None))
        if not samples:
            # Some backends refuse to grab: rewind and take the plain read path.
            cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, start) * 1000.0)
            samples = collect(cap.read)
    finally:
        cap.release()
    return samples


def detect_faces(frame, det, min_score=MIN_SCORE, min_face_frac=MIN_FACE_W):
    """[(x, y, w, h, score)] in original-frame pixels.

    ``min_score`` / ``min_face_frac`` default to the analysis thresholds; the
    two-up second look (``_second_look``) passes its own, lower pair.
    """
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
    # The detector keeps one input size at a time and the two detectors are used
    # at different sizes, so this is set on every call: measured at 0.5 us against
    # a 33 ms detect. Caching it per detector was both pointless and wrong — a
    # caller passing its own detector (tests) poisoned the cached size.
    try:
        det.setInputSize((iw, ih))
    except Exception:
        pass
    with _lock:
        if det is _detector["det"]:
            _detector["size"] = (iw, ih)
    try:
        _, faces = det.detect(input_frame)
    except Exception:
        return []
    if faces is None:
        return []
    out = []
    for f in faces:
        # YuNet rows are [x, y, w, h, 5 landmark pairs..., score]: the score is the
        # last column, not the fifth (which is the right eye's x). Reading it from
        # index 4 made MIN_SCORE compare a pixel coordinate against 0.6, i.e. it
        # never rejected a low-confidence box.
        x, y, ww, hh = (float(v) for v in f[:4])
        score = float(f[-1]) if len(f) >= 15 else float(f[4])
        x, ww = x * sx, ww * sx
        y, hh = y * sy, hh * sy
        if score >= min_score and ww >= w * min_face_frac:
            out.append((x, y, ww, hh, score))
    return out


# The second look always calls the real implementation: tests (and callers) patch
# `detect_faces` to script what a shot sees, and the relaxed pass must not be
# routed through those stubs with a different signature.
_detect_faces_impl = detect_faces


def get_second_detector():
    """A second YuNet instance with a lower score threshold, or None.

    Deliberately does *not* download the model: the second look is an
    optimisation for shots that would otherwise fall back to motion anchoring or
    frame halves, not a requirement, and such a shot is still framed.
    """
    with _lock:
        if _second_detector["det"] is not None:
            return _second_detector["det"]
    if not MODEL_PATH.exists():
        return None
    try:
        import cv2

        det = cv2.FaceDetectorYN.create(str(MODEL_PATH), "", (320, 320),
                                       SECOND_LOOK_SCORE, 0.4)
        with _lock:
            _second_detector["det"] = det
        return det
    except Exception:
        log.debug("Second-look face detector is unavailable", exc_info=True)
        return None


def track(samples, frame_w, persist=PERSIST_FRAC):
    """Group per-sample detections into persistent tracks. Returns tracks as
    lists of (t, cx, cy, w, h). ``persist`` is the share of samples a track must
    appear in; forced two-up relaxes it so that two people who alternate on
    screen (shot/reverse-shot) can still get one panel each."""
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
    return [tr for tr in tracks if len(tr) >= persist * n]


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


def distinct_faces(faces, frame_w):
    """Drop duplicate detections of one face so a speaker is never shown twice.

    Two boxes whose centres sit within ``DUPLICATE_CENTRE`` of a face width are
    the same head (a mirror image, a double detection, a face plus its
    reflection). The most persistent / largest box wins.
    """
    kept = []
    for face in sorted(faces, key=lambda f: (-len(f[3]), -f[2], f[0])):
        cx, cy, w = face[0], face[1], face[2]
        same = False
        for other in kept:
            ox, oy, ow = other[0], other[1], other[2]
            limit = max(DUPLICATE_CENTRE * max(w, ow), 0.05 * frame_w)
            if math.hypot(cx - ox, cy - oy) < limit:
                same = True
                break
        if not same:
            kept.append(face)
    return kept


def _median_faces(tracks):
    """(cx, cy, w, track) per track, from median box centres."""
    out = []
    for tr in tracks:
        out.append((statistics.median([p[1] for p in tr]),
                    statistics.median([p[2] for p in tr]),
                    statistics.median([p[3] for p in tr]), tr))
    return out


def _second_look(samples, dets):
    """Re-detect a shot whose first pass found fewer than two faces.

    YuNet's default score threshold (0.9, which the 2023mar weights are trained
    around) drops a head turned away to listen to the person beside them, which is
    exactly the face a two-up panel needs. The extra pass runs on the frames that
    were already decoded, only for the shots that need it, and its boxes are
    merged with the strict ones — ``track`` matches the duplicate to the existing
    track rather than inventing a second speaker. Returns None when no second
    detector is available (the caller then keeps the first pass).
    """
    det = get_second_detector()
    if det is None or not samples:
        return None
    out = []
    for (t, boxes), (_t, frame) in zip(dets, samples):
        extra = _detect_faces_impl(frame, det, SECOND_LOOK_SCORE, SECOND_LOOK_MIN_FACE_W)
        out.append((t, list(boxes) + extra))
    return out


def _substantial(faces):
    """Drop faces that are far smaller than the biggest one (a wall portrait, a
    face on a poster, a false positive on a shirt). Used on the second-look path,
    where the threshold is deliberately low."""
    if not faces:
        return faces
    biggest = max(f[2] for f in faces)
    return [f for f in faces if f[2] >= SECOND_LOOK_SIZE_RATIO * biggest]


def _select_split_pair(faces, frame_w, sample_count, min_coexistence=MIN_COEXISTENCE,
                       min_sep=SEPARATION):
    """Best persistent, well-separated pair of *distinct* faces.

    Scoring: genuine co-presence first, then how often both were on screen, then
    the pair's size, then the left-most pair — deterministic for 3+ speakers.
    ``min_coexistence=0`` is used by the forced two-up mode, which accepts any
    two distinct faces but still prefers the ones that share the screen; that
    mode also lowers ``min_sep``, because two speakers who sit shoulder to
    shoulder are still two panels (each cropped tight on its own person).
    """
    best, best_score = None, None
    for i, a in enumerate(faces):
        for b in faces[i + 1:]:
            if math.hypot(a[0] - b[0], a[1] - b[1]) < min_sep * frame_w:
                continue
            together = _coexistence(a[3], b[3], sample_count)
            if together < min_coexistence:
                continue
            score = (round(together, 3), min(len(a[3]), len(b[3])), round(a[2] + b[2], 3),
                     -abs(a[0] - b[0]))
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



def _sane_face(face, W, H):
    """A subject with usable numbers: malformed (NaN/inf) data must not reach int().

    Panel geometry is cached in JSON and written by earlier versions, so a crop is
    built from it defensively: an unusable centre falls back to the middle of the
    frame instead of taking the render down.
    """
    cx, cy, w = (float(v) for v in face[:3])
    if not math.isfinite(cx):
        cx = W / 2.0
    if not math.isfinite(cy):
        cy = H * PANEL_HEADROOM
    if not (math.isfinite(w) and w > 0):
        w = float(W) * MIN_FACE_W
    return (cx, cy, w) + tuple(face[3:])


def _panel_widths(ordered, W, H, aspect=PANEL_ASPECT):
    """The one width both panels use, so each subject is centred in their half.

    A fixed-width crop cannot be centred on a subject that sits near the frame
    edge — clamping its x coordinate to the frame is what pushed that speaker off
    to the side of their panel. So the width comes from the subjects instead:

    ``ideal``    the framing intent on its own: head + shoulders (``FACE_FILL``
                 face-widths), never tighter than ``PANEL_MIN_WIDTH`` of the frame.
    ``centred``  the widest equal crop that still puts *both* subjects on their own
                 panel's centre line: ``2 * min(cx, W - cx)`` for each of them, so
                 the tighter of the two wins.
    ``floor``    a subject pressed against the frame edge cannot be centred without
                 shrinking the panel to a stamp; keep a usable crop and clamp
                 instead (a small, bounded offset beats an unusable panel).
    ``limit``    when the speakers sit close together, tighten the crop so it does
                 not swallow the neighbour's head — floored, and only applied to
                 side-by-side pairs (a vertical two-shot is separated along y).
    """
    ideal, floors, centres = [], [], []
    widest = min(float(W), float(H) * aspect) * PANEL_TIGHTNESS
    for cx, _cy, w, _h in ordered:
        target = min(widest, max(float(w) * FACE_FILL, float(W) * PANEL_MIN_WIDTH))
        floors.append(min(target, max(float(w) * PANEL_FACE_FLOOR,
                                      float(W) * MIN_PANEL_FRACTION)))
        centres.append(min(max(float(cx), 0.0), float(W)))
        ideal.append(target)
    width = min(ideal)
    if centres:
        width = min(width, min(2.0 * min(c, W - c) for c in centres))
    if floors:
        width = max(width, min(floors))
    if len(ordered) == 2:
        a, b = ordered
        if abs(a[0] - b[0]) >= abs(a[1] - b[1]):        # side by side, not stacked
            limit = abs(a[0] - b[0]) * NEIGHBOUR_KEEP_OUT
            if limit > 0:
                width = min(width, max(limit, min(floors)))
    return max(2.0, width)


def _panels(faces, W, H):
    """Two 9:8 crops, one anchored on each subject, source-left/top first.

    Each panel is centred on the person it belongs to (subject centre = crop
    centre, within the even-pixel rounding yuv420p needs), never on a fixed
    quarter of the frame. Both panels get the width from ``_panel_widths`` and
    the same shape as the output's half-frame, so the split reads as one
    deliberate composition rather than two differently zoomed shots, and the
    subject's face sits ``PANEL_HEADROOM`` down the crop (the headroom a
    talking-head shot wants).

    ``faces`` are ``(cx, cy, w, track)`` tuples in source pixels; the first two
    are used, ordered left-to-right (top-to-bottom for a vertical two-shot).
    """
    ordered = _panel_order([_sane_face(f, W, H) for f in faces[:2]], W)
    cw = _panel_widths(ordered, W, H)
    aspect = PANEL_ASPECT if PANEL_ASPECT > 0 else 9.0 / 8.0
    panels = []
    for cx, cy, _w, _track in ordered:
        face_cx = float(cx)
        if not 0.0 <= face_cx <= W:
            # Face boxes should be inside the frame. Be defensive with stale or
            # malformed analysis data: preserve a valid crop at the nearest edge.
            face_cx = min(max(face_cx, cw / 2.0), max(cw / 2.0, W - cw / 2.0))
        cw_q = max(2, int(cw) // 2 * 2)
        ch = max(2, min(H - H % 2, int(round(cw_q / aspect)) // 2 * 2))
        # Recompute from the quantized crop dimensions; x is then centred on
        # the detected subject to within one pixel (required even by yuv420p).
        x = int(round(face_cx - cw_q / 2.0))
        x = min(max(x, 0), max(0, W - cw_q))
        y = int(min(max(cy - PANEL_HEADROOM * ch, 0.0), max(0.0, H - ch)))
        x, y = x - (x % 2), y - (y % 2)
        panels.append({"x": x, "y": y, "w": cw_q, "h": ch})
    while len(panels) < 2:
        # Defensive: never reached from ``analyze`` (which always passes two
        # anchors). Fall back to the frame's own half, which is what the renderer
        # does when a shot carries no panels at all.
        half = max(2, (W // 2) // 2 * 2)
        ch = max(2, min(H - H % 2, int(round(half * 8.0 / 9.0)) // 2 * 2))
        x = 0 if not panels else max(0, W - half)
        panels.append({"x": x, "y": max(0, (H - ch) // 2 // 2 * 2), "w": half, "h": ch})
    return panels


def _activity_maps(frames, max_width=320):
    """Small gray proxies of a shot: what moved, and where the detail is.

    Returns ``(motion, detail)`` as 2-D float arrays scaled 0..1, or None when
    the frames cannot be measured. Motion is the mean absolute difference
    between consecutive samples (2.5 samples a second, so a talking head, hands
    and posture read clearly); detail is Sobel edge energy on the middle sample.
    """
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None
    grays = []
    for entry in frames:
        frame = entry[1] if isinstance(entry, (tuple, list)) and len(entry) > 1 else entry
        if frame is None or getattr(frame, "size", 0) == 0 or getattr(frame, "ndim", 0) != 3:
            continue
        h, w = frame.shape[:2]
        if w > max_width:
            frame = cv2.resize(frame, (max_width, max(2, int(round(h * max_width / w)))),
                               interpolation=cv2.INTER_AREA)
        grays.append(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype("float32"))
    if len(grays) < 2:
        return None
    shape = min((g.shape for g in grays), key=lambda s: s[0] * s[1])
    grays = [g[:shape[0], :shape[1]] for g in grays]
    motion = np.zeros(shape, dtype="float32")
    for a, b in zip(grays, grays[1:]):
        motion += np.abs(a - b)
    motion /= float(len(grays) - 1) * 255.0
    mid = grays[len(grays) // 2]
    gx = cv2.Sobel(mid, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(mid, cv2.CV_32F, 0, 1, ksize=3)
    detail = cv2.magnitude(gx, gy) / 1020.0
    return motion, detail


def _smooth_1d(values, width):
    """Box-smooth a 1-D profile, ignoring masked-out (NaN) columns."""
    import numpy as np

    values = np.asarray(values, dtype="float32")
    valid = ~np.isnan(values)
    filled = np.where(valid, values, 0.0)
    k = max(3, (int(width) // 24) | 1)
    kernel = np.ones(k, dtype="float32")
    total = np.convolve(filled, kernel, mode="same")
    count = np.convolve(valid.astype("float32"), kernel, mode="same")
    with np.errstate(invalid="ignore", divide="ignore"):
        out = np.where(count > 0, total / np.maximum(count, 1e-6), np.nan)
    return out


def subject_columns(frames, W, H, faces=(), loose=(), count=2):
    """Anchor a panel per subject from the *picture*, for shots the faces missed.

    ``faces`` are the reliable face anchors of this shot (``(cx, cy, w)`` in
    source pixels, strongest first); ``loose`` are weaker face detections (seen
    in a couple of samples only), also source pixels. Returns ``[(cx, cy, w)]``
    ordered strongest-first — one entry when only one subject could be placed —
    or None when the shot cannot be measured at all.

    The ladder is: a known face, then a face the tracker did not trust, then
    whatever *moves* in a part of the frame no subject occupies yet (a listener
    who turned away still moves), then picture detail (a still listener still
    has edges; a backdrop does not). Each candidate must be far enough from the
    subjects already placed to be a different person, so one speaker is never
    cut into two panels — the failure this has to avoid.

    Salience is relative, not absolute: the candidate must stand out from the
    frame's own median, so a shot where *everything* moves (a pan, a fade, a
    zoom) yields nothing and the caller can fall back to the frame's own halves.
    """
    import numpy as np

    maps = _activity_maps(frames)
    if maps is None:
        return None
    motion, detail = maps
    height, width = motion.shape
    scale = width / float(W)                          # source px -> profile px

    anchors = []
    for face in faces:                                # strongest detection first
        if len(anchors) >= count:
            break
        cx, cy, w = (float(face[0]), float(face[1]), float(face[2]))
        if all(abs(cx - a[0]) >= SPLIT_SEPARATION * W for a in anchors):
            anchors.append((cx, cy, w))
    for extra in loose:                               # weaker detections, best first
        if len(anchors) >= count:
            break
        cx, cy, w = float(extra[0]), float(extra[1]), float(extra[2])
        limit = SPLIT_SEPARATION * W
        if all(abs(cx - a[0]) >= limit for a in anchors):
            anchors.append((cx, cy, w))

    while len(anchors) < count:
        mask = np.ones(width, dtype=bool)
        # Every detection claims the width it needs, whether or not it was placed:
        # two people moving next to each other form one blob, and the blob's
        # middle is the gap between them, which is nobody.
        for cx, w in ([(float(a[0]), float(a[2])) for a in anchors] +
                      [(float(c[0]), float(c[2])) for c in list(faces) + list(loose)]):
            half = max(2, int(round(max(w * 1.6, MOTION_MIN_WIDTH * W) * scale)))
            lo, hi = int(round(cx * scale)) - half, int(round(cx * scale)) + half
            mask[max(0, lo):max(0, hi)] = False
        if not mask.any():
            break
        source, floor = None, None
        for plane, bar in ((motion, MOTION_FLOOR), (detail, DETAIL_FLOOR)):
            masked = np.where(mask, plane.mean(axis=0), np.nan)
            if not np.isfinite(masked).any():
                continue
            # Relative bar: the candidate must stand out from the rest of the frame,
            # so a shot where *everything* moves or is busy yields nothing at all.
            bar = max(bar, 1.6 * float(np.nanmedian(masked)))
            if float(np.nanmax(masked)) >= bar:
                source, floor = plane, bar
                break
        if source is None:
            break
        band = _smooth_1d(np.where(mask, source.mean(axis=0), np.nan), width)
        if not np.isfinite(band).any():
            break
        at = int(np.nanargmax(band))
        peak = float(band[at])
        if peak < floor or peak < 1.25 * float(np.nanmedian(band)):
            break
        # The subject is the run of columns around the peak that stays above a
        # third of it. The centre is the *weighted* centre of that run, not its
        # midpoint: the profile is not symmetric (a speaker who shifts sideways
        # moves more at the edge they move toward, and a rigid subject — a hand,
        # a phone — peaks at its outline rather than in its middle).
        values = np.nan_to_num(band, nan=0.0)
        edge = max(peak * 0.3, floor * 0.5)
        lo = at
        while lo > 0 and values[lo - 1] >= edge:
            lo -= 1
        hi = at
        while hi + 1 < width and values[hi + 1] >= edge:
            hi += 1
        if not mask[at]:
            break
        section = values[lo:hi + 1]
        weights = np.maximum(section, 1e-6)
        cx = float(np.average(np.arange(lo, hi + 1), weights=weights)) / scale
        # vertical: the subject's own rows, biased so the head sits high
        rows = _smooth_1d(source[:, lo:hi + 1].mean(axis=1), height)
        rows = np.nan_to_num(rows, nan=0.0)
        if rows.max() > 0:
            top = int(np.argmax(rows >= 0.5 * float(rows.max())))
        else:
            top = 0
        span = float(max(hi - lo, 1)) / scale
        cy = (top + 0.30 * max(1, height - top)) * H / float(height)
        # The blob is wider than the head (hands, torso, the neighbour leaning in),
        # so it is only used to say where the person is; the panel width comes from
        # the face width the blob implies.
        sub_w = min(max(span / MOTION_HEAD_RATIO, MOTION_MIN_WIDTH * W), MOTION_MAX_FACE * W)
        if all(abs(cx - a[0]) >= SPLIT_SEPARATION * W for a in anchors):
            anchors.append((float(cx), float(min(max(cy, 0.05 * H), 0.95 * H)), float(sub_w)))
            continue
        break
    return anchors or None


def _fallback_shots(start, end, fallback, mode):
    """What to return when the face detector itself is unavailable.

    Forced two-up still needs two panels, so it returns a frame-view stacked shot
    for the whole range: the renderer crops the frame's left and right views and
    stacks them. This is the only two-up path that cannot centre anything — every
    other one anchors each panel on its subject. Every other mode uses the
    configured fallback layout.
    """
    if mode == "two_up":
        return [{"start": round(start, 2), "end": round(end, 2), "layout": "stacked",
                 "views": "frame", "mode": mode}]
    return [{"start": round(start, 2), "end": round(end, 2), "layout": fallback}]


def analyze(src, start, end, prefer=None, workdir=None, split_screen=True,
            fallback="blur_fit", speaker_mode=None, scan_src=None, on_progress=None):
    """Per-shot layouts for [start, end]. Returns [{start, end, layout, ...}].

    ``speaker_mode`` is 'auto' (default), 'two_up' or 'off'; ``split_screen``
    stays supported as the legacy boolean (True -> auto, False -> off) and is
    only consulted when no mode is given. AUTO keeps the conservative two-shot
    rule: both persistent faces must coexist in at least half the sampled frames,
    which avoids showing one person twice in shot/reverse-shot edits. TWO_UP
    always returns a stacked layout, with one panel per subject: two faces when
    the detector has them, otherwise a weak face, motion or picture detail
    (``views: "subject"``), and only the frame's own left/right views when
    nothing can be measured. ``scan_src``
    (e.g. the 480p preview proxy) can be used for shot/face analysis; detected
    coordinates are scaled back to the source frame.

    ``prefer`` remains the explicit per-render layout override ('crop' /
    'blur_fit') and wins over any mode.
    """
    mode = normalize_speaker_mode(speaker_mode, split_screen)
    if prefer in ("crop", "blur_fit"):
        return [{"start": round(start, 2), "end": round(end, 2), "layout": prefer}]
    fallback = fallback if fallback in ("crop", "blur_fit") else "blur_fit"

    cache = meta = None
    cache_signature = None
    if workdir is not None:
        suffix = {"off": "_no_split", "two_up": "_two_up"}.get(mode, "")
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
                           "split_screen": mode != "off", "speaker_mode": mode,
                           "scan": str(scan_src) if scan_src else None,
                           "fallback": fallback}
        if cache.exists() and meta.exists():
            try:
                saved_signature = json.loads(meta.read_text(encoding="utf-8"))
                shots = json.loads(cache.read_text(encoding="utf-8"))
                if saved_signature == cache_signature and isinstance(shots, list) and shots:
                    return shots
            except (OSError, ValueError, TypeError):
                pass

    if on_progress:
        on_progress("Loading face detector", 0.0)
    det = get_detector()
    try:
        import cv2
    except ImportError:
        return _fallback_shots(start, end, fallback, mode)
    if det is None and mode != "two_up":
        # Nothing else is measurable without OpenCV: AUTO and OFF keep the
        # configured fallback layout.
        return _fallback_shots(start, end, fallback, mode)
    # ...but forced two-up no longer depends on the face model: with the detector
    # unavailable it still anchors each panel on what moves in that half of the
    # frame (``detect_faces`` below returns nothing, and the motion path takes
    # over), which is far better than cutting the frame at its quarter points.

    # Analysis can run on a small proxy; face boxes are scaled back to source pixels.
    scan = Path(scan_src) if scan_src and Path(scan_src).exists() else Path(src)
    probe = cv2.VideoCapture(str(scan))
    try:
        _w = probe.get(cv2.CAP_PROP_FRAME_WIDTH)
        _h = probe.get(cv2.CAP_PROP_FRAME_HEIGHT)
        W = int(_w) if _w and _w > 0 else 1280
        H = int(_h) if _h and _h > 0 else 720
    finally:
        probe.release()

    scan_scale = 1.0
    if scan != Path(src):
        src_probe = cv2.VideoCapture(str(src))
        try:
            _sw = src_probe.get(cv2.CAP_PROP_FRAME_WIDTH)
            SW = int(_sw) if _sw and _sw > 0 else W
        finally:
            src_probe.release()
        scan_scale = (SW / W) if W else 1.0

    if on_progress:
        on_progress("Detecting scene cuts", 0.1)
    cuts = [c for c in detect_shots(scan, start, end) if start < c < end]
    bounds = [start] + cuts + [end]
    if on_progress:
        on_progress("Sampling frames", 0.3)
    # Keep a 4K clip's samples from consuming gigabytes while the proxy builds.
    if W > DETECT_MAX_WIDTH:
        samples = sample_frames(scan, start, end, max_width=DETECT_MAX_WIDTH)
        scan_scale *= W / DETECT_MAX_WIDTH
        H, W = max(2, round(H * DETECT_MAX_WIDTH / W)), DETECT_MAX_WIDTH
    else:
        samples = sample_frames(scan, start, end)
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
        if on_progress:
            on_progress(f"Tracking speakers · shot {i + 1}/{len(bounds) - 1}",
                        0.5 + 0.5 * i / max(1, len(bounds) - 1))
        s0, s1 = bounds[i], bounds[i + 1]
        fr = by_shot.get(i, [])
        dets = [(t, detect_faces(frame, det)) if det is not None else (t, []) for t, frame in fr]
        persist = SPLIT_PERSIST_FRAC if mode == "two_up" else PERSIST_FRAC
        faces = distinct_faces(_median_faces(track(dets, W, persist)), W)
        if mode == "two_up" and len(faces) < 2:
            # Two-up needs two people: give the shot a second chance with a relaxed
            # detector (the face YuNet's own 0.9 default drops) before falling back
            # to motion anchoring or the frame's two halves.
            again = _second_look(fr, dets)
            if again:
                dets = again
                faces = _substantial(distinct_faces(_median_faces(track(dets, W, persist)), W))
        pair = None
        anchors = None
        if mode == "two_up":
            layout = "stacked"
            if len(faces) >= 2:
                pair = _select_split_pair(faces, W, len(fr), min_coexistence=0.0,
                                          min_sep=SPLIT_SEPARATION)
            anchors = pair
            if anchors is None and fr:
                # The detector missed one of the speakers (a turned head, a face
                # too small or too soft for YuNet). Rather than cutting the frame
                # blindly at its quarter points — which leaves both people at the
                # side of their panel — anchor each panel on the subject that is
                # really in that part of the frame: a weakly detected face, then
                # movement, then detail. One person is never split across both
                # panels: a second subject has to be far enough to be someone else.
                loose = []
                for tr in track(dets, W, persist=LOOSE_PERSIST / max(1.0, float(len(fr)))):
                    cx = statistics.median([p[1] for p in tr])
                    cy = statistics.median([p[2] for p in tr])
                    w = statistics.median([p[3] for p in tr])
                    if any(math.hypot(cx - f[0], cy - f[1]) <
                           max(DUPLICATE_CENTRE * max(w, f[2]), 0.05 * W) for f in faces):
                        continue                      # the same head, detected again
                    loose.append((cx, cy, w))
                loose.sort(key=lambda c: -c[2])
                found = subject_columns(fr, W, H,
                                        faces=[(f[0], f[1], f[2]) for f in faces],
                                        loose=loose, count=2)
                if found and len(found) == 1:
                    # Only one subject could be placed. Keep it centred — that is
                    # the whole point — and give the other panel the frame's own
                    # half, which is what a blind split used to do for both.
                    (cx, cy, w) = found[0]
                    other = 0.75 * W if cx < W / 2 else 0.25 * W
                    found = [found[0], (other, cy, min(w, MOTION_MAX_FACE * W))]
                if found and len(found) == 2:
                    anchors = [(cx, cy, w, None) for cx, cy, w in found]
        else:
            layout = decide([(f[0], f[1], f[2]) for f in faces], W,
                            allow_split=(mode == "auto"))
            if layout == "stacked":
                pair = _select_split_pair(faces, W, len(fr))
                if s1 - s0 < MIN_STACK_SECONDS or pair is None:
                    # Not a stable, simultaneous two-shot: keep a single tracked face.
                    layout = decide([(f[0], f[1], f[2]) for f in faces], W, allow_split=False)
            anchors = pair
        if layout == "blur_fit":
            layout = fallback
        shot = {"start": round(s0, 2), "end": round(s1, 2), "layout": layout,
                "faces": len(faces)}
        if layout == "stacked":
            shot["views"] = "faces" if pair else ("subject" if anchors else "frame")
            if mode == "two_up":
                shot["mode"] = mode
            if anchors:
                shot["panels"] = _panels([(a[0] * scan_scale, a[1] * scan_scale,
                                           a[2] * scan_scale, 0) for a in anchors],
                                         int(round(W * scan_scale)), int(round(H * scan_scale)))
                if pair:
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
            s = scan_scale
            shot.update(fx0=round(x0 * s), fx1=round(x1 * s), cw=round(cw * s),
                        ch=int(round(H * s)))
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
