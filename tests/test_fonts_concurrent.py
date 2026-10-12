"""Concurrent font staging: ensure_fonts() is called from every render task
(ThreadPoolExecutor in pipeline.py) sharing one ass dir, so it must be safe
to run concurrently and must not rewrite identical files (Windows WinError 32
when a sibling thread or ffmpeg has the file open)."""
from concurrent.futures import ThreadPoolExecutor

from marrow.caption_styles import FONTS_DIR, ensure_fonts


def _expected():
    return sorted(p.name for p in FONTS_DIR.iterdir() if p.is_file())


def test_ensure_fonts_concurrent_same_dest(tmp_path):
    dest = tmp_path / "ass"
    dest.mkdir()
    with ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(lambda _: ensure_fonts(dest), range(32)))
    fonts = dest / "fonts"
    assert sorted(p.name for p in fonts.iterdir() if p.is_file()) == _expected()
    for src in FONTS_DIR.iterdir():
        if src.is_file():
            assert (fonts / src.name).read_bytes() == src.read_bytes()


def test_ensure_fonts_idempotent_no_rewrite(tmp_path):
    dest = tmp_path / "ass"
    dest.mkdir()
    ensure_fonts(dest)
    fonts = dest / "fonts"
    before = {p.name: p.stat().st_mtime_ns for p in fonts.iterdir() if p.is_file()}
    assert before
    ensure_fonts(dest)
    after = {p.name: p.stat().st_mtime_ns for p in fonts.iterdir() if p.is_file()}
    assert after == before
