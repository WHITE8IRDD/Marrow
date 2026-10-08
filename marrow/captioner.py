import re
from dataclasses import replace

import numpy as np

from .caption_styles import resolve_style
from .utils import format_ass_time

PUNCT_BREAK = (",", ".", "?", "!", ";", ":", "…", "،", "؛", "؟")

_AR = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]")
_NORM = lambda t: re.sub(r"[\W_]+", "", t.lower())


def hex_to_bgr(color: str) -> str:
    """'#RRGGBB' -> 'BBGGRR' (the byte order ASS uses)."""
    h = color.lstrip("#")
    if len(h) != 6:
        raise ValueError(f"Expected a #RRGGBB color, got {color!r}")
    return (h[4:6] + h[2:4] + h[0:2]).upper()


def ass_escape(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")")


def is_rtl(words):
    txt = "".join(w.text for w in words)
    return bool(txt) and len(_AR.findall(txt)) > len(txt) / 2


def _alpha(opacity_pct):                      # ASS alpha: 00 opaque .. FF transparent
    return f"{int(round(255 * (1 - opacity_pct / 100))):02X}"


def _on(st, scale):
    start = int(scale * 0.8) if st["anim"] == "pop" else scale
    t = f"\\fscx{start}\\fscy{start}"
    if st["highlight_mode"] == "pill":
        t += (f"\\1c&H{hex_to_bgr(st['pill_text'])}&\\3c&H{hex_to_bgr(st['pill_color'])}&"
              f"\\bord{st['pill_pad']}\\shad0")
    else:
        t += f"\\1c&H{hex_to_bgr(st['highlight_color'])}&"
    if st["anim"] == "pop":
        t += f"\\t(0,110,\\fscx{scale}\\fscy{scale})"
    return t


def _off(st):
    return (f"\\1c&H{hex_to_bgr(st['text_color'])}&\\3c&H{hex_to_bgr(st['outline_color'])}&"
            f"\\bord{st['outline']}\\shad{st['shadow']}\\fscx100\\fscy100")


def clean_words(words):
    """Merge/drop duplicate or overlapping words (batched transcription can repeat
    words at chunk boundaries). Returns a new sorted list."""
    out = []
    for w in sorted(words, key=lambda x: (x.start, x.end)):
        if out:
            p = out[-1]
            if _NORM(w.text) == _NORM(p.text) and w.start < p.end + 0.05:      # same word twice -> merge
                out[-1] = replace(p, end=max(p.end, w.end))
                continue
            if w.start < p.end:                                                # overlap -> trim previous
                out[-1] = replace(p, end=max(p.start + 0.02, w.start))
        out.append(w)
    return out


def _finalize(raw):
    """Safety net: sort by start, drop fully-duplicate overlaps, clamp the rest."""
    raw = sorted(raw, key=lambda e: (e[0], e[1]))
    out = []
    for s, e, body in raw:
        if out and s < out[-1][1] - 1e-9:
            ps, pe, pb = out[-1]
            if body == pb and e <= pe + 1e-9:
                continue
            out[-1] = (ps, max(ps + 0.02, min(pe, s)), pb)
        out.append((s, e, body))
    return [(s, e, b) for s, e, b in out if e > s + 1e-9]


def shift_words(words, clip_start, clip_end):
    """Return COPIES of the words inside the clip, with times relative to clip start."""
    dur = clip_end - clip_start
    out = []
    for w in words:
        if w.end <= clip_start or w.start >= clip_end:
            continue
        out.append(replace(w, start=max(0.0, w.start - clip_start), end=min(dur, w.end - clip_start)))
    return out


def group_words(words, max_words=4, max_chars=22, gap=0.6):
    lines, cur, chars = [], [], 0
    for w in words:
        extra = len(w.text) + (1 if cur else 0)
        if cur and (len(cur) >= max_words or chars + extra > max_chars or w.start - cur[-1].end > gap):
            lines.append(cur)
            cur, chars = [], 0
            extra = len(w.text)
        cur.append(w)
        chars += extra
        if w.text.endswith(PUNCT_BREAK) and len(cur) >= 2:
            lines.append(cur)
            cur, chars = [], 0
    if cur:
        lines.append(cur)
    return lines


def generate_ass(words, clip_start, clip_end, output_path, style, res_x=1080, res_y=1920,
                 margin_v=420, preset=None) -> int:
    st = resolve_style(preset or style.get("preset"), style.get("overrides"), style)
    clip_words = clean_words(shift_words(words, clip_start, clip_end))
    rtl = is_rtl(clip_words)
    lines = group_words(clip_words, st["max_words_per_line"], st["max_chars_per_line"])

    font = st["font_ar"] if rtl else st["font"]
    uppercase = st["uppercase"] and not rtl
    spacing = 0                                              # letter spacing breaks Arabic joining
    bold = -1 if st["bold"] else 0
    align, mv = {"lower": (2, int(margin_v)), "center": (5, 0), "top": (8, 260)}[st["position"]]
    text_c, out_c = hex_to_bgr(st["text_color"]), hex_to_bgr(st["outline_color"])
    if st["box"]:
        border_style, outline_col = 3, f"&H{_alpha(st['box_opacity'])}{hex_to_bgr(st['box_color'])}"
    else:
        border_style, outline_col = 1, f"&H00{out_c}"
    active, emph = int(st["active_scale"]), int(st["emphasis_scale"])

    threshold = 2.0
    if clip_words:
        threshold = float(np.percentile([w.score for w in clip_words], 85))

    header = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {res_x}", f"PlayResY: {res_y}",
        "WrapStyle: 0", "ScaledBorderAndShadow: yes", "", "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,{font},{st['size']},&H00{text_c},&H00{text_c},{outline_col},&H80000000,"
        f"{bold},{-1 if st['italic'] else 0},0,0,100,100,{spacing},0,{border_style},{st['outline']},"
        f"{st['shadow']},{align},60,60,{mv},1",
        "", "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    blur = f"{{\\blur{st['blur']}}}" if st["blur"] else ""
    raw = []

    if st["display"] == "word":
        palette = [hex_to_bgr(c) for c in (st.get("word_colors") or [st["highlight_color"]])]
        for k, w in enumerate(clip_words):
            nxt = clip_words[k + 1].start if k + 1 < len(clip_words) else float("inf")
            end = min(max(w.end + 0.10, w.start + 0.20), nxt)      # hold a little, NEVER overlap the next word
            end = max(end, w.start + 0.05)
            base = w.text.strip(".,!?;:…،؛؟") if st.get("strip_punct", True) else w.text
            txt = ass_escape(base.upper() if uppercase else base)
            col = palette[k % len(palette)]
            tag = f"\\1c&H{col}&\\fscx70\\fscy70\\t(0,90,\\fscx108\\fscy108)\\t(90,160,\\fscx100\\fscy100)"
            raw.append((w.start, end, "{" + tag + "}" + txt))
    else:
        lines = group_words(clip_words, st["max_words_per_line"], st["max_chars_per_line"])
        for li, line in enumerate(lines):
            limit = lines[li + 1][0].start if li + 1 < len(lines) else float("inf")
            for k, w in enumerate(line):
                end = min(line[k + 1].start, w.end + 0.35) if k + 1 < len(line) else w.end + 0.1
                end = max(min(end, limit), w.start + 0.05)
                parts = []
                for i, ww in enumerate(line):
                    txt = ass_escape(ww.text.upper() if uppercase else ww.text)
                    if i == k and st["highlight_mode"] != "none":
                        sc = emph if ww.score >= threshold else active
                        parts.append("{" + _on(st, sc) + "}" + txt + "{" + _off(st) + "}")
                    else:
                        parts.append(txt)
                raw.append((w.start, end, blur + " ".join(parts)))  # logical order; libass does the RTL reorder

    events = [f"Dialogue: 0,{format_ass_time(s)},{format_ass_time(e)},Default,,0,0,0,,{body}"
              for s, e, body in _finalize(raw)]
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(header + events) + "\n")
    return len(events)
