"""Regression coverage for device selection, bounded work and live progress."""
import subprocess
import sys
from pathlib import Path

import pytest

from marrow import layout, renderer, studio, transcriber, utils
from marrow.config import load_config


@pytest.mark.parametrize("height", [0, 480, 1080, 1440, 2160])
@pytest.mark.parametrize("encoder", ["libx264", "h264_nvenc"])
def test_explicit_export_device_wins_at_every_resolution(monkeypatch, height, encoder):
    monkeypatch.setattr(studio, "run_ffmpeg", lambda *a, **k: pytest.fail("Unexpected hardware probe"))
    assert studio.pick_export_encoder(height, encoder) == encoder


def test_explicit_cuda_does_not_silently_run_cpu(monkeypatch):
    monkeypatch.setattr(transcriber, "cuda_ready", lambda: (False, "cuDNN missing"))
    monkeypatch.setattr(transcriber, "_run", lambda *a: pytest.fail("Must not run on CPU"))
    with pytest.raises(RuntimeError, match="CUDA was selected.*cuDNN missing"):
        transcriber.transcribe("unused.wav", device="cuda", language="en")


@pytest.mark.parametrize("device,expected", [("auto", "cpu"), ("cpu", "cpu"), ("cuda", "cuda")])
def test_transcription_runs_on_selected_device(monkeypatch, device, expected):
    monkeypatch.setattr(transcriber, "cuda_ready", lambda: (device == "cuda", "unavailable"))
    monkeypatch.setattr(transcriber, "vram_total_gb", lambda: 8)
    calls = []
    monkeypatch.setattr(transcriber, "_run", lambda *a: calls.append(a) or ([], "en"))
    transcriber.transcribe("unused.wav", device=device, language="en")
    assert calls[0][1] == expected
    assert calls[0][2] == ("int8" if expected == "cpu" else "int8_float16")


@pytest.mark.parametrize("device", ["cuda", "auto"])
def test_runtime_cuda_failure_only_falls_back_in_auto(monkeypatch, device):
    monkeypatch.setattr(transcriber, "cuda_ready", lambda: (True, ""))
    monkeypatch.setattr(transcriber, "vram_total_gb", lambda: 8)
    devices = []

    def run(name, dev, *args):
        devices.append(dev)
        if dev == "cuda":
            raise RuntimeError("cuBLAS failed")
        return [], "en"

    monkeypatch.setattr(transcriber, "_run", run)
    if device == "cuda":
        with pytest.raises(RuntimeError, match="CPU fallback is disabled"):
            transcriber.transcribe("unused.wav", device=device, language="en")
        assert devices == ["cuda"]
    else:
        transcriber.transcribe("unused.wav", device=device, language="en")
        assert devices == ["cuda", "cpu"]


def test_cuda_oom_reduces_batch_without_changing_device(monkeypatch):
    monkeypatch.setattr(transcriber, "cuda_ready", lambda: (True, ""))
    monkeypatch.setattr(transcriber, "vram_total_gb", lambda: 8)
    batches = []

    def run(name, dev, ct, audio, lang, beam, bs, cb):
        assert dev == "cuda"
        batches.append(bs)
        if bs > 1:
            raise RuntimeError("CUDA out of memory")
        return [], "en"

    monkeypatch.setattr(transcriber, "_run", run)
    transcriber.transcribe("unused.wav", device="cuda", language="en", batch_size=4)
    assert batches == [4, 2, 1]


def test_frame_sampler_stops_when_timestamps_jump_past_window(monkeypatch):
    import cv2

    class Capture:
        grabbed = 0
        released = False

        def isOpened(self):
            return True

        def set(self, *args):
            pass

        def get(self, prop):
            if prop == cv2.CAP_PROP_FPS:
                return 30
            if prop == cv2.CAP_PROP_POS_MSEC:
                return 100_000  # seek lands beyond the requested clip
            return self.grabbed

        def grab(self):
            self.grabbed += 1
            assert self.grabbed < 4, "Decoded past the clip boundary"
            return True

        def read(self):
            self.grabbed += 1
            return True, b"frame"

        def release(self):
            self.released = True

    cap = Capture()
    monkeypatch.setattr(cv2, "VideoCapture", lambda _: cap)
    assert layout.sample_frames("unused.mp4", 2, 3) == []
    assert cap.released
    assert cap.grabbed <= 2


@pytest.mark.parametrize("uniform", [False, True])
def test_multiplatform_segment_progress_is_monotonic(monkeypatch, tmp_path, uniform):
    cfg = load_config("config.yaml")
    out = tmp_path / "out"
    out.mkdir()
    progress = []

    def render(src, start, end, ass, dst, cfg, plat, on_progress=None, **kw):
        for f in (0, .5, 1):
            on_progress(f)
        Path(dst).write_bytes(b"video")

    monkeypatch.setattr(renderer, "render_clip", render)
    monkeypatch.setattr(studio, "run_ffmpeg", lambda args: Path(args[-1]).write_bytes(b"video"))
    shots = [{"start": 0, "end": 2, "layout": "stacked", "views": "frame"},
             {"start": 2, "end": 10, "layout": "stacked" if uniform else "crop", "views": "frame"}]
    result = studio.render_clip_shots(cfg, "unused", tmp_path, [], 1, 0, 10,
                                     ["shorts", "reels"], out, False, shots, progress.append)
    assert len(result) == 2
    assert progress == sorted(progress)
    assert progress[0] == 0 and progress[-1] == 1
    assert .5 in progress  # first platform completes half the job


def fake_encoder(monkeypatch, script):
    """Real child processes exercise pipe blocking and OS-level cleanup."""
    popen = subprocess.Popen
    children = []

    def launch(*args, **kwargs):
        child = popen([sys.executable, "-u", "-c", script], **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr(utils.subprocess, "Popen", launch)
    return children


def test_stalled_encoder_is_terminated_and_reaped(monkeypatch):
    children = fake_encoder(monkeypatch, "import time; time.sleep(60)")
    with pytest.raises(RuntimeError, match="ffmpeg stalled"):
        utils.run_ffmpeg_progress([], 10, lambda f: None, stall_timeout=.1)
    assert children[0].poll() is not None


def test_progress_callback_failure_stops_encoder(monkeypatch):
    children = fake_encoder(monkeypatch, "import time; print('out_time_us=1000000'); time.sleep(60)")

    def cancel(frac):
        raise ValueError("cancelled")

    with pytest.raises(ValueError, match="cancelled"):
        utils.run_ffmpeg_progress([], 10, cancel)
    assert children[0].poll() is not None


def test_encoder_failure_keeps_stderr(monkeypatch):
    fake_encoder(monkeypatch, "import sys; print('NVENC driver error', file=sys.stderr); sys.exit(1)")
    with pytest.raises(RuntimeError, match="NVENC driver error"):
        utils.run_ffmpeg_progress([], 10, lambda f: None)


def test_encoder_progress_only_completes_on_success(monkeypatch):
    fake_encoder(monkeypatch, "print('out_time_us=5000000'); print('out_time_us=10000000')")
    seen = []
    utils.run_ffmpeg_progress([], 10, seen.append)
    assert seen == sorted(seen)
    assert seen[0] == 0 and seen[-1] == 1
    assert all(f < 1 for f in seen[:-1])


@pytest.mark.parametrize("device", ["cuda", "cpu"])
def test_gpu_model_cache_releases_vram_before_next_stage(monkeypatch, device):
    cache = {"key": ("small", device, "int8"), "model": object(), "pipe": object()}
    monkeypatch.setattr(transcriber, "_CACHE", cache)
    transcriber.release_gpu_model()
    if device == "cuda":
        assert cache == {"key": None, "model": None, "pipe": None}
    else:
        assert cache["model"] is not None


def test_pipeline_failed_ai_batch_does_not_retry_each_window(monkeypatch, tmp_path):
    import json
    from types import SimpleNamespace
    import numpy as np
    from marrow import pipeline
    from marrow.models import Candidate, Sentence, Word

    work = tmp_path / "work"
    work.mkdir()
    media = work / "source.mp4"
    media.write_bytes(b"test")
    (work / "audio.wav").write_bytes(b"cached")
    (work / "words.json").write_text(json.dumps({"model": "small", "words": [[0, 1, "hello"]]}))
    src = SimpleNamespace(path=media, workdir=work, video_id="test", title="Test")
    cfg = load_config("config.yaml")
    cfg["whisper"]["model"] = "small"
    cfg["render"]["encoder"] = "libx264"
    cfg["captions"]["enabled"] = False
    cfg["llm"]["enabled"] = True
    cfg["clip"]["target_count"] = 1
    cfg["cache_dir"] = str(work)
    candidates = [Candidate(i * 30, i * 30 + 25,
                            [Sentence(i * 30, i * 30 + 25, "A useful moment", [Word(0, 1, "hello")])],
                            heuristic=.8) for i in range(8)]
    calls, events = [], []

    class Scorer:
        def __init__(self, *args, **kwargs):
            assert kwargs["retries"] == 0

        def available(self):
            return True

        def batch_score(self, texts, lang):
            calls.append(texts)
            return [None] * len(texts)

        def score(self, *args):
            pytest.fail("Per-window retries would stall the pipeline")

    monkeypatch.setattr(pipeline, "OllamaScorer", Scorer)
    monkeypatch.setattr(pipeline, "require_ffmpeg", lambda: None)
    monkeypatch.setattr(pipeline, "resolve_source", lambda *a: src)
    monkeypatch.setattr(pipeline, "_find_source", lambda *a: (media, False))
    monkeypatch.setattr(pipeline, "probe_duration", lambda *a: 300)
    monkeypatch.setattr(pipeline, "compute_energy", lambda *a: (np.ones(300), 1))
    monkeypatch.setattr(pipeline, "generate_candidates", lambda *a: candidates)
    monkeypatch.setattr(pipeline, "score_candidates", lambda cs: cs)
    monkeypatch.setattr(pipeline, "shortlist", lambda cs, k: cs)
    monkeypatch.setattr(layout, "analyze", lambda *a, **kw: [])
    monkeypatch.setattr(studio, "make_clip_thumbs", lambda *a, **kw: None)

    def render(src, start, end, ass, dst, cfg, plat, on_progress=None):
        for f in (0, .5, 1):
            on_progress(f)
        Path(dst).write_bytes(b"result")

    monkeypatch.setattr(pipeline, "render_clip", render)
    result = pipeline.run_pipeline(media, config=cfg, output_dir=tmp_path / "out",
                                   progress=lambda stage, frac, **kw: events.append((stage, frac)))
    assert len(calls) == 1 and len(calls[0]) == 4
    assert len(result) == 1
    assert any("using heuristic scores" in stage for stage, _ in events)
    assert any("Scanning layout" in stage for stage, _ in events)
    assert any("Generating captions" in stage for stage, _ in events)
    assert events[-1] == ("Done", 1.0)
