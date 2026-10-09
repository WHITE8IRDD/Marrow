"""Headless-Chromium check of the live caption preview on Home.

Every caption control, the framing buttons and the enlarged view must change the phone at once, with no
Generate click and no server round trip. Needs: pip install playwright && python -m playwright install chromium.
Skips when playwright is not installed. The server under test runs on a temp home (no user data).
"""
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

PORT = 18784
ROOT = Path(__file__).resolve().parents[1]
# a 16:9 picture, so crop (cover) and blur fit (contain) give different scales
SVG_WIDE = ('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="900">'
            '<rect width="1600" height="900" fill="%23c33"/><rect x="600" width="400" height="900" fill="%23fc0"/></svg>')
SET = """([sel, value]) => {                   // set a control the way the user does, then tell the page
  const el = document.querySelector(sel);
  if (typeof value === 'boolean') el.checked = value; else el.value = value;
  el.dispatchEvent(new Event('input', { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
}"""


@pytest.fixture(scope="module")
def server():
    home = Path(tempfile.mkdtemp(prefix="marrow_preview_"))
    proc = subprocess.Popen(
        [sys.executable, "-m", "marrow.server", "--port", str(PORT), "--no-browser", "--home", str(home)],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    deadline = time.time() + 90
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"http://localhost:{PORT}/", timeout=3)
            break
        except Exception:
            time.sleep(1)
    yield f"http://localhost:{PORT}"
    proc.terminate()


def _px(page, selector, prop):
    return float(page.eval_on_selector(selector, f"el => getComputedStyle(el).{prop}").replace("px", ""))


def _scale(page, selector):
    return page.eval_on_selector(selector, "el => new DOMMatrix(getComputedStyle(el).transform).a")


def test_home_phone_follows_every_control(server):
    from playwright.sync_api import sync_playwright

    errors = []
    cap = "#homePhone .pv-cap"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.goto(f"{server}/#/")
            page.wait_for_selector(cap)
            page.evaluate("document.querySelector('#styleCard details.cust').open = true")
            page.wait_for_timeout(150)

            # captions show before any video is found
            assert "Find a video for real frames" in page.inner_text("#homePhone .pv-note")
            assert page.inner_text(cap).strip()

            # Line / Word
            page.click('#styleCard [data-ov="display"] button[data-v="word"]')
            page.wait_for_timeout(120)
            assert page.locator("#homePhone .pv-solo").count() == 1
            page.click('#styleCard [data-ov="display"] button[data-v="line"]')
            page.wait_for_timeout(120)
            assert page.locator("#homePhone .pv-solo").count() == 0

            # outline
            before = _px(page, cap, "webkitTextStrokeWidth")
            page.click('#styleCard [data-ov="outline"] button[data-v="8"]')
            page.wait_for_timeout(120)
            assert _px(page, cap, "webkitTextStrokeWidth") > before

            # uppercase, text colour, highlight colour, position
            page.evaluate(SET, ['#styleCard input[data-ov="uppercase"]', False])
            page.wait_for_timeout(120)
            text = page.inner_text(cap)
            assert text == text.lower() and text.strip()
            page.evaluate(SET, ['#styleCard input[data-ov="text_color"]', "#ff0000"])
            page.wait_for_timeout(120)
            assert page.eval_on_selector(cap, "el => getComputedStyle(el).color") == "rgb(255, 0, 0)"
            page.evaluate(SET, ['#styleCard input[data-ov="highlight_color"]', "#00ffff"])
            page.wait_for_timeout(120)
            assert page.eval_on_selector("#homePhone .pv-w.pv-on", "el => getComputedStyle(el).color") == "rgb(0, 255, 255)"
            page.click('#styleCard [data-ov="position"] button[data-v="center"]')
            page.wait_for_timeout(120)
            assert page.eval_on_selector(cap, "el => el.style.top") == "50%"

            # font: the face switches once it has loaded
            page.evaluate(SET, ['#styleCard select[data-ov="font"]', "Anton"])
            page.wait_for_timeout(600)
            assert "Anton" in page.eval_on_selector(cap, "el => getComputedStyle(el).fontFamily")

            # a preset keeps the controls the user touched and takes the rest from itself
            page.click('.scard[data-k="hormozi"]')
            page.wait_for_timeout(120)
            overrides = page.evaluate("readStyleRoot(document.getElementById('styleCard')).overrides")
            assert overrides.get("uppercase") is False and overrides.get("highlight_color") == "#00ffff"
            assert "size" not in overrides                     # untouched: Hormozi's own size (84) applies
            width = page.eval_on_selector("#homePhone", "el => el.clientWidth")
            assert _px(page, cap, "fontSize") == pytest.approx(84 / 1.7334 * width / 1080, abs=0.05)

            # Clean, untouched: saves nothing, so its own look (no pop animation) is what Generate gets
            page.click('[data-act="cust-reset"]')
            page.click('.scard[data-k="clean"]')
            page.wait_for_timeout(120)
            assert page.evaluate("readHomeOpts().caption_style") == {"preset": "clean", "overrides": {}}
            assert page.locator("#homePhone .pv-pop").count() == 0

            # captions off, then on again
            page.evaluate(SET, ['#optbox input[data-opt="captions"]', False])
            page.wait_for_timeout(120)
            assert "Captions are off" in page.inner_text("#homePhone .pv-note")
            assert page.eval_on_selector(cap, "el => el.hidden") is True
            page.evaluate(SET, ['#optbox input[data-opt="captions"]', True])
            page.wait_for_timeout(120)
            assert page.eval_on_selector(cap, "el => el.hidden") is False

            # English / Arabic
            page.click('.sampleLang button[data-l="ar"]')
            page.wait_for_timeout(120)
            assert page.get_attribute(cap, "dir") == "rtl"
            page.click('.sampleLang button[data-l="en"]')
            page.wait_for_timeout(120)

            # framing with a real picture: crop fills the frame, blur fit shows it whole over a blurred copy
            page.evaluate("src => pvSetMedia('image', src)", SVG_WIDE)
            page.wait_for_timeout(400)
            img = "#homePhone img.pv-fg"
            assert page.locator(img).is_visible()
            assert _scale(page, img) == pytest.approx(16 / 9 / (9 / 16), abs=0.05)     # 3.16: cover
            page.click('#optbox .seg[data-opt="layout"] button[data-v="blur_fit"]')
            page.wait_for_timeout(500)
            assert _scale(page, img) == pytest.approx(1.0, abs=0.01)                    # contain
            assert page.eval_on_selector("#homePhone .pv-bg", "el => getComputedStyle(el).opacity") == "1"
            page.click('#optbox .seg[data-opt="layout"] button[data-v="crop"]')
            page.wait_for_timeout(500)
            assert _scale(page, img) == pytest.approx(16 / 9 / (9 / 16), abs=0.05)

            # enlarged view: same caption, larger; Escape closes it
            page.click("#homePhone .pv-expand")
            page.wait_for_selector(".modal.pv-modal #pvBig .pv-cap")
            assert _px(page, "#pvBig .pv-cap", "fontSize") > _px(page, cap, "fontSize")
            page.keyboard.press("Escape")
            page.wait_for_selector(".modal.pv-modal", state="detached")

            assert errors == [], errors
            # a preview that cannot load says so, and keeps its captions
            page.evaluate("pvSetMedia('video', '/no-such-video.mp4')")
            page.wait_for_function("document.querySelector('#homePhone .pv-note').textContent === 'Preview unavailable'",
                                   timeout=8000)
            assert page.inner_text(cap).strip()
        finally:
            browser.close()
