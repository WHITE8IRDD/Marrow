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
        assert b"function viewHome" in r.read()
    with urllib.request.urlopen(base + "/static/app.css") as r:
        assert r.headers["Content-Type"].startswith("text/css")


def test_static_route_refuses_other_files(base):
    for path in ("/static/../server.py", "/static/server.py", "/static/app.exe"):
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(base + path)
        assert e.value.code == 404


def test_index_references_the_split_assets(base):
    with urllib.request.urlopen(base + "/") as r:
        html = r.read().decode("utf-8")
    assert '/static/app.css' in html and '/static/app.js' in html
