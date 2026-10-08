import marrow.layout as L
from marrow.captioner import generate_ass
from marrow.models import Word
from marrow import studio


def test_decide_layouts():
    W = 1280
    assert L.decide([(200, 100, 60), (1000, 100, 60)], W) == "stacked"
    assert L.decide([(640, 100, 60)], W) == "face"
    assert L.decide([], W) == "blur_fit"
    assert L.decide([(600, 100, 60), (650, 100, 60)], W) == "blur_fit"  # too close


def test_smooth_stays_in_bounds():
    W = 1280
    pts = [(t, 640 + 900 * (t % 2)) for t in [i * 0.4 for i in range(10)]]
    sm = L.smooth_centers(pts, W)
    assert len(sm) == len(pts)
    for (t, x), (t2, x2) in zip(sm, sm[1:]):
        assert abs(x2 - x) <= L.MAX_PAN * W * (t2 - t) + 1e-6  # max pan speed
    xs = [x for _, x in sm]
    assert min(xs) >= -1 and max(xs) <= W + 1


def test_analyze_two_faces_stacked(monkeypatch, tmp_path):
    import numpy as np

    monkeypatch.setattr(L, "get_detector", lambda: object())
    monkeypatch.setattr(L, "detect_shots", lambda *a: [])
    monkeypatch.setattr(
        L, "sample_frames",
        lambda *a, **k: [(t, np.zeros((180, 320, 3), np.uint8)) for t in (0.0, 0.5, 1.0, 1.5)])
    monkeypatch.setattr(L, "detect_faces",
                        lambda f, d: [(200, 100, 80, 80, 0.9), (1000, 100, 80, 80, 0.9)])
    shots = L.analyze("nonexistent.mp4", 0.0, 2.0, workdir=tmp_path)
    assert len(shots) == 1 and shots[0]["layout"] == "stacked"
    assert len(shots[0]["panels"]) == 2
    assert (tmp_path / "shots_0_2.json").exists()  # cached


def test_analyze_hysteresis_merges_short(monkeypatch, tmp_path):
    import numpy as np

    monkeypatch.setattr(L, "get_detector", lambda: object())
    monkeypatch.setattr(L, "detect_shots", lambda *a: [1.5, 1.8])
    monkeypatch.setattr(
        L, "sample_frames",
        lambda *a, **k: [(t, np.zeros((180, 320, 3), np.uint8)) for t in (0.0, 1.0, 2.0, 3.0)])
    monkeypatch.setattr(L, "detect_faces",
                        lambda f, d: [(200, 100, 80, 80, 0.9), (1000, 100, 80, 80, 0.9)])
    shots = L.analyze("nonexistent.mp4", 0.0, 4.0)
    assert [round(s["end"] - s["start"], 2) for s in shots] == [1.8, 2.2]
    assert all(s["layout"] == "stacked" for s in shots)


def test_ass_pos_only_in_stacked(tmp_path):
    words = [Word(i * 0.4, i * 0.4 + 0.35, t, score=0.5)
             for i, t in enumerate("one two three four".split())]
    out = tmp_path / "seam.ass"
    shots = [{"s": 0.0, "e": 0.8, "layout": "stacked"},
             {"s": 0.8, "e": 2.0, "layout": "crop"}]
    n = generate_ass(words, 0.0, 2.0, out, {"preset": "bold-pop", "overrides": {}},
                     shots=shots)
    assert n > 0
    text = out.read_text(encoding="utf-8")
    assert "\\an5\\pos(540,960)" in text
    lines = [l for l in text.splitlines() if l.startswith("Dialogue:")]
    early = [l for l in lines if l.split(",")[1].startswith("0:00:00.")]
    assert early and all("\\pos(540,960)" in l for l in early[:2])
    late = [l for l in lines if l.split(",")[1].startswith("0:00:01.")]
    assert late and all("\\pos(" not in l for l in late)


def test_normalize_shots_fills_gaps():
    segs = studio.normalize_shots([{"start": 5.0, "end": 8.0, "layout": "face"}],
                                   0.0, 10.0, "crop")
    assert [(s["start"], s["end"], s["layout"]) for s in segs] == [
        (0.0, 5.0, "crop"), (5.0, 8.0, "face"), (8.0, 10.0, "crop")]
    assert not studio.needs_segmented_render([{"layout": "crop"}])
    assert studio.needs_segmented_render([{"layout": "stacked"}])


def test_apply_shot_overrides():
    shots = [{"start": 0, "end": 5, "layout": "face"}]
    out = studio.apply_shot_overrides(shots, {"0": "blur_fit", "9": "crop", "x": "zzz"})
    assert out[0]["layout"] == "blur_fit"
    assert studio.apply_shot_overrides(shots, None)[0]["layout"] == "face"
