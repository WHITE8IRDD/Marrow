from pathlib import Path

from marrow import studio
from marrow.downloader import FORMAT_LADDER, PLAYER_CLIENTS, ydl_opts
from marrow.highlight_scorer import _validate
from marrow.server import App


def test_ydl_opts_cookies_retries_resume():
    o = ydl_opts({"cookies": {"from_browser": "chrome", "cookiefile": ""}}, {"format": "b"})
    assert o["cookiesfrombrowser"] == ("chrome",)
    assert o["retries"] == 10 and o["fragment_retries"] == 10
    assert o["continuedl"] is True
    assert callable(o["retry_sleep_functions"]["http"])
    assert o["retry_sleep_functions"]["http"](10) == 30
    o2 = ydl_opts({})
    assert "cookiesfrombrowser" not in o2 and "cookiefile" not in o2
    assert FORMAT_LADDER[0].startswith("bv*") and "web" in PLAYER_CLIENTS and "android" in PLAYER_CLIENTS


def test_error_clears_live_state(tmp_path):
    app = App(str(tmp_path))
    p = {"id": "a1b2c3", "name": "t", "source": "u", "source_kind": "url",
         "status": "running", "stage": "Transcribing", "progress": 0.5, "created": 0,
         "started": 0, "finished": None, "error": None, "video_id": "v",
         "settings": {"platform": "shorts"}, "clips": [],
         "log": ["> ANALYSIS_THREAD_01: ACTIVE", "[  1.00s -> 2.00s] hello",
                 "> AUDIO_TRANSCRIPT: PROCESSING"],
         "scan": {"t": 1.0}, "candidates": [{"s": 0, "e": 5}]}
    app.projects["a1b2c3"] = p
    app._clear_live(p)
    pub = app.public(p)
    blob = str(pub.get("log")) + str(pub.get("scan")) + str(pub.get("candidates"))
    assert "ANALYSIS_THREAD" not in blob and "AUDIO_TRANSCRIPT" not in blob
    assert pub.get("log") in (None, []) and pub.get("scan") is None


def test_export_cache_key(tmp_path):
    app = App(str(tmp_path))
    c = {"rank": 1, "start": 0.0, "end": 10.0, "rev": 5}
    s1 = {"format": "mp4", "quality": "1080p"}
    assert app.export_cache_key(c, s1) == app.export_cache_key(c, dict(s1))
    assert app.export_cache_key(c, s1) != app.export_cache_key(c, {**s1, "quality": "720p"})
    c2 = dict(c, rev=6)
    assert app.export_cache_key(c, s1) != app.export_cache_key(c2, s1)


def test_quality_encoder_mapping():
    assert studio.pick_export_encoder(720, "auto") in ("h264_nvenc", "libx264")
    assert studio.pick_export_encoder(1440, "auto") in ("hevc_nvenc", "libx264")


def test_clean_export_spec_falls_back():
    import tempfile

    app = App(tempfile.mkdtemp())
    s = app.clean_export_spec({"format": "avi", "quality": "8k", "framing": "zoom",
                               "style": {"preset": "nope", "overrides": {"position": "moon"}}})
    assert s["format"] == "mp4" and s["quality"] == "1080p" and s["framing"] is None
    assert s["style"] == {"preset": None, "overrides": {}}
    s2 = app.clean_export_spec({"style": {"preset": "hormozi", "overrides": {"position": "top"}}})
    assert s2["style"]["preset"] == "hormozi" and s2["style"]["overrides"] == {"position": "top"}


def test_batch_item_validation():
    good = {"hook": 9, "standalone": 8, "emotion": 7, "payoff": 6,
            "title": "T", "reason": "r", "hashtags": ["#A", "b"]}
    assert _validate(good)["hashtags"] == ["a", "b"]
    assert _validate({"hook": "x"}) is None


def test_create_with_probe_copies_preview(tmp_path):
    from marrow import probe as _probe

    (tmp_path / "work").mkdir()
    pdir = tmp_path / "probes" / "abc123def456"
    pdir.mkdir(parents=True)
    (pdir / "preview.mp4").write_bytes(b"fake-video-bytes")
    (pdir / "strip.jpg").write_bytes(b"fake-strip-bytes")
    _probe.PROBES["abc123def456"] = {
        "state": "ready", "progress": 1.0, "dir": str(pdir), "error": None,
        "born": __import__("time").time(), "info": {"title": "Real Title Here", "channel": "ch",
                            "duration": 100, "live": False,
                            "url": "https://example.com/v", "video_id": "vid9"},
    }
    try:
        import tempfile

        home = Path(tempfile.mkdtemp())
        app = App(str(home))
        (home / "work").mkdir(exist_ok=True)
        import marrow.server as _srv

        orig = _srv.App.config_for
        _srv.App.config_for = lambda self, *a, **k: {"cache_dir": str(home / "work")}
        try:
            p = app.create_project({"probe_id": "abc123def456", "settings": {}})
        finally:
            _srv.App.config_for = orig
        assert p["name"] == "Real Title Here"
        assert (home / "work" / "vid9" / "proxy.mp4").read_bytes() == b"fake-video-bytes"
        assert (home / "work" / "vid9" / "strip.jpg").read_bytes() == b"fake-strip-bytes"
    finally:
        _probe.PROBES.pop("abc123def456", None)
