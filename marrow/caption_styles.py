from pathlib import Path

FONTS_DIR = Path(__file__).parent / "assets" / "fonts"

BASE = dict(
    font="Arial", font_ar="Arial", size=72, bold=True, italic=False, uppercase=True,
    text_color="#FFFFFF", highlight_color="#FFE600",
    outline_color="#000000", outline=4, shadow=2, blur=0,
    box=False, box_color="#000000", box_opacity=60,           # whole-line box (BorderStyle 3)
    highlight_mode="color",                                    # color | pill
    pill_color="#7C5CFF", pill_text="#FFFFFF", pill_pad=10,
    active_scale=110, emphasis_scale=125, anim="pop",          # pop | none
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
                     pill_color="#7C5CFF", pill_text="#FFFFFF", outline=3, uppercase=False),
    "neon":     dict(label="Neon", font="Poppins", font_file="Poppins-Bold.ttf",
                     font_ar="Cairo", font_ar_file="Cairo-Bold.ttf",
                     highlight_color="#22E5FF", outline_color="#0077CC", outline=3, blur=2),
    "box":      dict(label="Box", font="Inter", font_file="Inter-Bold.ttf",
                     font_ar="Noto Sans Arabic", font_ar_file="NotoSansArabic-Bold.ttf",
                     box=True, box_opacity=65, outline=14, shadow=0, uppercase=False,
                     highlight_color="#FFD60A", size=60),
    "arabic":   dict(label="Arabic Bold", font="Cairo", font_file="Cairo-Bold.ttf", font_ar="Cairo",
                     font_ar_file="Cairo-Bold.ttf", uppercase=False, highlight_color="#FFE600", size=76),
}


def resolve_style(preset=None, overrides=None, legacy=None):
    """BASE < legacy config.captions < preset < user overrides (only known keys)."""
    st = dict(BASE)
    st.update({k: v for k, v in (legacy or {}).items() if k in BASE})
    st.update({k: v for k, v in PRESETS.get(preset or "", {}).items() if k in BASE})
    st.update({k: v for k, v in (overrides or {}).items() if k in BASE})
    return st


def ensure_fonts(dest_dir):
    """Copy bundled fonts next to the .ass file so ffmpeg can use a RELATIVE fontsdir (no C: colon)."""
    import shutil
    if FONTS_DIR.is_dir():
        shutil.copytree(FONTS_DIR, Path(dest_dir) / "fonts", dirs_exist_ok=True)
