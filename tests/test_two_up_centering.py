"""Two-up framing: every speaker sits in the middle of their own panel.

The bug this guards against: panels used to be cut at the *frame's* quarter
points (or centred on a face with the crop clamped at the source edge), so a
speaker who is not exactly at 25% / 75% of a wide shot came out pushed toward
one side of their half — both people drifting toward the middle seam, or a
cornered speaker sliding to the frame edge.

The rules under test:
* a panel is anchored on the subject, not on a fixed slice of the frame;
* a close pair still gets one panel each, cropped tight enough that the other
  speaker stays out of the panel;
* when the face detector misses a speaker (turned head, face too small, soft
  focus) that shot is re-detected with a relaxed detector first — YuNet's own
  default threshold is 0.9, so the *strict* pass drops exactly the marginal face
  a two-up panel needs — and only then falls back to the weakly detected face,
  movement, then picture detail, never on the same person twice;
* both panels share one width, so the split reads as one composition instead of
  two differently zoomed shots;
* the geometry that comes out of analysis is the geometry ffmpeg renders.

``test_rendered_two_up_centers_subjects_in_their_panels`` runs the whole chain
through real ffmpeg on a generated two-shot and *measures* the rendered video,
which is the check that would have caught the original report.
"""
import shutil
from pathlib import Path

import pytest

import marrow.layout as L
import marrow.renderer as R
import marrow.studio as studio

W, H = 1280, 720
FACE_W = 0.07 * W


def _panel_center(panel):
    return panel["x"] + panel["w"] / 2.0


def _as_faces(centres, face_w=FACE_W):
    return [(cx, 200.0, face_w, 0.0) for cx in centres]


# ---------------------------------------------------------------- panel geometry
def test_panels_center_each_subject_even_close_together():
    """A close pair: each panel is its own person, centred, neighbour outside."""
    centres = (0.42 * W, 0.58 * W)
    panels = L._panels(_as_faces(centres), W, H)
    assert len(panels) == 2
    for centre, panel in zip(centres, panels):
        assert abs(_panel_center(panel) - centre) <= 1.5
        assert 0 <= panel["x"] and panel["x"] + panel["w"] <= W
        assert panel["w"] / panel["h"] == pytest.approx(9 / 8, abs=0.02)
    # neither panel reaches the other speaker's face
    left, right = panels
    assert left["x"] + left["w"] <= centres[1] - FACE_W / 2
    assert right["x"] >= centres[0] + FACE_W / 2
    # the crops stay tight instead of swallowing the whole frame
    assert left["w"] <= (centres[1] - centres[0]) * 1.4


def test_panels_center_a_subject_that_sits_near_the_source_edge():
    """Clamping the crop used to push a cornered speaker to the side of the panel."""
    for centre in (0.12 * W, 0.20 * W, 0.80 * W, 0.88 * W):
        sides = sorted((centre, W - centre))          # panels come left-first
        panels = L._panels(_as_faces((centre, W - centre)), W, H)
        for side, panel in zip(sides, panels):
            assert abs(_panel_center(panel) - side) <= 1.5
            assert panel["x"] >= 0 and panel["x"] + panel["w"] <= W


def test_panels_keep_a_cornered_subject_inside_the_panel_without_blowing_it_up():
    """A speaker at the very edge: the crop is as centred as it can be, and small.

    Centring a subject 5% from the edge needs a 10%-wide crop, i.e. a face
    magnified ~10x. The panel stops shrinking at MIN_PANEL_FRACTION, so the
    subject is a little off-centre but the panel is still a usable shot.
    """
    for centre in (0.05 * W, 0.95 * W):
        panel = L._panels(_as_faces((centre, W - centre)), W, H)[0 if centre < W / 2 else 1]
        assert panel["x"] >= 0 and panel["x"] + panel["w"] <= W
        assert panel["w"] >= W * L.MIN_PANEL_FRACTION - 2
        distance = abs(_panel_center(panel) - centre)
        assert distance <= panel["w"] / 2          # never clipped out of its own panel


def test_panels_fall_back_to_source_halves_for_missing_data():
    """Defensive: a malformed shot still yields two in-bounds panels."""
    panels = L._panels([(40000.0, 10.0, 80.0, 0.0)], W, H)
    assert len(panels) == 2
    for panel in panels:
        assert panel["w"] % 2 == 0 and panel["h"] % 2 == 0
        assert 0 <= panel["x"] <= W - panel["w"] and 0 <= panel["y"] <= H - panel["h"]


# ------------------------------------------------------------ subject anchoring
def _frames_with_subjects(*blobs, frames=8, shift=18.0, flicker=-60):
    """Synthetic shot at analysis resolution: dark frames with moving subjects.

    Each blob is ``(cx, cy, w, h, value)`` in pixels of the 320x180 profile.
    A real speaker changes *inside* the head (mouth, eyes, a turn) and shifts a
    little, so the blobs both shift and change brightness — a moving rectangle
    whose pixels never change would only register at its outline.
    """
    import numpy as np

    height, width = 180, 320
    out = []
    for i in range(frames):
        frame = np.full((height, width, 3), 20, np.uint8)
        for cx, cy, w, h, value in blobs:
            dx = int(round((i % 2) * shift - shift / 2))
            x0, y0 = int(cx + dx - w / 2), int(cy - h / 2)
            frame[max(0, y0):y0 + h, max(0, x0):x0 + w] = int(value + (i % 2) * flicker)
        out.append((i * 0.4, frame))
    return out


def test_subject_columns_anchors_two_moving_subjects_with_no_faces_at_all():
    """No face detected anywhere: the two speakers still get one panel each."""
    frames = _frames_with_subjects((90, 90, 60, 90, 200), (230, 95, 60, 90, 210))
    found = L.subject_columns(frames, 1920, 1080, faces=[], loose=[], count=2)
    assert found is not None and len(found) == 2
    xs = sorted(f[0] for f in found)
    assert xs[0] == pytest.approx(90 / 320 * 1920, abs=0.05 * 1920)
    assert xs[1] == pytest.approx(230 / 320 * 1920, abs=0.05 * 1920)
    for cx, cy, w in found:
        assert 0 < cy < 1080
        assert L.MOTION_MIN_WIDTH * 1920 - 1 <= w <= L.MOTION_MAX_FACE * 1920 + 1


def test_subject_columns_keeps_a_known_face_and_finds_the_other_by_motion():
    frames = _frames_with_subjects((90, 90, 60, 90, 200), (230, 95, 60, 90, 210))
    # a real face box is this much narrower than the blob of everything that
    # moves around it (measured: ~1.7x on real podcast footage)
    face_w = 60 / L.MOTION_HEAD_RATIO / 320 * 1920
    known = (230 / 320 * 1920, 95 / 180 * 1080, face_w)
    found = L.subject_columns(frames, 1920, 1080, faces=[known], count=2)
    assert found is not None and len(found) == 2
    assert found[0] == pytest.approx(known, abs=1.0)          # the face is kept as-is
    # the second anchor is the *other* subject, not the same one again
    assert abs(found[1][0] - found[0][0]) >= L.SPLIT_SEPARATION * 1920
    assert found[1][0] == pytest.approx(90 / 320 * 1920, abs=0.06 * 1920)


def test_subject_columns_never_cuts_one_person_into_two_panels():
    """One moving speaker, no second subject: never a second anchor for them."""
    frames = _frames_with_subjects((160, 90, 70, 100, 200))
    found = L.subject_columns(frames, 1920, 1080, faces=[], loose=[], count=2)
    assert found is None or len(found) == 1


def test_subject_columns_ignores_a_shot_that_moves_everywhere():
    """A pan or a fade is not a subject: the caller falls back to frame halves."""
    import numpy as np

    frames = []
    for i in range(8):
        frame = np.full((180, 320, 3), 20, np.uint8)
        start = (i * 30) % 320
        frame[60:120, start:start + 40] = 200                  # a bar crossing the frame
        frames.append((i * 0.4, frame))
    assert L.subject_columns(frames, 1920, 1080, faces=[], loose=[], count=2) is None


def test_subject_columns_returns_the_known_face_alone_when_nothing_else_moves():
    import numpy as np

    frames = [(i * 0.4, np.full((180, 320, 3), 20, np.uint8)) for i in range(6)]
    assert L.subject_columns(frames, 1920, 1080,
                             faces=[(1380.0, 570.0, 90.0)], count=2) == [(1380.0, 570.0, 90.0)]


def test_analyze_two_up_without_any_face_anchors_panels_on_the_subjects(monkeypatch, tmp_path):
    """End of the same chain: the shot carries panels, not a blind quarter split."""
    monkeypatch.setattr(L, "get_detector", lambda: object())
    monkeypatch.setattr(L, "detect_shots", lambda *a: [])
    monkeypatch.setattr(L, "detect_faces", lambda frame, det: [])
    monkeypatch.setattr(L, "sample_frames", lambda *a, **k: _frames_with_subjects(
        (90, 90, 60, 90, 200), (230, 95, 60, 90, 210), frames=6))
    shot = L.analyze("nonexistent.mp4", 0.0, 6.0, workdir=tmp_path, speaker_mode="two_up")[0]
    assert shot["layout"] == "stacked" and shot["views"] == "subject"
    left, right = shot["panels"]
    assert left["x"] < right["x"]
    # the unreadable source makes analyse fall back to a 1280x720 frame size
    for panel, subject_x in zip((left, right), (90 / 320 * 1280, 230 / 320 * 1280)):
        assert abs(_panel_center(panel) - subject_x) <= 0.06 * 1280
    assert left != right


def test_analyze_two_up_keeps_the_one_subject_it_can_place_centered(monkeypatch, tmp_path):
    """One speaker detectable: that panel is still centred on them."""
    monkeypatch.setattr(L, "get_detector", lambda: object())
    monkeypatch.setattr(L, "detect_shots", lambda *a: [])
    monkeypatch.setattr(L, "detect_faces", lambda frame, det: [])
    monkeypatch.setattr(L, "sample_frames",
                        lambda *a, **k: _frames_with_subjects((90, 90, 60, 90, 200), frames=6))
    shot = L.analyze("nonexistent.mp4", 0.0, 3.0, workdir=tmp_path, speaker_mode="two_up")[0]
    assert shot["views"] == "subject" and len(shot["panels"]) == 2
    subject_x = 90 / 320 * 1280                       # the fake source probes as 1280x720
    assert min(abs(_panel_center(p) - subject_x) for p in shot["panels"]) <= 0.06 * 1280
    assert shot["panels"][0] != shot["panels"][1]


def test_analyze_two_up_still_uses_frame_views_when_nothing_is_measurable(monkeypatch, tmp_path):
    """One sample is not enough to locate anyone: keep the old, safe fallback."""
    import numpy as np

    monkeypatch.setattr(L, "get_detector", lambda: object())
    monkeypatch.setattr(L, "detect_shots", lambda *a: [])
    monkeypatch.setattr(L, "sample_frames",
                        lambda *a, **k: [(0.0, np.full((180, 320, 3), 20, np.uint8))])
    monkeypatch.setattr(L, "detect_faces", lambda frame, det: [])
    shot = L.analyze("nonexistent.mp4", 0.0, 2.0, workdir=tmp_path, speaker_mode="two_up")[0]
    assert shot["layout"] == "stacked" and shot["views"] == "frame"
    assert "panels" not in shot


# -------------------------------------------------------------------- rendering
def _two_up_cfg(**platform):
    cfg = {"platforms": {"shorts": {"res_x": 360, "res_y": 640, "max_duration": 180,
                                    "caption_margin_v": 420}},
           "render": {"layout": "crop", "encoder": "libx264", "preset": "ultrafast",
                      "crf": 30, "fps": 25, "loudnorm": False},
           "zoom": {"enabled": False}, "captions": {"enabled": False}}
    cfg["platforms"]["shorts"].update(platform)
    return cfg


def _silent_render(monkeypatch, seen):
    """Capture ffmpeg calls: the segments, the concat, and the progress variant."""
    def fake_run(args, cwd=None):
        seen.append([str(a) for a in args])
        out = Path(str(args[-1]))
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"x" * 2000)
        except OSError:
            pass

        class R_:
            stderr = ""
        return R_()

    monkeypatch.setattr(studio, "run_ffmpeg", fake_run)
    monkeypatch.setattr(R, "run_ffmpeg", fake_run)
    monkeypatch.setattr(R, "run_ffmpeg_progress", lambda args, total, cb, cwd=None: fake_run(args, cwd))
    return fake_run


def test_renderer_uses_the_centred_panel_geometry(monkeypatch, tmp_path):
    seen = []
    _silent_render(monkeypatch, seen)
    shots = [{"start": 0.0, "end": 2.0, "layout": "stacked", "views": "subject",
              "panels": [{"x": 120, "y": 60, "w": 800, "h": 710},
                         {"x": 660, "y": 60, "w": 800, "h": 710}]}]
    studio.render_clip_shots(_two_up_cfg(), tmp_path / "in.mp4", tmp_path, [], 1, 0.0, 2.0,
                             ["shorts"], tmp_path, False, shots)
    graphs = [a[a.index("-filter_complex") + 1] for a in seen if "-filter_complex" in a]
    assert graphs
    for panel in shots[0]["panels"]:
        assert any(f"crop={panel['w']}:{panel['h']}:{panel['x']}:{panel['y']}" in g for g in graphs)
    assert all("vstack=inputs=2" in g for g in graphs)
    assert not any("x='iw/4-ow/2'" in g for g in graphs)      # not the blind quarter split


@pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")),
                    reason="ffmpeg/ffprobe not installed")
def test_rendered_two_up_centers_subjects_in_their_panels(tmp_path):
    """Real ffmpeg, generated two-shot, measured output — the reported bug itself."""
    import numpy as np
    import cv2

    # A 16:9 two-shot with one red and one blue speaker at 35% and 80% of the
    # width — neither at the 25% / 75% the old blind split assumed. Both change
    # their own pixels (a talking head) and shift slightly.
    src = tmp_path / "two_shot.mp4"
    graph = (
        # Each speaker is drawn twice: a dim base, and the bright version on its
        # own clock. Both drift a little. That is what a talking head looks like
        # to the sampler — pixels inside the subject changing — and the two
        # clocks are deliberately out of step with the 2.5 fps analysis sampling.
        "[0:v]drawbox=x='175+7*sin(3*t)':y=90:w=95:h=190:c=0x770000@1:t=fill[a];"
        "[a]drawbox=x='175+7*sin(3*t)':y=90:w=95:h=190:c=red@1:t=fill:"
        "enable='lt(mod(t,0.7),0.35)'[b];"
        "[b]drawbox=x='455+7*sin(2*t)':y=95:w=95:h=190:c=0x000077@1:t=fill[c];"
        "[c]drawbox=x='455+7*sin(2*t)':y=95:w=95:h=190:c=blue@1:t=fill:"
        "enable='lt(mod(t,0.9),0.45)'[v]"
    )
    studio.run_ffmpeg(["-f", "lavfi", "-i", "color=c=0x141414:s=640x360:r=25:d=2.5",
                       "-filter_complex", graph, "-map", "[v]",
                       "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", src])

    shots = L.analyze(str(src), 0.0, 2.5, workdir=tmp_path, speaker_mode="two_up")
    assert shots and shots[0]["layout"] == "stacked"
    assert shots[0].get("panels"), "the two-up shot must carry its own panel geometry"

    produced = studio.render_clip_shots(_two_up_cfg(res_x=180, res_y=320), src, tmp_path,
                                        [], 1, 0.0, 2.5, ["shorts"], tmp_path, False, shots)
    out = produced["shorts"]
    assert out.exists() and out.stat().st_size > 0

    cap = cv2.VideoCapture(str(out))
    rx, ry = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    seen = {"top": [], "bottom": []}
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        for name, colour in (("top", (40, 40, 220)), ("bottom", (220, 40, 40))):  # BGR
            half = frame[: ry // 2] if name == "top" else frame[ry // 2:]
            mask = (np.abs(half.astype(int) - np.array(colour)).sum(axis=2) < 220)
            if mask.sum() < 20:
                continue
            columns = np.where(mask.any(axis=0))[0]
            seen[name].append((columns.min() + columns.max()) / 2.0 / rx)
    cap.release()
    for name, found in seen.items():
        assert found, f"no subject found in the {name} panel"
        offset = abs(float(np.mean(found)) - 0.5)
        assert offset < 0.06, f"the {name} subject sits {offset:.1%} off the panel centre"


# ------------------------------------------- detector, second look, panel rules
def test_panels_share_one_width_so_the_split_reads_as_one_composition():
    """Both halves at the same scale: a split is one composition, not two shots."""
    for centres in ((0.30 * W, 0.70 * W), (0.12 * W, 0.62 * W), (0.45 * W, 0.55 * W)):
        panels = L._panels(_as_faces(centres), W, H)
        assert panels[0]["w"] == panels[1]["w"], centres
        assert panels[0]["h"] == panels[1]["h"], centres


def test_panels_leave_headroom_above_the_head():
    face = (0.5 * W, 200.0, FACE_W, 0.0)
    panel = L._panels([face, (0.9 * W, 200.0, FACE_W, 0.0)], W, H)[0]
    assert 0.25 <= (face[1] - panel["y"]) / float(panel["h"]) <= 0.60


def test_panels_stay_centered_when_the_two_faces_are_different_sizes():
    """A near speaker and a far one: each still lands on their panel's middle."""
    near, far = (0.80 * W, 200.0, 0.12 * W, 0.0), (0.22 * W, 200.0, 0.05 * W, 0.0)
    panels = L._panels([near, far], W, H)
    for panel, face in zip(panels, (far, near)):
        assert abs(_panel_center(panel) - face[0]) <= 2.0, (panel, face)


def test_panels_tighten_for_a_close_pair_but_not_below_a_usable_close_up():
    wide = L._panels(_as_faces((0.25 * W, 0.75 * W)), W, H)
    tight = L._panels(_as_faces((0.40 * W, 0.60 * W)), W, H)
    assert tight[0]["w"] < wide[0]["w"]
    assert tight[0]["w"] >= L.PANEL_FACE_FLOOR * FACE_W          # not one eye per panel
    assert tight[0]["w"] >= L.MIN_PANEL_FRACTION * W


def test_panels_centre_each_speaker_within_three_percent_across_the_width():
    """The whole point, on the geometry alone: every pair, every position.

    A subject so close to the edge that centring needs a crop narrower than the
    panel floor stays where it is (bounded, see the cornered-subject test above);
    everything else has to land on the centre line.
    """
    floor = L.MIN_PANEL_FRACTION * W
    for left in (0.05, 0.10, 0.15, 0.20, 0.30, 0.45):
        for right in (0.55, 0.70, 0.85, 0.95):
            panels = L._panels(_as_faces((left * W, right * W)), W, H)
            for centre, panel in zip((left * W, right * W), panels):
                if 2.0 * min(centre, W - centre) <= floor:      # cannot be centred
                    continue
                assert abs(_panel_center(panel) - centre) <= 0.03 * panel["w"], (left, right)


def test_detect_faces_reads_the_score_from_the_last_column():
    """YuNet rows are [x, y, w, h, 10 landmark floats, score].

    The score used to be taken from row[4] — the right eye's x coordinate — so
    MIN_SCORE compared a pixel position against 0.6 and never rejected anything,
    no matter how low the detector's confidence was.
    """
    import numpy as np

    row = np.asarray([[100, 60, 100, 80, 220.0, 90.0, 300.0, 92.0, 260.0, 130.0,
                      215.0, 145.0, 300.0, 148.0, 0.93]], np.float32)

    class Detector:
        def setInputSize(self, size):
            pass

        def detect(self, frame):
            return 1, row

    L._detector["size"] = None
    frame = np.zeros((720, 1280, 3), np.uint8)
    faces = L.detect_faces(frame, Detector())
    assert faces and abs(faces[0][4] - 0.93) < 1e-6          # the real score, not 220.0
    assert L.detect_faces(frame, Detector(), min_score=0.95) == []
    # a 5-column row (no landmarks) still yields its score
    row5 = np.asarray([[100, 60, 100, 80, 0.8]], np.float32)
    Detector.detect = lambda self, frame: (1, row5)
    assert abs(L.detect_faces(frame, Detector())[0][4] - 0.8) < 1e-6


def test_second_look_merges_the_marginal_speaker_without_duplicating(monkeypatch, tmp_path):
    """The relaxed pass adds the missing speaker and never invents a second one.

    YuNet's `detect` returns its top candidates rather than a stable set, so the
    relaxed pass can report a different box for a face the strict pass already
    found; tracking has to merge the two, and a blob far smaller than the speaker
    has to be ignored.
    """
    import numpy as np

    times = [i * 0.5 for i in range(10)]
    monkeypatch.setattr(L, "get_detector", lambda: object())
    monkeypatch.setattr(L, "get_second_detector", lambda: object())
    monkeypatch.setattr(L, "detect_shots", lambda *a: [])
    monkeypatch.setattr(L, "_activity_maps", lambda *a, **k: None)
    monkeypatch.setattr(L, "sample_frames",
                        lambda *a, **k: [(t, np.zeros((180, 320, 3), np.uint8)) for t in times])
    monkeypatch.setattr(L, "detect_faces", lambda f, d, *a: [(300, 100, 60, 80, 0.9)])
    monkeypatch.setattr(L, "_detect_faces_impl",
                        lambda f, d, *a: [(305, 100, 62, 80, 0.7), (1000, 100, 58, 80, 0.5),
                                          (306, 104, 12, 16, 0.4)])
    shot = L.analyze("nonexistent.mp4", 0.0, 5.0, workdir=tmp_path, speaker_mode="two_up")[0]
    assert shot["views"] == "faces"
    assert len(shot["panels"]) == 2
    assert shot["panels"][0]["x"] < shot["panels"][1]["x"]
    assert shot["faces"] == 2                      # the tiny blob is not a speaker
    assert shot["panels"][0]["w"] == shot["panels"][1]["w"]


def test_second_look_runs_only_when_two_up_is_short_of_faces(monkeypatch, tmp_path):
    import numpy as np

    calls = []
    monkeypatch.setattr(L, "get_detector", lambda: object())
    monkeypatch.setattr(L, "get_second_detector", lambda: object())
    monkeypatch.setattr(L, "_second_look", lambda *a: calls.append(1) or None)
    monkeypatch.setattr(L, "detect_shots", lambda *a: [])
    monkeypatch.setattr(L, "_activity_maps", lambda *a, **k: None)
    monkeypatch.setattr(L, "sample_frames",
                        lambda *a, **k: [(t, np.zeros((180, 320, 3), np.uint8))
                                         for t in (0.0, 0.5, 1.0, 1.5)])
    monkeypatch.setattr(L, "detect_faces",
                        lambda f, d, *a: [(200, 100, 60, 60, 0.9), (1000, 100, 60, 60, 0.9)])
    L.analyze("nonexistent.mp4", 0.0, 3.0, workdir=tmp_path, speaker_mode="two_up")
    assert calls == []                             # two faces already: no second pass
    monkeypatch.setattr(L, "detect_faces", lambda f, d, *a: [(200, 100, 60, 60, 0.9)])
    L.analyze("nonexistent.mp4", 3.0, 6.0, workdir=tmp_path, speaker_mode="two_up")
    assert calls == [1]                            # one face: worth a second look


# ---------------------------------------------------- the real YuNet detector
# YuNet is trained on photographs, so a synthetic face only has to be realistic
# enough to produce a real detection. These score 0.76-0.85, i.e. *under* YuNet's
# own 0.9 default: the strict pass misses them and the second-look detector finds
# them, which is exactly the marginal second speaker two-up has to frame. Nothing
# here stands in for the detector; it is the real model on real frames.


def _model_ready():
    try:
        return L.MODEL_PATH.exists() and L.get_second_detector() is not None
    except Exception:
        return False


needs_model = pytest.mark.skipif(not _model_ready(),
                                 reason="YuNet model/OpenCV not available")


def synth_head(w=520, h=700, seed=0, skin=(178, 196, 224), hair=(48, 42, 40), turn=0.0):
    """(bgr, mask) of a soft-shaded head; face centre at (0.5w, 0.44h)."""
    import cv2
    import numpy as np

    r = np.random.default_rng(seed)
    img = np.zeros((h, w, 3), np.float32)
    mask = np.zeros((h, w), np.uint8)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cx, cy = w * 0.5, h * 0.44
    fw, fh = w * 0.66, h * 0.42
    oval = (((xx - cx) / (fw / 2)) ** 2 + ((yy - cy) / (fh / 2)) ** 2) <= 1.0
    img[oval] = np.array(skin, np.float32) * (0.72 + 0.38 * np.clip(
        (xx - (cx - fw / 2)) / fw, 0, 1) ** 1.4)[oval][..., None]
    mask[oval] = 255
    hair_mask = ((((xx - cx) / (fw * 0.56)) ** 2 +
                  ((yy - (cy - fh * 0.34)) / (fh * 0.62)) ** 2 <= 1.0) & (yy < cy - fh * 0.12))
    img[hair_mask] = np.array(hair, np.float32) * (0.85 + 0.3 * r.random(hair_mask.sum()))[..., None]
    mask[hair_mask] = 255
    for s in (-1, 1):                                        # brows
        cv2.ellipse(img, (int(cx + s * fw * 0.20), int(cy - fh * 0.10)),
                    (int(fw * 0.13), int(fh * 0.035)), 0, 0, 360,
                    tuple(float(v) for v in np.array(hair) * 0.9), -1)
    for s in (-1, 1):                                        # eyes
        ex, ey = cx + s * fw * 0.19, cy - fh * 0.045
        cv2.ellipse(img, (int(ex), int(ey)), (int(fw * 0.085), int(fh * 0.045)), 0, 0, 360,
                    (232, 236, 240), -1)
        cv2.circle(img, (int(ex), int(ey)), int(fw * 0.035), (78, 66, 52), -1)
        cv2.circle(img, (int(ex), int(ey)), int(fw * 0.016), (28, 24, 22), -1)
        cv2.circle(img, (int(ex - fw * 0.012), int(ey - fh * 0.012)), max(1, int(fw * 0.008)),
                   (250, 250, 250), -1)
        cv2.ellipse(img, (int(ex), int(ey - fh * 0.045)), (int(fw * 0.10), int(fh * 0.03)), 0, 0, 360,
                    tuple(float(v) for v in np.array(skin) * 0.86), -1)
    cv2.line(img, (int(cx), int(cy)), (int(cx + turn * fw * 0.06), int(cy + fh * 0.18)),
             tuple(float(v) for v in np.array(skin) * 0.82), max(2, int(fw * 0.03)))
    for s in (-1, 1):                                        # nostrils
        cv2.circle(img, (int(cx + s * fw * 0.05), int(cy + fh * 0.19)), max(2, int(fw * 0.022)),
                   tuple(float(v) for v in np.array(skin) * 0.66), -1)
    cv2.ellipse(img, (int(cx), int(cy + fh * 0.30)), (int(fw * 0.20), int(fh * 0.065)), 0, 0, 360,
                (120, 128, 178), -1)
    cv2.line(img, (int(cx - fw * 0.18), int(cy + fh * 0.30)),
             (int(cx + fw * 0.18), int(cy + fh * 0.30)), (80, 78, 105), max(2, int(fw * 0.018)))
    neck = (yy > cy + fh * 0.42) & (np.abs(xx - cx) < fw * 0.22)
    shoulders = (((xx - cx) / (w * 0.75)) ** 2 + ((yy - h * 1.02) / (h * 0.30)) ** 2) <= 1.0
    body = neck | shoulders
    img[body] = np.array((128, 150, 186), np.float32) * (0.8 + 0.3 * (yy / h))[body][..., None]
    mask[body] = 255
    img = cv2.GaussianBlur(img, (0, 0), max(0.6, w / 260))
    img += r.normal(0, 2.2, img.shape).astype(np.float32)
    return np.clip(img, 0, 255).astype(np.uint8), cv2.GaussianBlur(mask, (0, 0), w / 260)


def synth_two_shot(left_x, right_x, face_w=0.075, size=(1920, 1080), seeds=(0, 1)):
    """A 1080p two-shot where each face centre lands on the requested x."""
    import cv2
    import numpy as np

    w, h = size
    yy = np.mgrid[0:h, 0:w].astype(np.float32)[0]
    canvas = np.clip(58 + 42 * (yy / h)[..., None] * np.array([1.0, 1.0, 1.06], np.float32),
                     0, 255).astype(np.uint8)
    for target, seed in zip((left_x, right_x), seeds):
        head, mask = synth_head(seed=seed, turn=(seed - 0.5) * 0.25)
        ph, pw = head.shape[:2]
        scale = (face_w * w / 0.66) / pw                     # the oval is 0.66 of the patch
        head = cv2.resize(head, (int(pw * scale), int(ph * scale)), interpolation=cv2.INTER_AREA)
        mask = cv2.resize(mask, (head.shape[1], head.shape[0]), interpolation=cv2.INTER_AREA)
        x0 = int(round(target - head.shape[1] / 2))
        y0 = int(round(h * 0.46 - head.shape[0] * 0.44))
        roi = canvas[max(0, y0):y0 + head.shape[0], max(0, x0):x0 + head.shape[1]]
        m = mask[:roi.shape[0], :roi.shape[1]].astype(np.float32)[..., None] / 255.0
        roi[:] = (head[:roi.shape[0], :roi.shape[1]] * m + roi * (1 - m)).astype(np.uint8)
    return canvas


def _detect(frame, det, min_frac=0.02):
    return L.detect_faces(frame, det, 0.0, min_frac)


@needs_model
def test_real_detector_misses_the_marginal_speaker_and_the_second_look_finds_it():
    """Why the second look exists, measured on the real model.

    YuNet's own default score threshold is 0.9; the faces below it are the ones
    two-up has to frame. The strict pass finds nothing, the relaxed detector finds
    both — with real scores in (0, 1], which is also what proves the score is read
    from the right column.
    """
    frame = synth_two_shot(430, 1490)
    assert not _detect(frame, L.get_detector()), "the synthetic faces sit below YuNet's 0.9"
    faces = _detect(frame, L.get_second_detector())
    assert len(faces) == 2, faces
    assert all(0.0 < f[4] <= 1.0 for f in faces), [f[4] for f in faces]
    centres = sorted(f[0] + f[2] / 2 for f in faces)
    assert abs(centres[0] - 430) < 0.03 * frame.shape[1]
    assert abs(centres[1] - 1490) < 0.03 * frame.shape[1]


@needs_model
@pytest.mark.parametrize("left,right", [(430, 1490), (250, 1600), (860, 1160)])
def test_real_two_shot_panels_centre_both_speakers(left, right):
    """Detection -> panels -> offset, on real detector boxes."""
    frame = synth_two_shot(left, right)
    h, w = frame.shape[:2]
    faces = sorted(_detect(frame, L.get_second_detector()), key=lambda f: f[0])
    assert len(faces) == 2, faces
    tracks = [(f[0] + f[2] / 2, f[1] + f[3] / 2, f[2],
               [(i * 0.4, f[0] + f[2] / 2, f[1] + f[3] / 2, f[2], f[3]) for i in range(4)])
              for f in faces]
    panels = L._panels(tracks, w, h)
    for panel, (cx, _cy, _fw, _tr) in zip(panels, tracks):
        assert abs(_panel_center(panel) - cx) <= 0.05 * panel["w"]


@needs_model
def test_real_close_pair_is_refused_as_two_separate_panels():
    """Two faces barely a head apart are one subject, not a two-shot."""
    frame = synth_two_shot(880, 1050, face_w=0.075)
    faces = _detect(frame, L.get_second_detector())
    assert len(faces) == 2, faces
    gap = abs((faces[0][0] + faces[0][2] / 2) - (faces[1][0] + faces[1][2] / 2))
    assert gap < L.SEPARATION * frame.shape[1], gap
    tracks = [(f[0] + f[2] / 2, f[1] + f[3] / 2, f[2], [(i,) + tuple(f) for i in range(4)])
              for f in faces]
    assert L._select_split_pair(tracks, frame.shape[1], 4, min_coexistence=0.0) is None


@pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")),
                    reason="ffmpeg not installed")
@needs_model
def test_rendered_real_faces_sit_on_their_panel_centrelines(tmp_path):
    """The end-to-end promise on real faces: re-detect them in the rendered halves.

    The colour-box test above measures synthetic subjects the detector never sees;
    this one renders faces the real detector finds, then measures where they land
    in the finished video — the reported bug, in the pixels a viewer gets.
    """
    import cv2
    from marrow.config import load_config

    still = tmp_path / "twoshot.png"
    cv2.imwrite(str(still), synth_two_shot(430, 1490))
    video = tmp_path / "twoshot.mp4"
    studio.run_ffmpeg(["-loop", "1", "-i", str(still), "-t", "2", "-r", "25",
                       "-c:v", "libx264", "-preset", "ultrafast", "-crf", "26",
                       "-pix_fmt", "yuv420p", video])

    cfg = load_config()
    cfg["render"].update(speaker_mode="two_up", encoder="libx264", preset="ultrafast",
                         crf=30, loudnorm=False)
    cfg["captions"]["enabled"] = False
    cfg["platforms"]["shorts"].update(res_x=540, res_y=960)
    shots = L.analyze(str(video), 0.0, 2.0, workdir=tmp_path, speaker_mode="two_up")
    assert shots[0]["views"] == "faces", shots[0]

    out = tmp_path / "out.mp4"
    R.render_clip(str(video), 0.0, 2.0, None, out, cfg, "shorts",
                  layout=shots[0]["layout"], shot=shots[0])
    assert out.stat().st_size > 5_000

    cap = cv2.VideoCapture(str(out))
    ok, rendered = cap.read()
    cap.release()
    assert ok and rendered.shape[:2] == (960, 540)
    det = L.get_second_detector()
    ph = 960 // 2
    widths = []
    for half in (0, 1):
        crop = rendered[half * ph:(half + 1) * ph]
        faces = _detect(crop, det, min_frac=0.05)
        assert faces, f"no speaker found in half {half}"
        face = max(faces, key=lambda f: f[2])
        offset = (face[0] + face[2] / 2 - crop.shape[1] / 2) / crop.shape[1]
        assert abs(offset) <= 0.05, f"speaker {half} sits {offset:+.3f} off centre"
        widths.append(face[2] / crop.shape[1])
    assert abs(widths[0] - widths[1]) <= 0.08, widths      # framed at the same size
