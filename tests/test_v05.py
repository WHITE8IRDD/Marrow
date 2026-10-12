"""v0.5: active-speaker focus, karaoke/smooth captions, cache + override rules."""
import json
import shutil

import pytest

import marrow.layout as L
import marrow.renderer as R
import marrow.studio as studio
from marrow.caption_styles import BASE, PRESETS, resolve_style
from marrow.captioner import generate_ass
from marrow.models import Word

cv2 = pytest.importorskip("cv2", reason="vision extra not installed")
import numpy as np


# ---------------------------------------------------------------- speaker focus
def _scene(mouth, frame=0):
    """100x100 frame with two 'faces'; `mouth` in {None, 0, 1} draws changing
    bright pixels in that face's mouth region (simulating talking)."""
    f = np.full((160, 1280, 3), 60, np.uint8)
    for i, cx in enumerate((212, 1012)):
        cv2.rectangle(f, (cx - 12, 25), (cx + 12, 55), (180, 180, 180), -1)
        if mouth == i:
            v = 200 + ((frame * 37 + cx) % 55)      # varies frame to frame
            h = 42 + (frame % 4)                    # mouth opens/closes
            cv2.rectangle(f, (cx - 6, h), (cx + 6, h + 8), (v, v, v), -1)
    return f


def _tracks(mouths):
    """Two tracks over the sample times; the talking face's mouth box jitters."""
    ts = [i * 0.4 for i in range(len(mouths) + 1)]
    a, b = [], []
    for i, t in enumerate(ts):
        a.append((t, 212.0, 40.0, 24.0, 30.0))
        b.append((t, 1012.0, 40.0, 24.0, 30.0))
    return [a, b], ts


def test_speaker_activity_picks_the_mover():
    # face 0 (left -> panel 0) talks for the first 2 s, then face 1 takes over
    mouths = [0, 0, 0, 0, 0, 1, 1, 1, 1, 1]
    frames = []
    for i in range(len(mouths) + 1):
        frames.append((i * 0.4, _scene(mouths[min(i, len(mouths) - 1)], i)))
    tracks, _ = _tracks(mouths)
    act = L.speaker_activity(frames, tracks)
    assert act, "expected at least one focus interval"
    assert all(len(iv) == 3 for iv in act)
    first = act[0]
    assert first[2] == 0 and first[0] <= 0.5 and first[1] >= 1.5
    assert any(iv[2] == 1 for iv in act)
    # intervals never overlap and stay in time order
    for x, y in zip(act, act[1:]):
        assert x[1] <= y[0] + 1e-6


def test_speaker_activity_silence_gates():
    mouths = [0] * 10
    frames = [(i * 0.4, _scene(mouths[min(i, 9)], i)) for i in range(11)]
    tracks, _ = _tracks(mouths)
    silent = np.zeros(200)                      # energy.npy analog: pure silence
    assert L.speaker_activity(frames, tracks, rms=silent) == []
    loud = np.ones(200)
    assert L.speaker_activity(frames, tracks, rms=loud) != []


def test_speaker_activity_needs_two_tracks():
    frames = [(i * 0.4, _scene(0, i)) for i in range(6)]
    tracks, _ = _tracks([0] * 5)
    assert L.speaker_activity(frames, tracks[:1]) == []
    assert L.speaker_activity(frames[:2], tracks) == []


def test_analyze_stacked_includes_active(monkeypatch, tmp_path):
    mouths = [0, 0, 0, 1, 1, 1, 0, 0, 0, 1]
    frames = [(i * 0.4, _scene(m, i)) for i, m in enumerate(mouths)]
    monkeypatch.setattr(L, "get_detector", lambda: object())
    monkeypatch.setattr(L, "detect_shots", lambda *a: [])
    monkeypatch.setattr(L, "sample_frames", lambda *a, **k: frames)
    monkeypatch.setattr(L, "detect_faces", lambda f, d: [(200, 25, 24, 30, 0.9), (1000, 25, 24, 30, 0.9)])
    shots = L.analyze("nonexistent.mp4", 0.0, 4.0, workdir=tmp_path)
    assert len(shots) == 1 and shots[0]["layout"] == "stacked"
    assert shots[0].get("active"), "stacked shot should carry focus intervals"
    assert all(0.0 <= s < e <= 4.0 and p in (0, 1) for s, e, p in shots[0]["active"])
    # cached JSON round-trips (the pipeline reads this back)
    assert json.loads((tmp_path / "shots_0_4.json").read_text())[0]["active"]


def test_analyze_no_vision_falls_back(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "download_model", lambda: False)   # keep the test offline
    shots = L.analyze("nonexistent.mp4", 0.0, 2.0, workdir=tmp_path)
    assert shots and shots[0]["layout"] in ("crop", "blur_fit")


# ------------------------------------------------------------------- renderer
def test_panel_zoom_expr():
    e = R._panel_zoom_expr([[0.5, 2.0, 0], [3.0, 4.0, 1]], 0, fps=30)
    assert e and e.startswith("min(1+0.07*(")
    assert "clip((on-15.0)/9.0,0,1)" in e          # 0.5 s * 30 fps, 0.3 s ramp
    assert "smoothstep" not in e                    # zoompan's evaluator lacks it
    assert R._panel_zoom_expr([[0.5, 2.0, 0]], 1, fps=30) is None
    assert R._panel_zoom_expr([], 0, fps=30) is None
    assert R._panel_zoom_expr([[2.0, 0.5, 0]], 0, fps=30) is not None   # swapped -> clamped


def test_stacked_graph_static_unchanged():
    shot = {"panels": [{"x": 10, "y": 20, "w": 600, "h": 480}, {"x": 700, "y": 20, "w": 600, "h": 480}]}
    g = R.build_filter_graph("stacked", 1080, 1920, 30, {"enabled": False}, shot=shot)
    assert "zoompan" not in g and "vstack" in g
    assert "crop=600:480:10:20" in g


def test_stacked_graph_active_zoom():
    shot = {"panels": [{"x": 10, "y": 20, "w": 600, "h": 480}, {"x": 700, "y": 20, "w": 600, "h": 480}],
            "active": [[0.4, 2.2, 0], [2.6, 4.0, 1]]}
    g = R.build_filter_graph("stacked", 1080, 1920, 30, {"enabled": False}, shot=shot)
    assert g.count("zoompan") == 2                  # one push-in chain per panel
    assert "vstack" in g and g.rstrip().endswith("[base]") or "[base]" in g
    assert "fps=30" in g


def test_relative_shot_shifts_active():
    sg = {"start": 10.0, "end": 16.0, "layout": "stacked", "panels": [1, 2],
          "active": [[9.0, 11.0, 0], [12.0, 20.0, 1], [30.0, 31.0, 0]]}
    out = studio.relative_shot(sg, 10.0, 6.0)
    assert out["start"] == 0.0 and out["end"] == 6.0
    assert out["active"] == [[0.0, 1.0, 0], [2.0, 6.0, 1]]   # clamped, dropped out-of-range
    assert "active" not in studio.relative_shot({"start": 0, "end": 5, "layout": "face"}, 0.0, 5.0)


# ------------------------------------------------------------------- captions
def _words(text, per=0.4, score=0.5):
    return [Word(i * per, i * per + per * 0.9, t, score=score) for i, t in enumerate(text.split())]


def test_karaoke_holds_previous_words(tmp_path):
    out = tmp_path / "k.ass"
    generate_ass(_words("make it go viral now"), 0.0, 2.0, out, {"preset": "karaoke", "overrides": {}})
    lines = [l for l in out.read_text(encoding="utf-8").splitlines() if l.startswith("Dialogue")]
    second = lines[1]
    # the first word stays lit (highlight &H00E6FF in BGR) while the second pops
    assert "\\1c&H00E6FF&}MAKE" in second
    assert "\\t(0,110," in second


def test_opus_preset_fades_and_smooths(tmp_path):
    out = tmp_path / "o.ass"
    generate_ass(_words("make it go viral"), 0.0, 1.6, out, {"preset": "opus", "overrides": {}})
    text = out.read_text(encoding="utf-8")
    assert "\\fad(90,60)" in text
    # smooth highlight: the word starts in the base color and eases into the lime
    assert "\\1c&HFFFFFF&\\t(0,110,\\fscx" in text and "\\1c&H3DFFB9&)" in text


def test_hold_and_smooth_overridable(tmp_path):
    st = resolve_style("karaoke", {"hold_highlight": False, "smooth": False}, None)
    assert st["hold_highlight"] is False and st["smooth"] is False
    out = tmp_path / "off.ass"
    generate_ass(_words("make it go viral now"), 0.0, 1.2, out,
                 {"preset": "karaoke", "overrides": {"hold_highlight": False}})
    lines = [l for l in out.read_text(encoding="utf-8").splitlines() if l.startswith("Dialogue")]
    assert "\\1c&H00E6FF&}MAKE" not in lines[1]
    assert set(PRESETS) >= {"opus", "karaoke"}
    assert BASE["hold_highlight"] is False and BASE["smooth"] is True


def test_pill_mode_stays_instant(tmp_path):
    out = tmp_path / "p.ass"
    generate_ass(_words("make it go"), 0.0, 1.2, out,
                 {"preset": "pill", "overrides": {"hold_highlight": True}})
    text = out.read_text(encoding="utf-8")
    assert "\\bord10\\shad0" in text                # pill border, unchanged
    assert "\\1c&HFFFFFF&\\t(0,110" not in text     # no smooth-color tag in pill mode


# --------------------------------------------------------------------- server
def test_clean_overrides_new_keys():
    from marrow.server import clean_overrides

    ov = clean_overrides({"hold_highlight": True, "smooth": False, "fade_in": 120,
                          "fade_out": "90", "fade_in2": 5, "bogus": 1})
    assert ov == {"hold_highlight": True, "smooth": False, "fade_in": 120, "fade_out": 90}
    assert clean_overrides({"fade_in": 9000}) == {}       # out of range -> dropped
    assert clean_overrides({"hold_highlight": "yes"})["hold_highlight"] is True


# ------------------------------------------------------- ffmpeg render (slow)
has_ffmpeg = shutil.which("ffmpeg") and shutil.which("ffprobe")


@pytest.mark.skipif(not has_ffmpeg, reason="ffmpeg not installed")
def test_render_stacked_active_speaker(tmp_path):
    """Full ffmpeg pass: stacked panels with focus intervals produce a valid 9:16 clip."""
    src = tmp_path / "src.mp4"
    studio.run_ffmpeg([
        "-f", "lavfi", "-i", "testsrc2=s=1280x720:r=30:d=4",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest", src])
    cfg = {
        "platforms": {"shorts": {"res_x": 1080, "res_y": 1920, "max_duration": 180,
                                 "caption_margin_v": 420}},
        "render": {"layout": "crop", "encoder": "libx264", "preset": "ultrafast",
                   "crf": 28, "fps": 30, "loudnorm": False},
        "zoom": {"enabled": False},
        "captions": {"enabled": True, "preset": "opus", "overrides": {}},
    }
    words = _words("hello there friend how are you today", per=0.5)
    shots = [{"start": 0.0, "end": 4.0, "layout": "stacked", "faces": 2,
              "panels": [{"x": 40, "y": 60, "w": 620, "h": 550}, {"x": 660, "y": 60, "w": 620, "h": 550}],
              "active": [[0.5, 1.8, 0], [2.2, 3.6, 1]]}]
    out = studio.render_clip_shots(cfg, src, tmp_path, words, 1, 0.0, 4.0, ["shorts"],
                                   tmp_path, True, shots)
    f = out["shorts"]
    assert f.exists() and f.stat().st_size > 10_000
    from marrow.utils import probe_duration
    assert abs(probe_duration(f) - 4.0) < 0.35
