import json
from pathlib import Path

from marrow.captioner import hex_to_bgr
from marrow.models import Word
from marrow.server import App, clean_clip_style


def _words(text="hello bright world today"):
    return [Word(i * 0.4, i * 0.4 + 0.35, t, score=0.5) for i, t in enumerate(text.split())]


def test_rerender_style_preset_and_overrides():
    s = clean_clip_style({"preset": "hormozi",
                          "overrides": {"position": "top", "highlight_color": "#00F060"}})
    assert s == {"preset": "hormozi",
                 "overrides": {"position": "top", "highlight_color": "#00F060"}}
    assert clean_clip_style({"preset": "nope"}) == {"preset": None, "overrides": {}}


def test_rerender_style_flat_backward_compat():
    s = clean_clip_style({"highlight_color": "#FF0000", "uppercase": False})
    assert s == {"preset": None,
                 "overrides": {"highlight_color": "#FF0000", "uppercase": False}}


def test_modal_payload_resolves_to_ass(tmp_path):
    from marrow.captioner import generate_ass

    body_style = {"preset": "hormozi",
                  "overrides": {"position": "top", "highlight_color": "#00F060"}}
    style = clean_clip_style(body_style)  # what queue_rerender now stores
    out = tmp_path / "edit.ass"
    n = generate_ass(_words(), 0.0, 2.0, out,
                     {"preset": style["preset"], "overrides": style["overrides"],
                      "font": "Arial"},
                     1080, 1920, 420)
    assert n > 0
    text = out.read_text(encoding="utf-8")
    assert "Anton" in text                      # hormozi font
    assert hex_to_bgr("#00F060") in text        # override color, not preset default
    assert ",8,60,60,260,1" in text             # top alignment + margin


def _proj2(app, vid):
    (app.work / vid).mkdir(parents=True, exist_ok=True)
    (app.out / vid).mkdir(parents=True, exist_ok=True)
    words = {"model": "small", "words": [[i * 0.4, i * 0.4 + 0.35, f"w{i}"] for i in range(50)]}
    (app.work / vid / "words.json").write_text(json.dumps(words))
    import numpy as np

    np.save(app.work / vid / "energy.npy", np.zeros(100, dtype="float32"))
    media = app.work / vid / "source.mp4"
    media.write_bytes(b"fake-video")
    settings = {"platform": "shorts", "layout": "crop", "captions": True, "zoom": False,
                "caption_style": {"preset": "bold-pop", "overrides": {}}}
    p = {"id": "c1", "name": "t", "source": str(media), "source_kind": "file",
         "status": "done", "stage": "Done", "progress": 1.0, "created": 0,
         "started": 0, "finished": 0, "error": None, "video_id": vid,
         "settings": settings, "clips": [
            {"rank": 1, "start": 0.0, "end": 10.0, "duration": 10.0, "score": 0.9,
             "title": "one", "reason": "", "hashtags": [], "status": "ready",
             "files": {"shorts": "clip_01_shorts.mp4"}, "rev": 111, "thumb": None}]}
    app.projects["c1"] = p
    return p


def test_rerender_persists_clip_style(tmp_path, monkeypatch):
    from marrow import studio as _studio

    app = App(str(tmp_path))
    p = _proj2(app, "vstyle")

    def fake_render(cfg, media_, workdir, words_, rank, start, end, platforms, out_dir, captions_on,
                      shots=None):
        fp = Path(out_dir) / f"clip_{rank:02d}_shorts.mp4"
        fp.write_bytes(b"rendered")
        return {"shorts": fp}

    monkeypatch.setattr(_studio, "render_clip_files", fake_render)
    monkeypatch.setattr(_studio, "make_thumb", lambda *a: False)
    style = {"preset": "hormozi", "overrides": {"position": "top"}}
    app._run_rerender("c1", 1, 0.0, 10.0, True, style, {}, None)
    assert app.clip(p, 1)["style"] == style
    assert app.clip(p, 1)["custom_style"] is True


def test_export_cache_key_includes_edits(tmp_path):
    app = App(str(tmp_path))
    c = {"rank": 1, "start": 0.0, "end": 10.0, "rev": 3,
         "style": {"preset": "bold-pop", "overrides": {}}}
    spec = {"format": "mp4", "quality": "1080p"}
    assert app.export_cache_key(c, spec, {}) == app.export_cache_key(c, spec, {})
    assert app.export_cache_key(c, spec, {"5": "fixed"}) != app.export_cache_key(c, spec, {})
    c2 = dict(c, style={"preset": "hormozi", "overrides": {}})
    assert app.export_cache_key(c, spec, {}) != app.export_cache_key(c2, spec, {})


def test_patch_style_framing_words(tmp_path):
    from marrow.server import App

    app = App(str(tmp_path))
    vid = "vp"
    (app.work / vid).mkdir(parents=True, exist_ok=True)
    (app.out / vid).mkdir(parents=True, exist_ok=True)
    words = {"model": "small", "words": [[0.0, 0.4, "hello"], [0.5, 0.9, "world"]]}
    (app.work / vid / "words.json").write_text(json.dumps(words))
    settings = {"platform": "shorts", "layout": "crop", "captions": True, "zoom": False,
                "caption_style": {"preset": "bold-pop", "overrides": {}}}
    app.projects["e1"] = {"id": "e1", "name": "t", "source": "s", "source_kind": "file",
                           "status": "done", "stage": "Done", "progress": 1.0, "created": 0,
                           "started": 0, "finished": 0, "error": None, "video_id": vid,
                           "settings": settings, "clips": [
            {"rank": 1, "start": 0.0, "end": 1.0, "duration": 1.0, "score": 0.9,
             "title": "t", "reason": "", "hashtags": [], "status": "ready",
             "files": {"shorts": "clip_01_shorts.mp4"}, "rev": 1, "thumb": None}]}
    pub = app.update_clip("e1", 1, {"style": {"preset": "hormozi", "overrides": {"position": "top"}},
                                    "framing": "blur_fit", "words": {"0": "HELLO"}})
    c = app.clip(app.projects["e1"], 1)
    assert c["style"] == {"preset": "hormozi", "overrides": {"position": "top"}}
    assert c["framing"] == "blur_fit" and c["custom_style"] is True
    saved = json.loads((app.work / vid / "words.json").read_text(encoding="utf-8"))
    assert saved["words"][0][2] == "HELLO"
    assert pub["clips"][0]["style"]["preset"] == "hormozi"


def test_waveform_peaks(tmp_path):
    import wave

    from marrow import studio as _studio

    d = tmp_path / "w"
    d.mkdir()
    rate, n = 16000, 16000 * 2
    import array

    with wave.open(str(d / "audio.wav"), "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(rate)
        f.writeframes(array.array("h", [int(10000 * (i % 100 < 50)) for i in range(n)]).tobytes())
    out = _studio.waveform(d, buckets=50)
    assert len(out["peaks"]) == 50 and out["duration"] == 2.0
    assert max(out["peaks"]) == 1.0
    out2 = _studio.waveform(d, buckets=50)  # cached
    assert out2 == out


def test_export_advanced_reaches_ffmpeg(tmp_path, monkeypatch):
    from marrow import studio as _studio
    from marrow.config import load_config

    seen = {}

    def fake_run(args, cwd=None):
        seen["args"] = [str(a) for a in args]
        Path(seen["args"][-1]).write_bytes(b"x")

    monkeypatch.setattr(_studio, "run_ffmpeg", fake_run)
    cfg = load_config("config.yaml")
    words = _words()
    out = tmp_path / "adv.mp4"
    _studio.export_clip(cfg, tmp_path / "in.mp4", tmp_path, words, 1, 0.0, 2.0,
                        {"format": "mp4", "quality": "1080p", "captions": False,
                         "platform": "shorts", "framing": "crop",
                         "advanced": {"crf": 18, "video_mbps": 12, "audio_kbps": 192, "fps": 0}},
                        out)
    args = seen["args"]
    assert ("-crf" in args and "18" in args) or ("-cq" in args and "18" in args)
    assert "-maxrate" in args and "12.0M" in args
    assert "192k" in args
