"""Caption style data behind the live preview: the Text size key, the payload the page reads, and font heights."""
import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from marrow import server as S
from marrow.caption_styles import BASE, FONTS_DIR, font_height_em, normalize_style_keys, resolve_style
from marrow.captioner import generate_ass
from marrow.models import Word


def test_text_size_key_is_the_renderer_size():
    # the Text size slider used to save font_size, which the renderer never read
    assert S.clean_overrides({"font_size": 90, "uppercase": False}) == {"size": 90, "uppercase": False}
    assert S.clean_overrides({"font_size": 90, "size": 80}) == {"size": 80}
    assert "font_size" not in S.clean_overrides({"font_size": 90})
    assert resolve_style(None, {"font_size": 90}, None)["size"] == 90
    assert resolve_style("hormozi", {"font_size": 90}, None)["size"] == 90      # overrides beat the preset
    assert resolve_style("bold-pop", None, {"font_size": 66})["size"] == 66     # config captions.font_size
    assert resolve_style("hormozi", None, {"font_size": 66})["size"] == 84      # a preset's own size still wins


def test_saved_settings_keep_the_size_under_its_renderer_name():
    settings = S.clean_job_settings({"caption_style": {"font_size": 91}})
    assert settings["caption_style"]["overrides"] == {"size": 91}
    settings = S.clean_job_settings({"caption_style": {"overrides": {"font_size": 88}}})
    assert settings["caption_style"]["overrides"] == {"size": 88}


def test_resolve_style_does_not_change_its_inputs():
    overrides, legacy = {"font_size": 90}, {"font_size": 66}
    resolve_style("clean", overrides, legacy)
    assert overrides == {"font_size": 90} and legacy == {"font_size": 66}
    assert normalize_style_keys({"font_size": 1, "size": None}) == {"size": 1}


def test_text_size_reaches_the_subtitle_file(tmp_path):
    words = [Word(i * 0.4, i * 0.4 + 0.35, t, score=0.5) for i, t in enumerate("make it go viral".split())]
    out = tmp_path / "size.ass"
    generate_ass(words, 0.0, 3.0, out, {"preset": "bold-pop", "overrides": S.clean_overrides({"font_size": 90})})
    style = next(line for line in out.read_text(encoding="utf-8").splitlines() if line.startswith("Style:"))
    assert style.split(",")[2] == "90"        # Fontsize


@pytest.fixture()
def base(tmp_path):
    S.Handler.app = S.App(str(tmp_path))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), S.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()


def test_style_payload_feeds_the_preview(base):
    with urllib.request.urlopen(base + "/api/caption-styles") as r:
        d = json.load(r)
    assert {"base", "presets", "legacy", "margins", "font_height"} <= set(d)
    assert set(d["legacy"]) <= set(BASE)                 # only keys the renderer reads; never font_size
    assert d["legacy"]["size"] == 72                     # config captions.font_size, under its renderer name
    assert d["margins"] == {"shorts": 420, "reels": 460}  # caption_margin_v per platform
    assert d["font_height"]["Arial"] == pytest.approx(1.117, abs=0.001)
    assert all(1.0 < v < 2.5 for v in d["font_height"].values())


def test_font_height_follows_libass(tmp_path):
    # libass sizes Fontsize to the font's height (win ascent + descent), so the preview uses the same rule
    assert font_height_em(FONTS_DIR / "Montserrat-ExtraBold.ttf") == pytest.approx(1.562, abs=0.002)
    assert font_height_em(FONTS_DIR / "Poppins-Bold.ttf") == pytest.approx(1.762, abs=0.002)
