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
  focus) the panel is still anchored on that person — from the weakly detected
  face, then movement, then picture detail — and never on the same person twice;
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
