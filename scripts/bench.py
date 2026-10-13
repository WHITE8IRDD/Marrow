"""Micro-benchmarks for the work Marrow repeats most often.

Every number this prints is a wall-clock measurement of a real ffmpeg/OpenCV
call on a synthetic clip, so optimisations can be argued with data instead of
intuition. Run it on your own machine (a real 1080p podcast beats the synthetic
testsrc source):

    python scripts/bench.py            # all benchmarks
    python scripts/bench.py analysis   # shot cuts + frame sampling
    python scripts/bench.py thumbs     # clip preview tiles
    python scripts/bench.py render     # forced two-up: one pass vs segments
    python scripts/bench.py probe      # ffprobe duration calls

Notes
-----
* The synthetic source is a 60 s 1080p testsrc2 clip with audio; it is built in
  a temp folder and removed afterwards.
* Face *detection* needs the YuNet model (downloaded on first use). When the
  model is missing these timings still cover the two video decodes - which is
  where shot analysis spends most of its time - and report that detection was
  stubbed.
"""
import argparse
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from marrow import layout as L          # noqa: E402
from marrow import renderer as R        # noqa: E402
from marrow import studio               # noqa: E402
from marrow.utils import probe_duration, run_ffmpeg  # noqa: E402


def _say(label, seconds, extra=""):
    print(f"  {label:<46} {seconds * 1000:8.1f} ms  {extra}")


def _best(fn, repeats=3):
    times = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t0)
    return min(times)


def make_source(dirpath, seconds=60, size="1920x1080"):
    src = Path(dirpath) / "bench_src.mp4"
    if src.exists():
        return src
    run_ffmpeg(["-f", "lavfi", "-i", f"testsrc2=s={size}:r=30:d={seconds}",
                "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", src])
    return src


def make_proxy(src, dirpath):
    proxy = Path(dirpath) / "proxy.mp4"
    if not proxy.exists():
        run_ffmpeg(["-i", src, "-vf", "scale=-2:480,fps=24", "-an",
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30", proxy])
    return proxy


class _StubDetector:
    """Stands in for YuNet when the model file is unavailable."""

    def setInputSize(self, size):
        self.size = size

    def detect(self, frame):
        import numpy as np

        h, w = frame.shape[:2]
        return 1, np.asarray([[w * 0.2, h * 0.3, w * 0.12, h * 0.2, 0.9],
                              [w * 0.7, h * 0.3, w * 0.12, h * 0.2, 0.9]], np.float32)


def bench_analysis(src, proxy, seconds=60):
    print("\nShot analysis over a 60 s window (shot cuts + frame sampling + faces)")
    real_detector = L.get_detector()
    detector_missing = real_detector is None
    det = real_detector or _StubDetector()
    print(f"  face detector: {'stub (YuNet model missing)' if detector_missing else 'YuNet'}")

    def full_pass():
        L.detect_shots(src, 0.0, seconds)
        frames = L.sample_frames(src, 0.0, seconds)
        for _t, frame in frames:
            L.detect_faces(frame, det)

    def proxy_pass():
        L.detect_shots(proxy, 0.0, seconds)
        frames = L.sample_frames(proxy, 0.0, seconds)
        for _t, frame in frames:
            L.detect_faces(frame, det)

    cuts = _best(lambda: L.detect_shots(src, 0.0, seconds))
    sample = _best(lambda: L.sample_frames(src, 0.0, seconds))
    sample_proxy = _best(lambda: L.sample_frames(proxy, 0.0, seconds))
    cuts_proxy = _best(lambda: L.detect_shots(proxy, 0.0, seconds))
    _say("shot cuts on 1080p source", cuts)
    _say("shot cuts on 480p proxy", cuts_proxy, f"{cuts / max(cuts_proxy, 1e-9):.1f}x faster")
    _say("2.5 fps frame samples on 1080p", sample)
    _say("2.5 fps frame samples on 480p proxy", sample_proxy,
         f"{sample / max(sample_proxy, 1e-9):.1f}x faster")
    whole_full = _best(full_pass, repeats=1)
    whole_proxy = _best(proxy_pass, repeats=1)
    _say("analysis+detection, full-res source", whole_full)
    _say("analysis+detection, 480p proxy", whole_proxy,
         f"{whole_full / max(whole_proxy, 1e-9):.1f}x faster")


def bench_thumbs(src, proxy, dirpath, clips=5):
    print(f"\nClip preview tiles for {clips} clips (full-res source vs 480p scan proxy)")
    items = [(i + 1, i * 9.0) for i in range(clips)]
    full = _best(lambda: studio.make_clip_thumbs(src, items, Path(dirpath) / "one", scale="270:480"))
    small = _best(lambda: studio.make_clip_thumbs(proxy, items, Path(dirpath) / "two", scale="270:480"))
    _say("5 tiles from the 1080p source", full)
    _say("5 tiles from the 480p proxy", small, f"{full / max(small, 1e-9):.1f}x faster")


def bench_sampling(src, proxy, seconds=20):
    """grab()+retrieve() skips the colour conversion of every frame we drop."""
    import cv2

    def read_all(path, step=0.4):
        cap = cv2.VideoCapture(str(path))
        out, target = [], 0.0
        while target < seconds:
            ok, frame = cap.read()
            if not ok or frame is None:
                break
            t = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
            if t + 0.01 >= target:
                out.append((t, frame))
                target += step
        cap.release()
        return out

    print(f"\nFrame sampling over {seconds} s (2.5 fps)")
    for label, path in (("1080p source", src), ("480p proxy", proxy)):
        old = _best(lambda: read_all(path))
        new = _best(lambda: L.sample_frames(path, 0.0, seconds))
        _say(f"{label}: read()", old)
        _say(f"{label}: grab()+retrieve()", new, f"{old / max(new, 1e-9):.1f}x faster")


def bench_render(src, dirpath, seconds=8):
    print("\nRendering one 8 s two-up clip (per-shot segments vs a single pass)")
    Path(dirpath, "seg").mkdir(exist_ok=True)
    Path(dirpath, "one").mkdir(exist_ok=True)
    cfg = {"platforms": {"shorts": {"res_x": 1080, "res_y": 1920, "max_duration": 180,
                                    "caption_margin_v": 420}},
           "render": {"layout": "crop", "encoder": "libx264", "preset": "veryfast",
                      "crf": 23, "fps": 30, "loudnorm": False},
           "zoom": {"enabled": False}, "captions": {"enabled": False}}
    # Face panels differ per shot -> the renderer must encode every segment and
    # concat them (the "before" path for two-up).
    panels = []
    for i in range(int(seconds // 2)):
        off = 40 * i
        panels.append({"start": i * 2.0, "end": (i + 1) * 2.0, "layout": "stacked",
                       "panels": [{"x": 100 + off, "y": 40, "w": 300, "h": 340},
                                  {"x": 900 + off, "y": 40, "w": 300, "h": 340}]})
    t0 = time.perf_counter()
    studio.render_clip_shots(cfg, src, dirpath, [], 1, 0.0, seconds, ["shorts"],
                             Path(dirpath) / "seg", False, [dict(s) for s in panels])
    segmented = time.perf_counter() - t0
    # Same framing, but both views live inside the frame -> one encode, no concat.
    halves = [{"start": i * 2.0, "end": (i + 1) * 2.0, "layout": "stacked",
               "views": "frame"} for i in range(int(seconds // 2))]
    t0 = time.perf_counter()
    studio.render_clip_files(cfg, src, Path(dirpath), [], 1, 0.0, seconds, ["shorts"],
                             Path(dirpath) / "one", False, [dict(s) for s in halves])
    single = time.perf_counter() - t0
    _say("segment-per-shot render + concat", segmented)
    _say("single-pass stacked render", single,
         f"{segmented / max(single, 1e-9):.1f}x faster")
    print(f"  encoder used: {R.pick_encoder(cfg['render']['encoder'])}")


def bench_probe(src):
    print("\nDuration probing (the pipeline asks for it several times per run)")
    calls = 6
    t0 = time.perf_counter()
    for _ in range(calls):
        probe_duration(src)
    cold = (time.perf_counter() - t0) / calls
    t0 = time.perf_counter()
    for _ in range(calls):
        probe_duration(src)
    warm = (time.perf_counter() - t0) / calls
    _say(f"ffprobe duration, first run (avg/{calls})", cold)
    _say(f"ffprobe duration, repeated calls (avg/{calls})", warm,
         "cached" if warm < cold / 5 else "not cached")
    mid = statistics.median([_best(lambda: probe_duration(src), 1) for _ in range(3)])
    _say("median single call", mid)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("which", nargs="*", default=[],
                    help="benchmarks to run: analysis sampling thumbs render probe "
                         "(default: all)")
    ap.add_argument("--keep", action="store_true", help="keep the synthetic source")
    args = ap.parse_args(argv)
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        print("ffmpeg/ffprobe not found on PATH", file=sys.stderr)
        return 2
    tmp = tempfile.mkdtemp(prefix="marrow_bench_")
    try:
        src = make_source(tmp)
        proxy = make_proxy(src, tmp)
        print(f"source: {src} ({src.stat().st_size / 2**20:.1f} MB)")
        order = {"analysis": lambda: bench_analysis(src, proxy),
                 "sampling": lambda: bench_sampling(src, proxy),
                 "thumbs": lambda: bench_thumbs(src, proxy, tmp),
                 "render": lambda: bench_render(src, tmp),
                 "probe": lambda: bench_probe(src)}
        wanted = args.which or ["analysis", "sampling", "thumbs", "render", "probe"]
        for which in ["analysis", "sampling", "thumbs", "render", "probe"]:
            if which in wanted:
                order[which]()
    finally:
        if not args.keep:
            shutil.rmtree(tmp, ignore_errors=True)
        else:
            print(f"kept {tmp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
