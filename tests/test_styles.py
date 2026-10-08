from marrow.caption_styles import BASE, PRESETS, resolve_style
from marrow.captioner import generate_ass, is_rtl
from marrow.models import Word
from marrow.transcriber import pick_model


def test_resolve_style_precedence():
    st = resolve_style("hormozi", {"size": 90}, {"size": 72, "text_color": "#000000"})
    assert st["size"] == 90             # overrides win
    assert st["position"] == "center"  # preset applies
    assert st["text_color"] == "#000000"  # legacy applies when preset/overrides lack it
    assert resolve_style("nope", None, None)["size"] == BASE["size"]
    assert "zzz" not in resolve_style(None, {"zzz": 1}, None)
    assert set(PRESETS) >= {"bold-pop", "hormozi", "beast", "clean", "pill", "neon", "box", "arabic"}


def test_is_rtl():
    ar = [Word(0, 0.4, t) for t in "هل تعلم ما هو السر".split()]
    en = [Word(0, 0.4, t) for t in "what is the secret".split()]
    assert is_rtl(ar) and not is_rtl(en) and not is_rtl([])


def _words(text, per_word=0.4):
    return [Word(i * per_word, i * per_word + per_word * 0.9, t, score=0.5)
            for i, t in enumerate(text.split())]


def test_generate_ass_arabic(tmp_path):
    out = tmp_path / "ar.ass"
    n = generate_ass(_words("هل تعلم ما هو السر الكبير"), 0.0, 3.0, out,
                     {"preset": "arabic", "overrides": {}})
    assert n > 0
    text = out.read_text(encoding="utf-8")
    style = next(line for line in text.splitlines() if line.startswith("Style:"))
    parts = style.split(",")
    assert parts[1] == "Cairo"   # font_ar used for RTL
    assert parts[13] == "0"      # Spacing 0 keeps Arabic joining
    assert "السر" in text        # words kept as-is, never uppercased


def test_generate_ass_english_uppercase(tmp_path):
    out = tmp_path / "en.ass"
    n = generate_ass(_words("make it go viral now"), 0.0, 3.0, out,
                     {"preset": "bold-pop", "overrides": {}})
    assert n > 0
    text = out.read_text(encoding="utf-8")
    assert "VIRAL" in text
    assert "Montserrat ExtraBold" in text


def test_pick_model():
    assert pick_model("small", "en") == "small"
    assert pick_model("auto", "en") == "distil-large-v3"
    assert pick_model(None, "ar") == "large-v3-turbo"
    assert pick_model("", "ar", quality="best") == "large-v3"
    assert pick_model("auto", "en", device="cpu") == "small"
