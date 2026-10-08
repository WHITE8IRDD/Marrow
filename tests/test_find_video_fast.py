"""Find-video is fast and sticky.

* a progressive mp4/webm is streamed straight from the site, so the preview needs no download
* the same link is never fetched twice (paste, Enter and Find all share one probe)
* Generate works as soon as the title is known, without waiting for the preview
* a preview download is cancelled once the user has generated from it
* the /stream route relays the site's bytes with Range support, so the browser can seek
"""
import http.server
import threading
import time
from pathlib import Path

import pytest

from marrow import probe
from marrow.server import App, Handler, ThreadingHTTPServer

URL = "https://video.example.com/watch?v=abc"


def _fmt(**kw):
    base = {"url": "https://cdn.example.com/x", "protocol": "https", "ext": "mp4",
            "vcodec": "avc1", "acodec": "mp4a", "height": 360}
    base.update(kw)
    return base


def _wait(pid, states, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        pr = probe.get(pid)
        if pr and pr["state"] in states:
            return pr
        time.sleep(0.02)
    raise AssertionError(f"probe {pid} never reached {states}: {probe.get(pid)}")


@pytest.fixture(autouse=True)
def _clean_probes():
    probe.PROBES.clear()
    yield
    probe.PROBES.clear()


# ---- stream selection --------------------------------------------------------------

def test_stream_format_prefers_best_progressive_file_up_to_480p():
    info = {"formats": [
        _fmt(format_id="18", height=360),
        _fmt(format_id="22", height=720),                     # too big for a preview: skipped
        _fmt(format_id="137", height=1080, acodec="none"),   # video only: not playable alone
        _fmt(format_id="140", vcodec="none", acodec="mp4a"),  # audio only
        _fmt(format_id="hls", protocol="m3u8_native", height=480),  # HLS: not a progressive file
        _fmt(format_id="webm", ext="webm", height=480),
    ]}
    pick = probe.stream_format(info)
    # the 480p webm beats the 360p mp4 (best quality at or under 480p)
    assert pick["ext"] == "webm"


def test_unknown_codecs_are_accepted_but_explicit_missing_streams_are_not():
    # yt-dlp reports a plain .mp4 link with unknown codecs (None); "none" means a stream is absent
    plain = {"formats": [_fmt(vcodec=None, acodec=None, height=None, url="plain")]}
    assert probe.stream_format(plain)["url"] == "plain"
    assert probe.stream_format({"formats": [_fmt(acodec="none")]}) is None


def test_stream_format_falls_back_to_smallest_above_480_then_none():
    only_720 = {"formats": [_fmt(height=720, url="u720"), _fmt(height=1080, url="u1080")]}
    assert probe.stream_format(only_720)["url"] == "u720"
    hls_only = {"formats": [_fmt(protocol="m3u8_native")]}
    assert probe.stream_format(hls_only) is None
    assert probe.stream_format({}) is None


def test_stream_format_keeps_the_headers_the_site_asked_for():
    info = {"formats": [_fmt(http_headers={"User-Agent": "UA/1", "Referer": "https://video.example.com/"})]}
    assert probe.stream_format(info)["headers"]["User-Agent"] == "UA/1"


# ---- starting a probe ---------------------------------------------------------------

def _fake_probe(monkeypatch, info):
    monkeypatch.setattr(probe, "probe", lambda url, cfg=None: dict(info))


def test_streamable_video_is_ready_without_downloading(tmp_path, monkeypatch):
    info = {"title": "Talk", "channel": "c", "duration": 90, "thumbnail": None, "live": False,
            "url": URL, "video_id": "abc",
            "stream": {"url": "https://cdn.example.com/x", "headers": {}, "ext": "mp4"}}
    _fake_probe(monkeypatch, info)
    called = []
    monkeypatch.setattr(probe, "fetch_preview", lambda *a, **k: called.append(a))
    pid = probe.start(URL, tmp_path)
    pr = _wait(pid, {"ready", "error"})
    assert pr["state"] == "ready", pr
    assert called == []  # nothing was downloaded
    assert pr["info"]["title"] == "Talk"


def test_a_site_without_a_progressive_file_downloads_the_preview(tmp_path, monkeypatch):
    _fake_probe(monkeypatch, {"title": "Talk", "live": False, "stream": None})
    downloaded = []

    def fake_preview(pid, url, out_dir, cfg=None):
        downloaded.append(pid)
        (Path(out_dir) / "preview.mp4").write_bytes(b"preview")

    monkeypatch.setattr(probe, "fetch_preview", fake_preview)
    monkeypatch.setattr(probe, "_strip_preview", lambda d: None)
    pid = probe.start(URL, tmp_path)
    pr = _wait(pid, {"ready", "error"})
    assert pr["state"] == "ready", pr
    assert downloaded == [pid]
    assert probe.preview_file(Path(pr["dir"])).name == "preview.mp4"
    assert pr["info"].get("stream") is None


def test_same_link_reuses_the_running_probe(tmp_path, monkeypatch):
    calls = []

    def slow_probe(url, cfg=None):
        calls.append(url)
        time.sleep(0.2)
        return {"title": "T", "live": False, "url": URL, "video_id": "x", "stream": None}

    monkeypatch.setattr(probe, "probe", slow_probe)
    monkeypatch.setattr(probe, "fetch_preview", lambda *a, **k: None)
    first = probe.start(URL, tmp_path)
    second = probe.start(URL, tmp_path)  # paste + Enter + Find all land here
    assert first == second
    _wait(first, {"ready", "error"})
    assert probe.start(URL, tmp_path) == first  # still reused once finished
    assert calls == [URL]


def test_a_failed_probe_is_not_reused(tmp_path, monkeypatch):
    monkeypatch.setattr(probe, "probe", lambda url, cfg=None: (_ for _ in ()).throw(RuntimeError("boom")))
    first = probe.start(URL, tmp_path)
    _wait(first, {"error"})
    monkeypatch.setattr(probe, "probe", lambda url, cfg=None: {"title": "T", "live": False, "stream": None})
    monkeypatch.setattr(probe, "fetch_preview", lambda *a, **k: None)
    assert probe.start(URL, tmp_path) != first


def test_thumbnail_does_not_delay_the_preview(tmp_path, monkeypatch):
    _fake_probe(monkeypatch, {"title": "T", "live": False, "thumbnail": "https://img/x.jpg",
                              "stream": {"url": "u", "headers": {}, "ext": "mp4"}})
    release = threading.Event()
    monkeypatch.setattr(probe, "_save_thumb", lambda url, d: release.wait(5))  # a slow image host
    pid = probe.start(URL, tmp_path)
    assert _wait(pid, {"ready", "error"})["state"] == "ready"   # ready while the thumbnail is still loading
    release.set()


# ---- cancel and generate ------------------------------------------------------------

def test_cancel_stops_a_running_preview_download(tmp_path, monkeypatch):
    _fake_probe(monkeypatch, {"title": "T", "live": False, "stream": None})

    class SlowYDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def download(self, urls):
            for _ in range(200):  # yt-dlp would call the hook for every chunk
                self.opts["progress_hooks"][0]({"status": "downloading", "downloaded_bytes": 1,
                                                "total_bytes": 100})
                time.sleep(0.01)

    import sys
    import types
    fake = types.ModuleType("yt_dlp")
    fake.YoutubeDL = SlowYDL
    monkeypatch.setitem(sys.modules, "yt_dlp", fake)
    pid = probe.start(URL, tmp_path)
    _wait(pid, {"preview"})
    probe.cancel(pid)
    assert _wait(pid, {"cancelled", "ready", "error"})["state"] == "cancelled"


def test_generate_is_allowed_while_the_preview_still_loads(tmp_path, monkeypatch):
    app = App(str(tmp_path))
    pdir = tmp_path / "probes" / "a1b2c3d4e5f6"
    pdir.mkdir(parents=True)
    probe.PROBES["a1b2c3d4e5f6"] = {
        "state": "preview", "progress": 0.3, "dir": str(pdir), "error": None, "url": URL,
        "born": time.time(), "info": {"title": "Still loading", "channel": "c", "duration": 60,
                                      "live": False, "url": URL, "video_id": "vid7", "stream": None}}
    from marrow import server as srv
    orig = srv.App.config_for
    srv.App.config_for = lambda self, *a, **k: {"cache_dir": str(tmp_path / "work")}
    try:
        p = app.create_project({"probe_id": "a1b2c3d4e5f6", "settings": {}})
        entry = probe.PROBES["a1b2c3d4e5f6"]
    finally:
        srv.App.config_for = orig
        probe.PROBES.pop("a1b2c3d4e5f6", None)
    assert p["name"] == "Still loading"
    assert entry.get("cancel") is True  # the unneeded preview download is told to stop


def test_generate_refuses_a_probe_that_has_no_title_yet(tmp_path):
    from marrow.server import ApiError
    app = App(str(tmp_path))
    probe.PROBES["ffff00001111"] = {"state": "fetching", "progress": 0, "dir": str(tmp_path),
                                    "error": None, "born": time.time(), "info": None}
    try:
        with pytest.raises(ApiError):
            app.create_project({"probe_id": "ffff00001111", "settings": {}})
    finally:
        probe.PROBES.pop("ffff00001111", None)


# ---- the /stream route -----------------------------------------------------------------

class _Site(http.server.BaseHTTPRequestHandler):
    """A fake video host: serves 1000 bytes and honours Range, like a real CDN."""
    body = bytes(range(256)) * 4
    seen = []

    def log_message(self, *a):
        pass

    def do_GET(self):
        _Site.seen.append(dict(self.headers))
        data, status, extra = self.body, 200, {}
        rng = self.headers.get("Range")
        if rng:
            a, b = rng.split("=", 1)[1].split("-")
            start = int(a)
            end = int(b) if b else len(self.body) - 1
            data = self.body[start:end + 1]
            status = 206
            extra["Content-Range"] = f"bytes {start}-{end}/{len(self.body)}"
        self.send_response(status)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Accept-Ranges", "bytes")
        for k, v in extra.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture
def running_app(tmp_path):
    site = ThreadingHTTPServer(("127.0.0.1", 0), _Site)
    threading.Thread(target=site.serve_forever, daemon=True).start()
    Handler.app = App(str(tmp_path))
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    src = f"http://127.0.0.1:{site.server_address[1]}/video.mp4"
    pid = "c0ffee123456"
    probe.PROBES[pid] = {"state": "ready", "progress": 1.0, "dir": str(tmp_path), "error": None,
                         "url": URL, "born": time.time(),
                         "info": {"title": "T", "url": URL, "video_id": "v", "live": False,
                                  "stream": {"url": src, "headers": {"X-Site": "1"}, "ext": "mp4"}}}
    _Site.seen.clear()
    yield base, pid
    server.shutdown()
    site.shutdown()
    probe.PROBES.pop(pid, None)


def test_probe_payload_points_the_page_at_the_stream(running_app):
    import json
    import urllib.request
    base, pid = running_app
    data = json.loads(urllib.request.urlopen(f"{base}/api/probe/{pid}", timeout=5).read())
    assert data["state"] == "ready"
    assert data["preview"] == f"/api/probe/{pid}/stream"
    assert "stream" not in data["info"]  # the upstream link stays on the server
    assert "url" in data["info"]  # the page-facing info keeps its usual keys


def test_stream_relays_ranges_and_site_headers(running_app):
    import urllib.request
    base, pid = running_app
    req = urllib.request.Request(f"{base}/api/probe/{pid}/stream", headers={"Range": "bytes=4-7"})
    with urllib.request.urlopen(req, timeout=5) as r:
        assert r.status == 206
        assert r.headers["Content-Range"] == "bytes 4-7/1024"
        assert r.read() == _Site.body[4:8]
    sent = _Site.seen[-1]
    assert sent.get("Range") == "bytes=4-7"
    assert sent.get("X-Site") == "1"


def test_stream_404s_until_ready(running_app):
    import urllib.error
    import urllib.request
    base, pid = running_app
    probe.PROBES[pid]["state"] = "found"
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(f"{base}/api/probe/{pid}/stream", timeout=5)
    assert exc.value.code == 404


def test_stream_only_relays_web_links(running_app):
    import urllib.error
    import urllib.request
    base, pid = running_app
    probe.PROBES[pid]["info"]["stream"]["url"] = "file:///etc/passwd"
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(f"{base}/api/probe/{pid}/stream", timeout=5)
    assert exc.value.code == 404


def test_stream_reports_a_dead_source_as_502(running_app):
    import urllib.error
    import urllib.request
    base, pid = running_app
    probe.PROBES[pid]["info"]["stream"]["url"] = "http://127.0.0.1:9/gone.mp4"  # nothing listens here
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(f"{base}/api/probe/{pid}/stream", timeout=10)
    assert exc.value.code == 502
