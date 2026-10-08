"""Headless-Chromium smoke test: every route renders with zero console errors.

Needs: pip install playwright && python -m playwright install chromium
Skips otherwise. The server under test runs on a temp home (no user data).
"""
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

pw = pytest.importorskip("playwright.sync_api", reason="playwright not installed")

PORT = 18783


@pytest.fixture(scope="module")
def server():
    home = Path(tempfile.mkdtemp(prefix="marrow_smoke_"))
    proc = subprocess.Popen(
        [sys.executable, "-m", "marrow.server", "--port", str(PORT),
         "--no-browser", "--home", str(home)],
        cwd=Path(__file__).resolve().parents[1],
        stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    deadline = time.time() + 90
    while time.time() < deadline:
        try:
            import urllib.request
            urllib.request.urlopen(f"http://localhost:{PORT}/", timeout=3)
            break
        except Exception:
            time.sleep(1)
    yield f"http://localhost:{PORT}"
    proc.terminate()


@pytest.mark.parametrize("route", ["#/", "#/projects", "#/edits", "#/settings"])
def test_route_renders_without_errors(server, route, tmp_path):
    from playwright.sync_api import sync_playwright

    errors, failed = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("requestfailed", lambda r: failed.append(r.url))
        page.goto(f"{server}/{route}")
        page.wait_for_timeout(2500)
        try:
            main_len = page.eval_on_selector("#main", "el => el.innerHTML.length")
        finally:
            page.screenshot(path=str(tmp_path / f"smoke_{route.strip('#/') or 'home'}.png"))
            browser.close()
    assert not errors, f"JS errors on {route}: {errors}"
    assert not failed, f"failed requests on {route}: {failed}"
    assert main_len > 100, f"empty content area on {route}"
