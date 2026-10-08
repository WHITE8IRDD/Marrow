from dataclasses import replace

import numpy as np

from .utils import format_ass_time

PUNCT_BREAK = (",", ".", "?", "!", ";", ":", "…")


def hex_to_bgr(color: str) -> str:
    """'#RRGGBB' -> 'BBGGRR' (the byte order ASS uses)."""
    h = color.lstrip("#")
    if len(h) != 6:
        raise ValueError(f"Expected a #RRGGBB color, got {color!r}")
    return (h[4:6] + h[2:4] + h[0:2]).upper()


def ass_escape(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")")


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
                 margin_v=420) -> int:
    """Write an ASS file with one event per word; the spoken word is highlighted and scaled.
    Returns the number of Dialogue events written."""
    clip_words = shift_words(words, clip_start, clip_end)
    lines = group_words(
        clip_words,
        max_words=style.get("max_words_per_line", 4),
        max_chars=style.get("max_chars_per_line", 22),
    )

    text_c = hex_to_bgr(style.get("text_color", "#FFFFFF"))
    hl_c = hex_to_bgr(style.get("highlight_color", "#FFE600"))
    out_c = hex_to_bgr(style.get("outline_color", "#000000"))
    active = int(style.get("active_scale", 110))
    emph = int(style.get("emphasis_scale", 125))
    uppercase = style.get("uppercase", True)
    bold = -1 if style.get("bold", True) else 0

    threshold = 2.0
    if clip_words:
        threshold = float(np.percentile([w.score for w in clip_words], style.get("emphasis_percentile", 85)))

    header = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {res_x}",
        f"PlayResY: {res_y}",
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,{style.get('font', 'Arial')},{style.get('font_size', 72)},"
        f"&H00{text_c},&H00{hl_c},&H00{out_c},&H80000000,{bold},0,0,0,100,100,0,0,1,"
        f"{style.get('outline', 4)},{style.get('shadow', 2)},2,60,60,{int(margin_v)},1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    events = []
    for li, line in enumerate(lines):
        limit = lines[li + 1][0].start if li + 1 < len(lines) else float("inf")
        for k, w in enumerate(line):
            start = w.start
            if k + 1 < len(line):
                end = min(line[k + 1].start, w.end + 0.35)
            else:
                end = w.end + 0.1
            end = max(min(end, limit), start + 0.05)

            parts = []
            for i, ww in enumerate(line):
                txt = ass_escape(ww.text.upper() if uppercase else ww.text)
                if i == k:
                    scale = emph if ww.score >= threshold else active
                    parts.append(
                        f"{{\\1c&H{hl_c}&\\fscx{scale}\\fscy{scale}}}{txt}"
                        f"{{\\1c&H{text_c}&\\fscx100\\fscy100}}"
                    )
                else:
                    parts.append(txt)
            events.append(
                f"Dialogue: 0,{format_ass_time(start)},{format_ass_time(end)},Default,,0,0,0,,"
                + " ".join(parts)
            )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(header + events) + "\n")
    return len(events)
