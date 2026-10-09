import struct
from functools import lru_cache
from pathlib import Path

FONTS_DIR = Path(__file__).parent / "assets" / "fonts"

BASE = dict(
    font="Arial", font_ar="Arial", size=72, bold=True, italic=False, uppercase=True,
    text_color="#FFFFFF", highlight_color="#FFE600",
    outline_color="#000000", outline=4, shadow=2, blur=0,
    box=False, box_color="#000000", box_opacity=60,           # whole-line box (BorderStyle 3)
    highlight_mode="color",                                    # color | pill
    pill_color="#FFFFFF", pill_text="#000000", pill_pad=10,
    active_scale=110, emphasis_scale=125, anim="pop",          # pop | none
    display="line",                                          # line | word (one word at a time)
    word_colors=None,                                        # cycled per word in word mode (None = highlight_color)
    strip_punct=True,
    min_gap=0.22,                                            # min on-screen time per caption event (pace)
    position="lower",                                          # lower | center | top
    max_words_per_line=4, max_chars_per_line=22,
)

PRESETS = {
    "bold-pop": dict(label="Bold Pop", font="Montserrat ExtraBold", font_file="Montserrat-ExtraBold.ttf",
                     font_ar="Cairo", font_ar_file="Cairo-Bold.ttf", bold=False, outline=5),
    "hormozi":  dict(label="Hormozi", font="Anton", font_file="Anton-Regular.ttf", bold=False,
                     font_ar="Tajawal", font_ar_file="Tajawal-ExtraBold.ttf",
                     highlight_color="#00F060", size=84, outline=6, max_words_per_line=3,
                     position="center", active_scale=115),
    "beast":    dict(label="Beast", font="Bebas Neue", font_file="BebasNeue-Regular.ttf", bold=False,
                     font_ar="Cairo", font_ar_file="Cairo-Bold.ttf",
                     highlight_color="#FF3B30", size=104, outline=7, max_words_per_line=3,
                     position="center", emphasis_scale=140),
    "clean":    dict(label="Clean", font="Poppins SemiBold", font_file="Poppins-SemiBold.ttf", bold=False,
                     font_ar="Noto Sans Arabic", font_ar_file="NotoSansArabic-Bold.ttf",
                     uppercase=False, highlight_color="#A78BFA", outline=0, shadow=4, size=64, anim="none"),
    "pill":     dict(label="Pill", font="Poppins", font_file="Poppins-Bold.ttf",
                     font_ar="Cairo", font_ar_file="Cairo-Bold.ttf", highlight_mode="pill",
                     pill_color="#FFFFFF", pill_text="#000000", outline=3, uppercase=False),
    "neon":     dict(label="Neon", font="Poppins", font_file="Poppins-Bold.ttf",
                     font_ar="Cairo", font_ar_file="Cairo-Bold.ttf",
                     highlight_color="#22E5FF", outline_color="#0077CC", outline=3, blur=2),
    "box":      dict(label="Box", font="Inter", font_file="Inter-Bold.ttf",
                     font_ar="Noto Sans Arabic", font_ar_file="NotoSansArabic-Bold.ttf",
                     box=True, box_opacity=65, outline=14, shadow=0, uppercase=False,
                     highlight_color="#FFD60A", size=60),
    "arabic":   dict(label="Arabic Bold", font="Cairo", font_file="Cairo-Bold.ttf", font_ar="Cairo",
                     font_ar_file="Cairo-Bold.ttf", uppercase=False, highlight_color="#FFE600", size=76),
    "one-word": dict(label="One Word", display="word", font="Montserrat ExtraBold",
                     font_file="Montserrat-ExtraBold.ttf", bold=False,
                     font_ar="Cairo", font_ar_file="Cairo-Bold.ttf", size=120, position="center",
                     outline=7, uppercase=True, highlight_color="#FFE600",
                     word_colors=["#FFE600", "#FFFFFF", "#00F060"], max_words_per_line=1),
    "one-word-clean": dict(label="One Word Clean", display="word", font="Poppins",
                     font_file="Poppins-Bold.ttf", bold=False,
                     font_ar="Cairo", font_ar_file="Cairo-Bold.ttf", size=104, position="lower",
                     outline=0, shadow=6, uppercase=False, highlight_color="#FFFFFF",
                     word_colors=["#FFFFFF"], max_words_per_line=1),
}


ARIAL_HEIGHT_EM = 1.117      # Arial (and its metric twin Liberation Sans): usWinAscent 1854 + usWinDescent 434, 2048 upm


@lru_cache(maxsize=None)
def font_height_em(path):
    """Height of a font in em: OS/2 usWinAscent + usWinDescent over unitsPerEm.

    libass sizes a subtitle style's Fontsize to this height, not to the em. So Montserrat ExtraBold
    (height 1.56 em) at Fontsize 72 is drawn with an em of about 46 px. The preview uses the same rule."""
    data = Path(path).read_bytes()
    count = struct.unpack_from(">H", data, 4)[0]
    tables = {}
    for i in range(count):
        tag, _, offset, _ = struct.unpack_from(">4sIII", data, 12 + 16 * i)
        tables[tag] = offset
    upm = struct.unpack_from(">H", data, tables[b"head"] + 18)[0]
    win_asc, win_desc = struct.unpack_from(">HH", data, tables[b"OS/2"] + 74)
    return (win_asc + win_desc) / upm


def font_heights():
    """{family: height in em} for every bundled preset font, plus Arial (used for families not bundled)."""
    out = {"Arial": ARIAL_HEIGHT_EM}
    for preset in PRESETS.values():
        for fam, fname in ((preset.get("font"), preset.get("font_file")),
                           (preset.get("font_ar"), preset.get("font_ar_file"))):
            path = FONTS_DIR / fname if fname else None
            if fam and path and path.is_file():
                out.setdefault(fam, round(font_height_em(path), 4))
    return out


# Key names older builds and config files used for the caption size. The renderer reads `size`.
_LEGACY_KEYS = {"font_size": "size"}


def normalize_style_keys(d):
    """Copy of `d` with legacy key names renamed to the names the renderer reads."""
    out = dict(d or {})
    for old, new in _LEGACY_KEYS.items():
        if old in out:
            value = out.pop(old)
            if out.get(new) is None:
                out[new] = value
    return out


def resolve_style(preset=None, overrides=None, legacy=None):
    """BASE < legacy config.captions < preset < user overrides (only known keys)."""
    legacy = normalize_style_keys(legacy)
    overrides = normalize_style_keys(overrides)
    st = dict(BASE)
    st.update({k: v for k, v in legacy.items() if k in BASE})
    st.update({k: v for k, v in PRESETS.get(preset or "", {}).items() if k in BASE})
    st.update({k: v for k, v in overrides.items() if k in BASE})
    return st


def ensure_fonts(dest_dir):
    """Copy bundled fonts next to the .ass file so ffmpeg can use a RELATIVE fontsdir (no C: colon)."""
    import shutil
    if FONTS_DIR.is_dir():
        shutil.copytree(FONTS_DIR, Path(dest_dir) / "fonts", dirs_exist_ok=True)
