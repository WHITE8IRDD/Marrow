"""Regression tests for the "video doesn't get fetched" family of bugs.

* live clip URLs must never embed absolute file-system paths (they 404 while rendering)
* a proxy/strip must only appear under its final name once ffmpeg has finished
* the find-video preview must use the saved cookie settings and fall back gracefully
* a corrupt proxy left behind by an older build must be rebuilt, not served forever
"""
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from marrow import probe, studio
from marrow.server import App


def _app(tmp_path):
    return App(str(tmp_path))


def test_live_clip_urls_use_file_names_only(tmp_path):
    app = _app(tmp_path)
    vid = "vlive"
    (app.work / vid).mkdir(parents=True, exist_ok=True)
    abs_file = str(app.out / vid / "clip_01_shorts.mp4")  # what the pipeline stores while rendering
    p = {"id": "live1", "name": "t", "source": "u", "source_kind": "url", "status": "running",
         "stage": "Rendering clip 1/3", "progress": 0.8, "created": 0, "started": 0, "finished": None,
         "error": None, "video_id": vid, "settings": {"platform": "shorts"},
         "clips": [{"rank": 1, "start": 0.0, "end": 20.0, "duration": 20.0, "score": 0.5,
                    "title": "x", "status": "ready", "files": {"shorts": abs_file},
                    "render_pct": 1.0}]}
    app.projects["live1"] = p
    clip = app.public(p)["clips"][0]
    assert clip["urls"] == {"shorts": f"/media/{vid}/clip_01_shorts.mp4?v=0"}
    assert clip["platforms"] == ["shorts"]
    assert "//" not in clip["urls"]["shorts"][len("/media/"):]


def test_proxy_is_written_to_a_part_file_then_renamed(tmp_path, monkeypatch):
    calls = []

    def fake_ffmpeg(args, cwd=None):
        out = Path(args[-1])
        calls.append(out.name)
        if out.name.startswith("proxy"):  # while the proxy encodes, its final name must not exist
            assert not (tmp_path / "proxy.mp4").exists(), "proxy must not appear before encoding ends"
        out.write_bytes(b"encoded")

    monkeypatch.setattr(studio, "run_ffmpeg", fake_ffmpeg)
    studio.make_proxy("source.mp4", tmp_path, 120.0)
    assert calls == ["proxy.part.mp4", "strip.part.jpg"]
    assert (tmp_path / "proxy.mp4").read_bytes() == b"encoded"
    assert (tmp_path / "strip.jpg").exists()
    assert not list(tmp_path.glob("*.part.*"))


def test_failed_proxy_leaves_no_visible_file(tmp_path, monkeypatch):
    def boom(args, cwd=None):
        Path(args[-1]).write_bytes(b"half")
        raise RuntimeError("ffmpeg died")

    monkeypatch.setattr(studio, "run_ffmpeg", boom)
    with pytest.raises(RuntimeError):
        studio.make_proxy("source.mp4", tmp_path, 60.0)
    assert not (tmp_path / "proxy.mp4").exists()
    assert not list(tmp_path.glob("*.part.*"))


def test_preview_file_prefers_finished_container(tmp_path):
    (tmp_path / "preview.f137.mp4").write_bytes(b"video-only stream")
    (tmp_path / "preview.f251.webm").write_bytes(b"audio-only stream")
    assert probe.preview_file(tmp_path) is None  # intermediates are never served
    (tmp_path / "preview.mp4").write_bytes(b"final")
    assert probe.preview_file(tmp_path).name == "preview.mp4"
    (tmp_path / "preview.part.mp4").write_bytes(b"partial")
    assert probe.preview_file(tmp_path).name == "preview.mp4"


def test_find_video_uses_saved_cookies_and_retries_other_clients(tmp_path, monkeypatch):
    """The preview must not ignore the cookie settings, and must try other clients/formats."""
    attempts = []

    class FakeYDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def download(self, urls):
            attempts.append(self.opts)
            if len(attempts) < 3:
                raise RuntimeError("HTTP Error 403: Forbidden")
            Path(self.opts["outtmpl"].replace("%(ext)s", "mp4")).write_bytes(b"preview")

    import sys
    import types

    fake = types.ModuleType("yt_dlp")
    fake.YoutubeDL = FakeYDL
    monkeypatch.setitem(sys.modules, "yt_dlp", fake)
    cfg = {"cookies": {"from_browser": "chrome", "cookiefile": ""}}
    probe.fetch_preview("pid1", "https://example.com/v", tmp_path, cfg)

    assert len(attempts) == 3
    assert all(o["cookiesfrombrowser"] == ("chrome",) for o in attempts)
    assert len({(o["format"], str(o.get("extractor_args"))) for o in attempts}) == 3  # distinct combos
    assert (tmp_path / "preview.mp4").exists()


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="needs ffmpeg")
def test_corrupt_proxy_is_replaced(tmp_path):
    from marrow.server import App as _App

    src = Path(tempfile.mkdtemp()) / "src.mp4"
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                    "testsrc=size=320x240:rate=10:duration=3", "-f", "lavfi", "-i",
                    "sine=frequency=300:duration=3", "-shortest", "-c:v", "libx264", "-c:a", "aac",
                    str(src)], check=True)
    app = _App(str(tmp_path))
    vid = "vfix"
    wd = app.work / vid
    wd.mkdir(parents=True, exist_ok=True)
    (wd / "proxy.mp4").write_bytes(b"\x00 truncated mp4 without an index")  # an older build's leftover
    app.projects["pfix"] = {"id": "pfix", "name": "t", "source": str(src), "source_kind": "file",
                            "status": "running", "stage": "", "progress": 0, "created": 0,
                            "started": 0, "finished": None, "error": None, "video_id": vid,
                            "settings": {}, "clips": []}
    app._build_proxy("pfix", str(src), str(wd), 3.0)
    from marrow.utils import probe_duration

    assert probe_duration(wd / "proxy.mp4") > 0
    assert (wd / "strip.jpg").exists()
