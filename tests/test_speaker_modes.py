"""Speaker framing modes: auto / force two-up / off.

Covers the three promises of the feature:
* AUTO only stacks two *different* faces that are genuinely on screen together,
  so shot/reverse-shot footage is never duplicated.
* FORCE TWO-UP always produces two panels — from two distinct co-present faces
  when they exist, otherwise from the frame's own left/right views — and never
  shows one speaker twice. It also works with no face detection at all.
* The chosen mode travels through the processing, regeneration and export paths
  into the rendered filter graph, and the legacy `split_screen` boolean keeps
  working.
"""
import json
from pathlib import Path
import pytest

import marrow.layout as L
import marrow.renderer as R
import marrow.studio as studio
from marrow.models import Word
from marrow.server import clean_job_settings, job_overrides


# --------------------------------------------------------------- mode plumbing
def test_normalize_speaker_mode_accepts_new_names_and_legacy_boolean():
    assert L.normalize_speaker_mode("auto") == "auto"
    assert L.normalize_speaker_mode("two_up") == "two_up"
    assert L.normalize_speaker_mode("force-two-up") == "two_up"
    assert L.normalize_speaker_mode("off") == "off"
    assert L.normalize_speaker_mode("nonsense", True) == "auto"
    assert L.normalize_speaker_mode(None, True) == "auto"
    assert L.normalize_speaker_mode(None, False) == "off"
    assert L.normalize_speaker_mode(None, None) == "auto"
    # the legacy boolean still decides when no mode is given
    assert L.normalize_speaker_mode(True) == "auto"
    assert L.normalize_speaker_mode(False) == "off"
    # ...but an explicit mode wins over a stale boolean
    assert L.normalize_speaker_mode("two_up", False) == "two_up"


def test_speaker_mode_for_reads_config_and_falls_back_to_split_screen():
    assert L.speaker_mode_for({"speaker_mode": "two_up", "split_screen": False}) == "two_up"
    assert L.speaker_mode_for({"split_screen": False}) == "off"       # old config.yaml
    assert L.speaker_mode_for({"split_screen": True}) == "auto"
    assert L.speaker_mode_for({}) == "auto"
    assert L.speaker_mode_for({"split_screen": False}, override="auto") == "auto"
    assert L.split_screen_flag("two_up") is True and L.split_screen_flag("off") is False


def test_job_settings_keep_the_legacy_boolean_in_step():
    two = clean_job_settings({"speaker_mode": "two_up"})
    assert two["speaker_mode"] == "two_up" and two["split_screen"] is True
    old_client_off = clean_job_settings({"split_screen": False})
    assert old_client_off["speaker_mode"] == "off"
    assert job_overrides(old_client_off)["render"] == {"speaker_mode": "off", "split_screen": False}
    # a payload written before modes existed still disables the split
    assert job_overrides({"captions": True, "caption_style": {"preset": None, "overrides": {}},
                          "zoom": False, "split_screen": False})["render"]["speaker_mode"] == "off"


# ------------------------------------------------------------------ layout rules
def _two_face_stubs(monkeypatch, times, faces_fn):
    import numpy as np

    monkeypatch.setattr(L, "get_detector", lambda: object())
    monkeypatch.setattr(L, "detect_shots", lambda *a: [])
    monkeypatch.setattr(
        L, "sample_frames",
        lambda *a, **k: [(t, np.full((180, 320, 3), i, np.uint8)) for i, t in enumerate(times)])
    monkeypatch.setattr(L, "detect_faces", faces_fn)


def test_face_panel_crops_center_speakers_near_source_edges():
    """Edge clamping used to leave each face toward the outside of its panel."""
    width, height = 1280, 720
    centers = (180.0, 1100.0)
    panels = L._panels([(centers[0], 260.0, 80.0, 0.0),
                        (centers[1], 260.0, 80.0, 0.0)], width, height)

    assert len(panels) == 2
    for center, panel in zip(centers, panels):
        # The face anchor is the horizontal center of its crop (within the even
        # pixel alignment needed by yuv420p), and every crop stays in-bounds.
        assert abs(panel["x"] + panel["w"] / 2 - center) <= 1
        assert 0 <= panel["x"] <= width - panel["w"]
        assert panel["w"] / panel["h"] == pytest.approx(9 / 8, abs=0.01)
    assert panels[0]["w"] < width * 0.45   # edge subjects get a tighter centered crop
    assert panels[1]["w"] < width * 0.45


def test_auto_still_refuses_shot_reverse_shot(monkeypatch, tmp_path):
    times = [i * 0.5 for i in range(10)]

    def alternating(frame, _det):
        i = int(frame[0, 0, 0])
        faces = []
        if i < 6:
            faces.append((150, 50, 80, 80, 0.9))
        if i >= 4:
            faces.append((1050, 50, 80, 80, 0.9))
        return faces

    _two_face_stubs(monkeypatch, times, alternating)
    shots = L.analyze("nonexistent.mp4", 0.0, 5.0, workdir=tmp_path, speaker_mode="auto")
    assert shots[0]["layout"] == "face" and "panels" not in shots[0]


def test_two_up_forces_panels_from_two_co_present_faces(monkeypatch, tmp_path):
    times = [i * 0.5 for i in range(10)]
    _two_face_stubs(monkeypatch, times, lambda f, d: [(150, 50, 80, 80, 0.9), (1050, 50, 80, 80, 0.9)])
    shot = L.analyze("nonexistent.mp4", 0.0, 5.0, workdir=tmp_path, speaker_mode="two_up")[0]
    assert shot["layout"] == "stacked" and shot["views"] == "faces"
    assert len(shot["panels"]) == 2
    a, b = shot["panels"]
    assert (a["x"], a["y"], a["w"], a["h"]) != (b["x"], b["y"], b["w"], b["h"])
    assert (tmp_path / "shots_0_5_two_up.json").exists()   # own cache entry


def test_two_up_stacks_even_when_faces_never_coexist(monkeypatch, tmp_path):
    """Shot/reverse-shot in forced mode: one panel per real person (never one
    person's face in both panels), which AUTO deliberately refuses to do."""
    times = [i * 0.5 for i in range(10)]

    def alternating(frame, _det):
        return [(150, 50, 80, 80, 0.9)] if int(frame[0, 0, 0]) < 5 else [(1050, 50, 80, 80, 0.9)]

    _two_face_stubs(monkeypatch, times, alternating)
    shot = L.analyze("nonexistent.mp4", 0.0, 5.0, workdir=tmp_path, speaker_mode="two_up")[0]
    assert shot["layout"] == "stacked" and shot["views"] == "faces"
    assert shot["panels"][0] != shot["panels"][1]


def test_two_up_without_face_detection_uses_two_frame_views(monkeypatch, tmp_path):
    monkeypatch.setattr(L, "get_detector", lambda: None)
    shots = L.analyze("nonexistent.mp4", 0.0, 8.0, speaker_mode="two_up")
    assert shots == [{"start": 0.0, "end": 8.0, "layout": "stacked",
                      "views": "frame", "mode": "two_up"}]
    # auto/off keep the configured fallback instead
    assert L.analyze("nonexistent.mp4", 0.0, 8.0, speaker_mode="auto",
                     fallback="blur_fit")[0]["layout"] == "blur_fit"
    assert L.analyze("nonexistent.mp4", 0.0, 8.0, split_screen=False,
                     fallback="crop")[0]["layout"] == "crop"


def test_single_face_is_never_duplicated_into_two_panels(monkeypatch, tmp_path):
    """One head detected twice (a mirror or a duplicate box) is still one speaker."""
    times = [i * 0.5 for i in range(10)]
    _two_face_stubs(monkeypatch, times,
                    lambda f, d: [(200, 60, 90, 90, 0.9), (215, 70, 88, 88, 0.88)])
    auto = L.analyze("nonexistent.mp4", 0.0, 5.0, workdir=tmp_path, speaker_mode="auto")[0]
    assert auto["layout"] != "stacked" and "panels" not in auto
    two = L.analyze("nonexistent.mp4", 0.0, 5.0, workdir=tmp_path, speaker_mode="two_up")[0]
    assert two["layout"] == "stacked"
    assert two["views"] == "frame"            # frame halves, not the same face twice
    assert "panels" not in two


def test_three_speakers_pick_two_distinct_views(monkeypatch, tmp_path):
    """3+ visible speakers: two of them get panels; nobody is invented or reused."""
    times = [i * 0.5 for i in range(10)]
    faces = [(150, 50, 80, 80, 0.95), (600, 60, 70, 70, 0.9), (1080, 55, 60, 60, 0.85)]
    _two_face_stubs(monkeypatch, times, lambda f, d: list(faces))
    for mode in ("auto", "two_up"):
        shot = L.analyze("nonexistent.mp4", 0.0, 5.0, workdir=tmp_path, speaker_mode=mode)[0]
        assert shot["layout"] == "stacked", mode
        panels = shot["panels"]
        assert len(panels) == 2                                   # never a third panel
        assert panels[0] != panels[1]                             # two distinct views
        assert shot["faces"] == 3
        # the two largest faces are used, left panel first
        assert panels[0]["x"] < panels[1]["x"]
        assert panels[0]["w"] >= 200 and panels[1]["w"] >= 200


def test_analyze_uses_scan_source_and_scales_panels_back(monkeypatch, tmp_path):
    """Analysing the 480p proxy must not shrink the panels: coordinates are scaled."""
    import numpy as np

    calls = {}

    class FakeCap:
        def __init__(self, path):
            self.path, self.fps = str(path), 30.0
            calls.setdefault("opened", []).append(self.path)

        def isOpened(self):
            return True

        def get(self, prop):
            import cv2

            if prop == cv2.CAP_PROP_FRAME_WIDTH:
                return 640.0 if "proxy" in self.path else 1280.0
            if prop == cv2.CAP_PROP_FRAME_HEIGHT:
                return 360.0 if "proxy" in self.path else 720.0
            if prop == cv2.CAP_PROP_FPS:
                return self.fps
            return 0.0

        def set(self, *a):
            return True

        def read(self):
            return False, None

        def release(self):
            pass

    import cv2

    monkeypatch.setattr(cv2, "VideoCapture", FakeCap)
    monkeypatch.setattr(L, "get_detector", lambda: object())
    monkeypatch.setattr(L, "detect_shots", lambda *a: [])
    monkeypatch.setattr(L, "sample_frames", lambda *a, **k: [(0.0, np.zeros((360, 640, 3), np.uint8)),
                                                             (0.5, np.zeros((360, 640, 3), np.uint8))])
    monkeypatch.setattr(L, "detect_faces", lambda f, d: [(100, 60, 60, 60, 0.9), (480, 60, 60, 60, 0.9)])
    proxy = tmp_path / "proxy.mp4"
    proxy.write_bytes(b"x")
    src = tmp_path / "src.mp4"
    src.write_bytes(b"x")
    shot = L.analyze(str(src), 0.0, 2.0, speaker_mode="two_up", scan_src=str(proxy))[0]
    assert any("proxy" in p for p in calls["opened"])            # analysis ran on the proxy
    # 60 px wide face at 640 px wide proxy -> 120 px in the 1280 px source
    assert shot["panels"][0]["w"] >= 200
    assert shot["panels"][1]["x"] > shot["panels"][0]["x"]


# ------------------------------------------------------------------- rendering
def _fake_ffmpeg(seen):
    """Record ffmpeg args and create the file ffmpeg was asked to write."""

    def fake_run(args, cwd=None):
        args = [str(a) for a in args]
        seen.append(args)
        out = Path(args[-1])
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"x" * 2000)
        except OSError:
            pass

        class R_:
            stderr = ""
        return R_()

    return fake_run


def _capture_render(monkeypatch, module=R):
    seen = []
    monkeypatch.setattr(module, "run_ffmpeg", _fake_ffmpeg(seen))
    return seen


def _render_graph(monkeypatch, layout, shot, tmp_path, cfg=None, **kw):
    seen = _capture_render(monkeypatch, R)
    cfg = cfg or {"platforms": {"shorts": {"res_x": 360, "res_y": 640, "max_duration": 180,
                                           "caption_margin_v": 420},
                                "reels": {"res_x": 360, "res_y": 640, "max_duration": 90,
                                          "caption_margin_v": 460}},
                  "render": {"layout": "crop", "encoder": "libx264", "preset": "ultrafast",
                             "crf": 30, "fps": 30, "loudnorm": False},
                  "zoom": {"enabled": False}}
    R.render_clip(str(tmp_path / "in.mp4"), 0.0, 4.0, None, tmp_path / "out.mp4", cfg,
                  "shorts", layout=layout, shot=shot)
    args = seen[-1]
    return args[args.index("-filter_complex") + 1]


def _shots_for(monkeypatch, tmp_path, mode, faces_fn, times=None):
    times = times or [i * 0.5 for i in range(10)]
    _two_face_stubs(monkeypatch, times, faces_fn)
    return L.analyze("nonexistent.mp4", 0.0, 5.0, workdir=tmp_path, speaker_mode=mode)


def test_selected_mode_reaches_the_rendered_filter_graph(monkeypatch, tmp_path):
    co_present = lambda f, d: [(150, 50, 80, 80, 0.9), (1050, 50, 80, 80, 0.9)]
    auto = _shots_for(monkeypatch, tmp_path, "auto", co_present)
    two_up = _shots_for(monkeypatch, tmp_path, "two_up", co_present)
    off = _shots_for(monkeypatch, tmp_path, "off", co_present)

    auto_graph = _render_graph(monkeypatch, auto[0]["layout"], auto[0], tmp_path)
    two_graph = _render_graph(monkeypatch, two_up[0]["layout"], two_up[0], tmp_path)
    off_graph = _render_graph(monkeypatch, off[0]["layout"], off[0], tmp_path)

    assert "vstack=inputs=2" in auto_graph
    for panel in auto[0]["panels"]:
        assert f'crop={panel["w"]}:{panel["h"]}:{panel["x"]}:{panel["y"]}' in auto_graph
    assert "vstack=inputs=2" in two_graph
    assert "split=2[ta][tb]" in auto_graph and "split=2[ta][tb]" in two_graph
    assert "vstack" not in off_graph and "split=2" not in off_graph


def test_two_up_without_faces_reaches_the_left_right_split_graph(monkeypatch, tmp_path):
    monkeypatch.setattr(L, "get_detector", lambda: None)
    shots = L.analyze("nonexistent.mp4", 0.0, 6.0, speaker_mode="two_up")
    graph = _render_graph(monkeypatch, shots[0]["layout"], None, tmp_path)
    assert "vstack=inputs=2" in graph
    assert "x='iw/4-ow/2'" in graph and "x='3*iw/4-ow/2'" in graph   # the frame's two views
    assert "crop='min(iw,ih*" not in graph                            # no single centre crop


def test_export_path_uses_the_clip_speaker_mode(monkeypatch, tmp_path):
    """Exports analyse with the configured mode and stack when it says two-up."""
    from marrow.config import load_config

    seen = {}
    real_analyze = L.analyze

    def spy_analyze(src, start, end, **kw):
        seen["kw"] = kw
        return [{"start": start, "end": end, "layout": "stacked", "views": "frame",
                 "mode": "two_up"}]

    monkeypatch.setattr(L, "analyze", spy_analyze)
    captured = []
    monkeypatch.setattr(studio, "run_ffmpeg", _fake_ffmpeg(captured))
    cfg = load_config("config.yaml")
    cfg["render"]["speaker_mode"] = "two_up"
    cfg["render"]["encoder"] = "libx264"
    cfg["platforms"]["shorts"].update(res_x=360, res_y=640)
    words = [Word(0.0, 1.0, "hi", score=0.5)]
    out = tmp_path / "exp.mp4"
    studious = studio.export_clip(cfg, tmp_path / "in.mp4", tmp_path, words, 1, 0.0, 2.0,
                                  {"format": "mp4", "quality": "480p", "captions": False,
                                   "platform": "shorts", "framing": "auto",
                                   "advanced": {"fps": 0, "crf": None, "video_mbps": None,
                                                "audio_kbps": None}},
                                  out)
    assert studious[0].endswith("exp.mp4")
    assert seen["kw"].get("speaker_mode") == "two_up"
    graph = captured[0][captured[0].index("-filter_complex") + 1]
    assert "vstack=inputs=2" in graph
    assert L.analyze is spy_analyze and real_analyze is not spy_analyze


def test_uniform_two_up_renders_in_one_pass_without_concat(monkeypatch, tmp_path):
    """All-frame-view clips skip the segment-and-concat path (fewer encodes)."""
    calls = []
    monkeypatch.setattr(R, "run_ffmpeg", _fake_ffmpeg(calls))
    cfg = {"platforms": {"shorts": {"res_x": 360, "res_y": 640, "max_duration": 180,
                                    "caption_margin_v": 420}},
           "render": {"layout": "crop", "encoder": "libx264", "preset": "ultrafast",
                      "crf": 30, "fps": 30, "loudnorm": False},
           "zoom": {"enabled": False}, "captions": {"enabled": False}}
    shots = [{"start": 0.0, "end": 2.0, "layout": "stacked", "views": "frame"},
             {"start": 2.0, "end": 4.0, "layout": "stacked", "views": "frame"}]
    assert studio.uniform_layout(shots) == "stacked"
    assert studio.uniform_layout([{"layout": "stacked", "panels": [1, 2]}]) is None
    assert studio.uniform_layout([{"layout": "crop"}]) is None
    out = studio.render_clip_files(cfg, tmp_path / "in.mp4", tmp_path, [], 1, 0.0, 4.0,
                                   ["shorts"], tmp_path, False, shots)
    graphs = [c[c.index("-filter_complex") + 1] for c in calls if "-filter_complex" in c]
    assert len(graphs) == 1 and "vstack=inputs=2" in graphs[0]     # one pass, no segments
    assert out["shorts"].name == "clip_01_shorts.mp4"


def test_regeneration_path_forwards_the_mode(monkeypatch, tmp_path):
    from marrow.server import App

    app = App(str(tmp_path))
    vid = "v1"
    (app.work / vid).mkdir(parents=True, exist_ok=True)
    (app.out / vid).mkdir(parents=True, exist_ok=True)
    words = {"model": "small", "words": [[i * 0.4, i * 0.4 + 0.35, f"w{i}"] for i in range(40)]}
    (app.work / vid / "words.json").write_text(json.dumps(words))
    import numpy as np

    np.save(app.work / vid / "energy.npy", np.zeros(64, dtype="float32"))
    (app.work / vid / "source.mp4").write_bytes(b"fake")
    settings = clean_job_settings({"speaker_mode": "two_up"})
    app.projects["a1"] = {
        "id": "a1", "name": "t", "source": str(app.work / vid / "source.mp4"),
        "source_kind": "file", "status": "done", "stage": "Done", "progress": 1.0, "created": 0,
        "started": 0, "finished": 0, "error": None, "video_id": vid, "settings": settings,
        "clips": [{"rank": 1, "start": 0.0, "end": 4.0, "duration": 4.0, "score": 0.9,
                   "title": "one", "reason": "", "hashtags": [], "status": "ready",
                   "files": {"shorts": "clip_01_shorts.mp4"}, "rev": 1, "thumb": None}],
    }
    seen = {}
    monkeypatch.setattr(L, "analyze", lambda src, s, e, **kw: seen.update(kw) or
                        [{"start": s, "end": e, "layout": "stacked", "views": "frame"}])
    monkeypatch.setattr(studio, "render_clip_files",
                        lambda *a, **k: {"shorts": Path(a[8]) / "clip_01_shorts.mp4"})
    monkeypatch.setattr(studio, "make_thumb", lambda *a: False)
    app._run_rerender("a1", 1, 0.0, 4.0, True, {}, {})
    assert seen.get("speaker_mode") == "two_up"
    assert seen.get("split_screen") is True


def test_pipeline_threads_the_mode_into_every_clip(monkeypatch, tmp_path):
    """The processing path: selected mode -> analyse(scan_src=proxy) -> graph."""
    import numpy as np

    import marrow.pipeline as P
    from marrow.config import load_config

    src_video = tmp_path / "talk.mp4"
    studio.run_ffmpeg(["-f", "lavfi", "-i", "testsrc2=s=640x360:r=30:d=9",
                       "-f", "lavfi", "-i", "sine=frequency=440:duration=9",
                       "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                       "-c:a", "aac", "-shortest", src_video])
    cfg_cache = tmp_path / "work"
    words = [Word(i * 0.6, i * 0.6 + 0.55, t, score=0.5)
             for i, t in enumerate(("hello there friends . today we talk . about "
                                    "framing two speakers . and why it matters .").split())]
    monkeypatch.setattr(P, "transcribe", lambda *a, **k: (words, "en"))
    monkeypatch.setattr(P, "compute_energy", lambda *a, **k: (np.ones(16000, dtype="float32"), 31.25))
    monkeypatch.setattr(L, "get_detector", lambda: None)          # no faces anywhere
    monkeypatch.setattr(L, "detect_shots", lambda *a: [])

    graphs = []
    fake_run = _fake_ffmpeg(graphs)
    monkeypatch.setattr(R, "run_ffmpeg", fake_run)
    monkeypatch.setattr(R, "run_ffmpeg_progress", lambda args, total, cb, cwd=None: fake_run(args, cwd))
    monkeypatch.setattr(studio, "run_ffmpeg", fake_run)

    cfg = load_config("config.yaml")
    cfg["cache_dir"] = str(cfg_cache)
    cfg["render"].update(speaker_mode="two_up", encoder="libx264", preset="ultrafast",
                         crf=32, loudnorm=False)
    cfg["captions"]["preset"] = "bold-pop"
    cfg["llm"]["enabled"] = False
    cfg["clip"].update(target_count=1, min_duration=4, max_duration=12)
    cfg["platforms"]["shorts"].update(res_x=360, res_y=640)
    results = P.run_pipeline(str(src_video), output_dir=str(tmp_path / "out"),
                             config=cfg, platform="shorts", clip_count=1,
                             speaker_mode="two_up")
    assert results and results[0]["shots"][0]["layout"] == "stacked"
    render_graphs = [g[g.index("-filter_complex") + 1] for g in graphs if "-filter_complex" in g]
    assert any("vstack=inputs=2" in g for g in render_graphs)       # two-up reached ffmpeg
    assert not any("crop='min(iw,ih*" in g for g in render_graphs)  # not a centre crop
    assert not any("concat" in " ".join(g) for g in graphs)         # no segment+concat step
    manifest = json.loads((tmp_path / "out" / src_video.stem / "manifest.json").read_text())
    assert manifest["clips"][0]["shots"][0]["views"] == "frame"


def test_legacy_split_screen_false_keeps_the_pipeline_unstacked(monkeypatch, tmp_path):
    import numpy as np

    import marrow.pipeline as P
    from marrow.config import load_config

    src_video = tmp_path / "solo.mp4"
    studio.run_ffmpeg(["-f", "lavfi", "-i", "testsrc2=s=640x360:r=30:d=9",
                       "-f", "lavfi", "-i", "sine=frequency=440:duration=9",
                       "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                       "-c:a", "aac", "-shortest", src_video])
    words = [Word(i * 0.6, i * 0.6 + 0.55, t, score=0.5)
             for i, t in enumerate(("one two three four . five six seven eight . "
                                    "nine ten eleven twelve . thirteen fourteen fifteen .").split())]
    monkeypatch.setattr(P, "transcribe", lambda *a, **k: (words, "en"))
    monkeypatch.setattr(P, "compute_energy", lambda *a, **k: (np.ones(16000, dtype="float32"), 31.25))
    monkeypatch.setattr(L, "get_detector", lambda: None)

    graphs = []
    fake_run = _fake_ffmpeg(graphs)
    monkeypatch.setattr(R, "run_ffmpeg", fake_run)
    monkeypatch.setattr(R, "run_ffmpeg_progress", lambda args, total, cb, cwd=None: fake_run(args, cwd))
    monkeypatch.setattr(studio, "run_ffmpeg", fake_run)
    cfg = load_config("config.yaml")
    cfg["cache_dir"] = str(tmp_path / "work")
    cfg["render"].update(split_screen=False, encoder="libx264", preset="ultrafast",
                         crf=32, loudnorm=False)
    cfg["render"].pop("speaker_mode", None)        # as written by an older version
    cfg["llm"]["enabled"] = False
    cfg["clip"].update(target_count=1, min_duration=4, max_duration=12)
    cfg["platforms"]["shorts"].update(res_x=360, res_y=640)
    results = P.run_pipeline(str(src_video), output_dir=str(tmp_path / "out"), config=cfg,
                             platform="shorts", clip_count=1)
    assert results
    render_graphs = [g[g.index("-filter_complex") + 1] for g in graphs if "-filter_complex" in g]
    assert render_graphs and not any("vstack" in g for g in render_graphs)


@pytest.mark.skipif(not (Path("/usr/bin/env").exists()), reason="always runs")
def test_two_up_frame_view_graph_encodes_with_real_ffmpeg(tmp_path):
    """Real ffmpeg must accept the forced two-up graph (real encode, real duration)."""
    import shutil

    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        pytest.skip("ffmpeg not installed")
    from marrow.utils import probe_duration

    src = tmp_path / "src.mp4"
    studio.run_ffmpeg(["-f", "lavfi", "-i", "testsrc2=s=1280x720:r=30:d=3",
                       "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
                       "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                       "-c:a", "aac", "-shortest", src])
    cfg = {"platforms": {"shorts": {"res_x": 360, "res_y": 640, "max_duration": 180,
                                    "caption_margin_v": 420}},
           "render": {"layout": "crop", "encoder": "libx264", "preset": "ultrafast",
                      "crf": 30, "fps": 30, "loudnorm": False},
           "zoom": {"enabled": False}, "captions": {"enabled": False}}
    shots = [{"start": 0.0, "end": 3.0, "layout": "stacked", "views": "frame"}]
    out = studio.render_clip_shots(cfg, src, tmp_path, [], 1, 0.0, 3.0, ["shorts"],
                                   tmp_path, False, shots)
    produced = out["shorts"]
    assert produced.exists() and produced.stat().st_size > 5_000
    assert abs(probe_duration(produced) - 3.0) < 0.35
    # ...and report the encoder that actually did the work, so the UI can say
    # "GPU" or "CPU" truthfully instead of guessing from the config value.
    from marrow import hw

    eng = hw.get_engine()["engines"].get("render")
    assert eng and eng["encoder"] == "libx264" and eng["device"] == "cpu"
    assert "libx264" in eng["label"]


# ------------------------------------------------- Home control + fast paths
def test_legacy_split_screen_field_accepts_a_mode_string():
    """The Home control posts the chosen mode in the legacy field; the server
    has to understand it and still mirror the boolean for older readers."""
    for mode, legacy in (("auto", True), ("two_up", True), ("off", False)):
        s = clean_job_settings({"split_screen": mode})
        assert s["speaker_mode"] == mode
        assert s["split_screen"] is legacy
        assert job_overrides(s)["render"]["speaker_mode"] == mode
    # older booleans keep working, and a stale boolean never overrides a mode
    assert clean_job_settings({"split_screen": False})["speaker_mode"] == "off"
    assert clean_job_settings({"speaker_mode": "two_up", "split_screen": False})["speaker_mode"] == "two_up"
    assert L.normalize_speaker_mode(None, "two_up") == "two_up"
    assert L.normalize_speaker_mode(None, "False") == "off"
    assert L.speaker_mode_for({"split_screen": "two_up"}) == "two_up"


def test_home_exposes_the_three_modes_and_keeps_the_legacy_key():
    js = (Path(__file__).resolve().parents[1] / "marrow" / "web" / "app.js").read_text(encoding="utf-8")
    assert 'data-opt="split_screen"' in js                    # old clients/tests keep finding it
    for mode in ("auto", "two_up", "off"):
        assert f'data-v="{mode}"' in js
    # Short labels that fit the segmented control; the full wording lives in the
    # explanation under it (and in the button's title attribute).
    for label in ('>Auto<', '>Two-up<', '>Off<'):
        assert label in js
    assert "Force two-up" in js
    assert "modeOf" in js and "syncSpeakerModeCopy" in js


def test_sample_frames_converts_only_the_samples_it_keeps(monkeypatch):
    """grab() walks the window, retrieve() converts only the kept frames."""
    calls = {"grab": 0, "retrieve": 0, "read": 0}
    frames = [b"frame%d" % i for i in range(120)]

    class FakeCap:
        def __init__(self, *_a, **_k):
            self.i = -1

        def isOpened(self):
            return True

        def get(self, prop):
            import cv2
            if prop == cv2.CAP_PROP_FPS:
                return 30.0
            if prop == cv2.CAP_PROP_POS_MSEC:
                return (self.i + 1) * (1000.0 / 30.0)
            return self.i + 1

        def set(self, *_a):
            return True

        def grab(self):
            calls["grab"] += 1
            self.i += 1
            return self.i < len(frames)

        def retrieve(self):
            calls["retrieve"] += 1
            return True, frames[self.i]

        def read(self):
            calls["read"] += 1
            self.i += 1
            return (self.i < len(frames)), frames[self.i]

        def release(self):
            pass

    class FakeCV2:
        CAP_PROP_FPS = 5
        CAP_PROP_POS_MSEC = 1
        CAP_PROP_POS_FRAMES = 2
        VideoCapture = FakeCap

    monkeypatch.setitem(__import__("sys").modules, "cv2", FakeCV2)
    samples = L.sample_frames("whatever.mp4", 1.0, 3.0)
    assert samples and len(samples) == 5            # 2 s at 2.5 fps
    assert calls["grab"] > calls["retrieve"]        # every other frame is skipped
    assert calls["read"] == 0
    assert samples[0][1] == b"frame30"              # starts at t=1.0 s


def test_sample_frames_falls_back_to_read_when_grab_fails(monkeypatch):
    calls = {"read": 0}

    class NoGrabCap:
        def __init__(self, *_a, **_k):
            self.i = -1

        def isOpened(self):
            return True

        def get(self, prop):
            import sys
            if prop == sys.modules["cv2"].CAP_PROP_FPS:
                return 30.0
            if prop == sys.modules["cv2"].CAP_PROP_POS_MSEC:
                return (self.i + 1) * (1000.0 / 30.0)
            return self.i + 1

        def set(self, *_a):
            return True

        def grab(self):
            return False

        def read(self):
            calls["read"] += 1
            self.i += 1
            return (self.i < 60), b"f%d" % self.i

        def release(self):
            pass

    class FakeCV2:
        CAP_PROP_FPS = 5
        CAP_PROP_POS_MSEC = 1
        CAP_PROP_POS_FRAMES = 2
        VideoCapture = NoGrabCap

    monkeypatch.setitem(__import__("sys").modules, "cv2", FakeCV2)
    samples = L.sample_frames("whatever.mp4", 0.0, 1.0)
    assert samples and calls["read"] > 0


def test_probe_duration_is_memoised_until_the_file_changes(monkeypatch):
    import marrow.utils as utils

    calls = {"n": 0}
    real_run = utils.subprocess.run

    def counting_run(*a, **kw):
        calls["n"] += 1
        return real_run(*a, **kw)

    src = _tiny_clip()                      # build the clip before counting subprocesses
    monkeypatch.setattr(utils.subprocess, "run", counting_run)
    utils._DURATION_CACHE.clear()
    assert utils.probe_duration(src) > 0
    assert utils.probe_duration(src) > 0
    assert calls["n"] == 1, "the second probe should come from the cache"


_TINY = {}


def _tiny_clip():
    """A cached 1 s testsrc clip for the cheap checks (built once per test run)."""
    if "path" not in _TINY:
        import shutil
        import tempfile

        if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
            pytest.skip("ffmpeg not installed")
        d = Path(tempfile.mkdtemp(prefix="marrow_tiny_"))
        src = d / "tiny.mp4"
        studio.run_ffmpeg(["-f", "lavfi", "-i", "testsrc2=s=320x240:r=30:d=1",
                           "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", src])
        _TINY["path"] = src
    return _TINY["path"]


def test_clip_thumbs_honour_the_scale_and_report_missing_tiles(tmp_path):
    import cv2
    import shutil

    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        pytest.skip("ffmpeg not installed")
    made = studio.make_clip_thumbs(_tiny_clip(), [(1, 0.0), (2, 0.4)], tmp_path, scale="90:160")
    assert set(made) == {1, 2}
    for path in made.values():
        assert path.exists() and path.stat().st_size > 0
        img = cv2.imread(str(path))
        assert img is not None and img.shape[:2] == (160, 90)
    # a source ffmpeg cannot read is reported as a failure instead of raising
    assert studio.make_clip_thumbs(tmp_path / "missing.mp4", [(3, 1.0)], tmp_path,
                                   scale="90:160") == {}


def test_home_mode_control_in_a_real_dom():
    """Runs scripts/ui_check.mjs: the real index.html + app.js inside jsdom, so
    the three-way control is clicked rather than string-matched. Skipped when
    node/jsdom are unavailable (install with `npm install jsdom`)."""
    import shutil
    import subprocess
    import sys

    node = shutil.which("node") or shutil.which("nodejs")
    if not node:
        pytest.skip("node is not installed")
    script = Path(__file__).resolve().parents[1] / "scripts" / "ui_check.mjs"
    probe = subprocess.run([node, "-e", "console.log(require.resolve('jsdom'))"],
                           capture_output=True, text=True)
    if probe.returncode != 0:
        pytest.skip("jsdom is not installed (npm install jsdom)")
    out = subprocess.run([node, str(script)], capture_output=True, text=True, timeout=180)
    assert out.returncode == 0, out.stdout + out.stderr
    assert "all UI checks passed" in out.stdout


def test_hardware_payload_and_ui_agree_on_the_engine_in_use():
    from marrow import hw

    hw.reset()
    hw.set_engine("render", device="cpu", encoder="libx264", label="libx264 (CPU)",
                  fallback="h264_nvenc is unavailable")
    snap = hw.get_engine()
    assert snap["engines"]["render"]["device"] == "cpu"
    assert snap["engines"]["render"]["fallback"].startswith("h264_nvenc")
    hw.reset()
    assert "render" not in hw.get_engine()["engines"]

    js = (Path(__file__).resolve().parents[1] / "marrow" / "web" / "app.js").read_text(encoding="utf-8")
    assert "d.engines" in js and "Fell back to CPU" in js


def test_clip_card_actions_in_a_real_browser():
    """scripts/browser_check.mjs lays the real stylesheet out in Chromium and
    measures the Download/Edit/More row at five widths (jsdom cannot do layout).
    Skipped unless node + puppeteer-core + a Chromium binary are available."""
    import shutil
    import subprocess

    node = shutil.which("node") or shutil.which("nodejs")
    if not node:
        pytest.skip("node is not installed")
    script = Path(__file__).resolve().parents[1] / "scripts" / "browser_check.mjs"
    probe = subprocess.run([node, "-e", "require.resolve('puppeteer-core')"],
                           capture_output=True, text=True,
                           env={**__import__("os").environ,
                                "NODE_PATH": __import__("os").environ.get("NODE_PATH", "")})
    chrome = next((p for p in (__import__("os").environ.get("CHROME_PATH"), "/tmp/chromium",
                               "/usr/bin/chromium", "/usr/bin/chromium-browser",
                               "/usr/bin/google-chrome") if p and Path(p).exists()), None)
    if probe.returncode != 0 or not chrome:
        pytest.skip("puppeteer-core and/or a Chromium binary are not installed")
    out = subprocess.run([node, str(script)], capture_output=True, text=True, timeout=300)
    assert "SKIP" not in out.stdout, out.stdout
    assert out.returncode == 0, out.stdout + out.stderr
    assert "all browser checks passed" in out.stdout
