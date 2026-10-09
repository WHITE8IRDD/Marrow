"""The web UI's JavaScript/CSS are served as static files with the right MIME types."""
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from marrow import server as S


@pytest.fixture()
def base(tmp_path):
    S.Handler.app = S.App(str(tmp_path))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), S.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()


def test_app_assets_are_served_with_module_safe_types(base):
    with urllib.request.urlopen(base + "/static/app.js") as r:
        assert r.status == 200
        assert r.headers["Content-Type"].startswith("text/javascript")
        content = r.read()
        assert b"function viewHome" in content
        assert b"function updateHomePreview" in content
        assert b"function renderLiveCaption" in content
        assert b"function openPreviewModal" in content
        assert b"homePrevBg" in content
        assert b"prev-controls" in content
    with urllib.request.urlopen(base + "/static/app.css") as r:
        assert r.headers["Content-Type"].startswith("text/css")
        css_content = r.read()
        assert b".prev-bg" in css_content
        assert b".layout-blur_fit" in css_content
        assert b".prev-modal-wrap" in css_content
        assert b"prevSlowZoom" in css_content


def test_caption_styles_api(base):
    import json
    with urllib.request.urlopen(base + "/api/caption-styles") as r:
        assert r.status == 200
        data = json.loads(r.read().decode("utf-8"))
        assert "base" in data
        assert "presets" in data
        assert "bold-pop" in data["presets"]
        assert "hormozi" in data["presets"]
        assert "beast" in data["presets"]
        assert "clean" in data["presets"]
        assert "pill" in data["presets"]
        assert "neon" in data["presets"]
        assert "box" in data["presets"]
        assert "arabic" in data["presets"]


def test_static_route_refuses_other_files(base):
    for path in ("/static/../server.py", "/static/server.py", "/static/app.exe"):
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(base + path)
        assert e.value.code == 404


def test_index_references_the_split_assets(base):
    with urllib.request.urlopen(base + "/") as r:
        html = r.read().decode("utf-8")
    assert '/static/app.css' in html and '/static/app.js' in html
