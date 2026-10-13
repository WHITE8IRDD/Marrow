"""zoompan must change framing, never the source playback speed."""
import shutil
import subprocess

import pytest

from marrow.renderer import build_filter_graph


def _ffmpeg():
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        pytest.skip("ffmpeg is required for timing integration tests")


@pytest.mark.parametrize("rate", [24, 25, 60, "30000/1001"])
@pytest.mark.parametrize("layout", ["stacked", "crop"])
def test_zoom_preserves_source_clock(rate, layout):
    # Flash at one second. A frame-count-only zoom used to move this flash
    # to .8s/.833s/2s for 24/25/60fps sources rendered at 30fps.
    shot = {"panels": [{"w": 160, "h": 160, "x": x, "y": 0} for x in (0, 160)],
            "active": [[0, 2, 0]]}  # only one animated panel also tests framesync
    graph = build_filter_graph(layout, 90, 160, 30, {"enabled": True}, shot=shot)
    result = subprocess.run([
        _ffmpeg(), "-v", "error", "-f", "lavfi", "-i",
        f"color=black:s=320x160:r={rate}:d=2,drawbox=color=white:t=fill:enable='gte(t,1)'",
        "-filter_complex_threads", "1", "-filter_complex", graph,
        "-map", "[v]", "-pix_fmt", "gray", "-f", "rawvideo", "pipe:1",
    ], capture_output=True, check=True, timeout=30)
    size = 90 * 160
    frames = [result.stdout[i:i + size] for i in range(0, len(result.stdout), size)]
    assert 59 <= len(frames) <= 61
    flash = next(i for i, frame in enumerate(frames) if sum(frame) / size > 200)
    assert abs(flash / 30 - 1) <= 1 / 30 + .001
