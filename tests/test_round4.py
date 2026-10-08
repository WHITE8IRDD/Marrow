import importlib.util
import json
from pathlib import Path

from marrow import studio
from marrow.captioner import generate_ass
from marrow.caption_styles import resolve_style
from marrow.models import Word
from marrow.server import App, clean_global_settings

ASS_CHECK = Path(__file__).resolve().parents[1] / "scripts" / "ass_check.py"


def _load_ass_check():
    spec = importlib.util.spec_from_file_location("ass_check", ASS_CHECK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_word_pace_merges_fast_words(tmp_path):
    words = [Word(i * 0.12, i * 0.12 + 0.10, t, score=0.5)
             for i, t in enumerate("a b c d e f".split())]
    out = tmp_path / "pace.ass"
    n = generate_ass(words, 0.0, 2.0, out, {"preset": "one-word", "overrides": {}})
    assert 0 < n < 6  # 0.12s spacing merges into fewer events
    mod = _load_ass_check()
    assert mod.check_file(str(out)) == []
    assert mod.check_starts(str(out), 0.15) == []


def test_word_pace_punctuation_holds(tmp_path):
    words = [Word(0.0, 0.3, "stop.", score=0.5), Word(0.5, 0.8, "go", score=0.5)]
    out = tmp_path / "punct.ass"
    generate_ass(words, 0.0, 2.0, out, {"preset": "one-word", "overrides": {}})
    mod = _load_ass_check()
    assert mod.check_file(str(out)) == []
    text = out.read_text(encoding="utf-8")
    assert "STOP" in text  # one-word preset is uppercase; period stripped by strip_punct


def test_pace_setting_flows():
    st = resolve_style(None, None, {"min_gap": 0.28})
    assert st["min_gap"] == 0.28
    assert resolve_style(None, None, {})["min_gap"] == 0.22
    cfg = clean_global_settings({"captions": {"min_gap": 0.16}})
    assert cfg["captions"]["min_gap"] == 0.16
    assert clean_global_settings({})["captions"]["min_gap"] == 0.22
    assert clean_global_settings({"captions": {"min_gap": 9}})["captions"]["min_gap"] == 0.22


def _proj(app, vid, settings):
    (app.work / vid).mkdir(parents=True, exist_ok=True)
    (app.out / vid).mkdir(parents=True, exist_ok=True)
    words = {"model": "small", "words": [[i * 0.4, i * 0.4 + 0.35, f"w{i}"] for i in range(50)]}
    (app.work / vid / "words.json").write_text(json.dumps(words))
    import numpy as np

    np.save(app.work / vid / "energy.npy", np.zeros(100, dtype="float32"))
    media = app.work / vid / "source.mp4"
    media.write_bytes(b"fake-video")
    p = {"id": "a1", "name": "t", "source": str(media), "source_kind": "file",
         "status": "done", "stage": "Done", "progress": 1.0, "created": 0,
         "started": 0, "finished": 0, "error": None, "video_id": vid,
         "settings": settings, "clips": [
            {"rank": 1, "start": 0.0, "end": 10.0, "duration": 10.0, "score": 0.9,
             "title": "one", "reason": "", "hashtags": [], "status": "ready",
             "files": {"shorts": "clip_01_shorts.mp4"}, "rev": 111, "thumb": None},
            {"rank": 2, "start": 10.0, "end": 20.0, "duration": 10.0, "score": 0.8,
             "title": "two", "reason": "", "hashtags": [], "status": "ready",
             "files": {"shorts": "clip_02_shorts.mp4"}, "rev": 222, "thumb": None}]}
    app.projects["a1"] = p
    return p


def test_rerender_is_clip_scoped(tmp_path, monkeypatch):
    from marrow import studio as _studio

    app = App(str(tmp_path))
    settings = {"platform": "shorts", "layout": "crop", "captions": True, "zoom": False,
                "caption_style": {"preset": "bold-pop", "overrides": {}}}
    p = _proj(app, "v1", settings)
    calls = []

    def fake_render(cfg, media_, workdir, words_, rank, start, end, platforms, out_dir, captions_on):
        calls.append(rank)
        fp = Path(out_dir) / f"clip_{rank:02d}_shorts.mp4"
        fp.write_bytes(b"rendered")
        return {"shorts": fp}

    monkeypatch.setattr(_studio, "render_clip_files", fake_render)
    monkeypatch.setattr(_studio, "make_thumb", lambda *a: False)
    app._run_rerender("a1", 1, 0.0, 10.0, True, {}, {})
    c1, c2 = app.clip(p, 1), app.clip(p, 2)
    assert calls == [1]  # only clip 1 rendered
    assert c2["rev"] == 222 and c2["files"] == {"shorts": "clip_02_shorts.mp4"}
    assert c2["title"] == "two"
    assert c1["rev"] != 111  # clip 1 got a fresh cache-busting rev

    app._run_rerender("a1", 2, 10.0, 20.0, True, {}, {})
    c1b, c2b = app.clip(p, 1), app.clip(p, 2)
    assert calls == [1, 2]
    assert c1b["rev"] == c1["rev"]  # clip 1 untouched by clip 2's render


def test_proxy_flags_drive_video_mount(tmp_path):
    app = App(str(tmp_path))
    vid = "v9"
    (app.work / vid).mkdir(parents=True, exist_ok=True)
    p = {"id": "b2", "name": "t", "source": "u", "source_kind": "url",
         "status": "running", "stage": "Transcribing", "progress": 0.2, "created": 0,
         "started": 0, "finished": None, "error": None, "video_id": vid,
         "settings": {"platform": "shorts"}, "clips": []}
    app.projects["b2"] = p
    assert app.public(p)["proxy"] is False
    (app.work / vid / "proxy.mp4").write_bytes(b"fake")
    (app.work / vid / "strip.jpg").write_bytes(b"fake")
    pub = app.public(p)
    assert pub["proxy"] is True and pub["strip"] is True
