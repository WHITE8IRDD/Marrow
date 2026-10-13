"""Headless-Chromium smoke test: every route renders with zero console errors.

Needs: pip install playwright && python -m playwright install chromium
Skips otherwise. The server under test runs on a temp home (no user data).
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

pw = pytest.importorskip("playwright.sync_api", reason="playwright not installed")

PORT = 18783


def launch_browser(p):
    executable = os.environ.get("MARROW_TEST_CHROMIUM")
    return p.chromium.launch(**({"executable_path": executable,
                                "args": ["--no-sandbox", "--disable-dev-shm-usage", "--no-zygote"]}
                               if executable else {}))


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
        browser = launch_browser(p)
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


def test_scan_pause_survives_polling_and_stage_change(server):
    with pw.sync_playwright() as p:
        browser = launch_browser(p)
        page = browser.new_page()
        page.goto(server)
        page.wait_for_function("typeof Scan !== 'undefined' && state.settings")
        result = page.evaluate("""() => {
          main.innerHTML = '<section id="scan"><video id="scanVideo"></video><button id="scanPlay"></button><span id="scanPill"></span><span id="scanLabel"></span><span id="trs"></span><span id="thr"></span></section>';
          const v = document.querySelector('video'); let plays = 0;
          v.play = () => { plays++; return Promise.resolve(); }; v.pause = () => {};
          Scan.reset(); v.dataset.src = 'test';
          const project = {id:'x', status:'running', stage:'Transcribing', scan:{t:12,dur:120}, clips:[]};
          Scan.update(project, []); const before = plays;
          Scan.toggle(); const time = v.currentTime;
          for (let i=0; i<5; i++) Scan.update({...project, scan:{t:30+i,dur:120}}, []);
          Scan.update({...project, stage:'Rendering clip 1/1', clips:[{rank:1,status:'rendering',start:50,end:60}]}, []);
          const paused = {plays, time:v.currentTime, requested:Scan.isPaused()};
          Scan.toggle(); Scan.update(project, []);
          return {before, paused, time, plays};
        }""")
        browser.close()
    assert result["paused"]["plays"] == result["before"]
    assert result["paused"]["time"] == result["time"]
    assert result["paused"]["requested"]
    assert result["plays"] > result["before"]


@pytest.mark.parametrize("width", [1440, 900, 390, 320])
def test_clip_actions_are_aligned(server, width):
    with pw.sync_playwright() as p:
        browser = launch_browser(p)
        page = browser.new_page(viewport={"width": width, "height": 1000})
        page.goto(server)
        page.wait_for_function("typeof cardEl !== 'undefined' && state.settings")
        dimensions = page.evaluate("""() => {
          main.innerHTML = '<div id="testGrid" style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));max-width:620px;gap:16px"></div>';
          for (let i=0; i<2; i++) document.querySelector('#testGrid').appendChild(cardEl({id:'test'}, {
            rank:i+1, score:.8, title:i?'A longer title that wraps cleanly over two lines':'Short title',
            duration:30, status:'ready', platforms:['shorts'], urls:{shorts:'about:blank'},
            hashtags:i?['longerhashtag','second']:[]
          }, ''));
          return [...document.querySelectorAll('.cactions')].map(el => ({
            box:el.getBoundingClientRect().toJSON(),
            buttons:[...el.querySelectorAll(':scope > button, :scope > details > summary')].map(x=>x.getBoundingClientRect().toJSON())
          }));
        }""")
        browser.close()
    for row in dimensions:
        assert [b["height"] for b in row["buttons"]] == [36, 36, 36]
        assert row["buttons"][1]["y"] == row["buttons"][2]["y"]
        assert row["buttons"][2]["right"] <= row["box"]["right"] + 1
    assert dimensions[0]["buttons"][2]["bottom"] == dimensions[1]["buttons"][2]["bottom"]
