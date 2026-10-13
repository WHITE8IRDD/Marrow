import logging
import os
import re
import shutil
import subprocess
from pathlib import Path

log = logging.getLogger("marrow")


def ensure_dir(path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def part_path(dst) -> Path:
    """Temp name beside `dst` that keeps the extension (ffmpeg picks the muxer from it)."""
    dst = Path(dst)
    return dst.with_name(f"{dst.stem}.part{dst.suffix}")


def atomic_copy(src, dst) -> None:
    """Copy so that `dst` only appears once it is complete (readers never see a partial file)."""
    dst = Path(dst)
    tmp = part_path(dst)
    try:
        shutil.copyfile(src, tmp)
        os.replace(tmp, dst)
    finally:
        tmp.unlink(missing_ok=True)


def slugify(text: str) -> str:
    slug = re.sub(r"[^\w.\-]+", "_", text).strip("_")
    return slug[:80] or "video"


def format_ass_time(t: float) -> str:
    """Seconds -> ASS timestamp H:MM:SS.CC (rounded, never produces .100)."""
    total_cs = max(0, int(round(t * 100)))
    h, rem = divmod(total_cs, 360000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def require_ffmpeg():
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            raise RuntimeError(
                f"{tool} was not found on PATH. Install FFmpeg "
                "(Windows: `winget install ffmpeg`, macOS: `brew install ffmpeg`, "
                "Linux: your package manager) and open a new terminal."
            )


def run_ffmpeg(args, cwd=None, timeout=1800):
    cmd = ["ffmpeg", "-nostdin", "-y", "-hide_banner", "-loglevel", "error"] + [str(a) for a in args]
    try:
        return subprocess.run(cmd, check=True, capture_output=True, text=True, cwd=cwd,
                              encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"ffmpeg timed out after {timeout}s. Check the source file and encoder.") from e
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffmpeg failed:\n{e.stderr}") from e


def run_ffmpeg_progress(args, total_sec, on_progress, cwd=None, stall_timeout=180):
    """Report encoded media time, drain both pipes and bound stalled encoders.

    Reader threads keep a blocked readline off the worker. A callback exception
    (including cancellation) must terminate/reap the encoder, not orphan it.
    """
    import threading
    import time
    from collections import deque
    from queue import Empty, Queue

    cmd = ["ffmpeg", "-nostdin", "-y", "-hide_banner", "-loglevel", "error",
           "-progress", "pipe:1", "-nostats"] + [str(a) for a in args]
    p = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, encoding="utf-8", errors="replace")
    events, err = Queue(), deque(maxlen=40)

    def read_progress():
        try:
            for line in p.stdout:
                events.put(line)
        finally:
            events.put(None)

    def drain():
        for line in p.stderr:
            err.append(line[-2000:])

    readers = [threading.Thread(target=read_progress, daemon=True),
               threading.Thread(target=drain, daemon=True)]
    for reader in readers:
        reader.start()
    last_advance, media_us, frac = time.monotonic(), -1, 0.0
    try:
        on_progress(0.0)
        while True:
            try:
                line = events.get(timeout=min(1.0, stall_timeout))
            except Empty:
                line = ""
            if line is None:
                break
            if line.startswith("out_time_us="):
                try:
                    us = int(line.strip().split("=", 1)[1])
                except ValueError:
                    us = -1
                if us > media_us:
                    media_us, last_advance = us, time.monotonic()
                    if total_sec > 0:
                        frac = max(0.0, min(0.99, us / 1e6 / total_sec))
            if time.monotonic() - last_advance > stall_timeout:
                raise RuntimeError(f"ffmpeg stalled: no encoded frames/audio progress for "
                                   f"{stall_timeout}s. Check the source and NVIDIA driver, "
                                   "or retry with the CPU encoder.\n" + "".join(err)[-1500:])
            on_progress(frac)
        try:
            code = p.wait(timeout=stall_timeout)
        except subprocess.TimeoutExpired as e:
            raise RuntimeError("ffmpeg stalled while finalizing the output.") from e
        readers[1].join(timeout=2)
        if code != 0:
            raise RuntimeError("ffmpeg failed:\n" + "".join(err)[-1500:])
        on_progress(1.0)
    finally:
        if p.poll() is None:
            p.terminate()
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()
        for reader in readers:
            reader.join(timeout=2)
        p.stdout.close()
        p.stderr.close()


_DURATION_CACHE = {}


def probe_duration(path) -> float:
    """Media duration in seconds, memoised per (file, size, mtime).

    A probe costs ~60 ms of process start-up and one pipeline run asks for the
    same duration several times (source, proxy, audio) - the UI asks again on
    every export. Re-probing an unchanged file is pure overhead, so the result is
    cached until the file changes.
    """
    key = os.fspath(path)
    try:
        st = os.stat(key)
        token = (st.st_size, st.st_mtime_ns)
    except OSError:
        token = None
    if token is not None and _DURATION_CACHE.get(key, (None, None))[0] == token:
        return _DURATION_CACHE[key][1]
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", key],
        check=True, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    duration = float(out.stdout.strip())
    if token is not None:
        _DURATION_CACHE[key] = (token, duration)
    return duration
