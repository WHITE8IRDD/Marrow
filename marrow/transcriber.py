"""Fast transcription: GPU-first, batched, language-aware, with live engine reporting."""
import gc
import os
import site
import time
from pathlib import Path

from .models import Word
from .utils import log
from . import hw

FAST_MODELS = {"large-v3-turbo", "distil-large-v3"}
_probe = None


def add_cuda_dll_dirs():
    """Windows: expose pip-installed cuBLAS/cuDNN DLLs to ctranslate2."""
    if os.name != "nt":
        return
    roots = [Path(p) for p in site.getsitepackages() + [site.getusersitepackages()]]
    for root in roots:
        for sub in ("cublas", "cudnn", "cuda_runtime", "cuda_nvrtc"):
            d = root / "nvidia" / sub / "bin"
            if d.is_dir():
                try:
                    os.add_dll_directory(str(d))
                except OSError:
                    pass
                os.environ["PATH"] = str(d) + os.pathsep + os.environ.get("PATH", "")


def cuda_ready():
    """(ok, reason). Really loads a tiny CUDA model once; 'a GPU exists' is not enough."""
    global _probe
    if _probe is not None:
        return _probe
    add_cuda_dll_dirs()
    try:
        import numpy as np
        from faster_whisper import WhisperModel

        m = WhisperModel("tiny", device="cuda", compute_type="int8_float16")
        segs, _ = m.transcribe(np.zeros(16000, dtype="float32"), beam_size=1)
        list(segs)
        del m
        gc.collect()
        _probe = (True, "")
    except Exception as e:  # noqa: BLE001
        _probe = (False, f"{type(e).__name__}: {e}")
    return _probe


def detect_language(audio_path):
    from faster_whisper import WhisperModel
    from faster_whisper.audio import decode_audio

    audio = decode_audio(str(audio_path), sampling_rate=16000)
    n, sec = len(audio), 16000
    clip = audio[n // 3: n // 3 + 30 * sec] if n > 60 * sec else audio[: 30 * sec]
    m = WhisperModel("tiny", device="cpu", compute_type="int8")
    lang, prob, _ = m.detect_language(clip)
    log.info("Detected language %s (%.0f%%)", lang, prob * 100)
    return lang, prob


def pick_model(setting, language, quality="fast", device="cuda"):
    if setting and setting != "auto":
        return setting
    if device == "cpu":
        return "small"
    if language == "en":
        return "distil-large-v3"
    return "large-v3" if quality == "best" else "large-v3-turbo"


def _run(name, dev, ct, audio_path, language, beam, bs, on_progress):
    from faster_whisper import BatchedInferencePipeline, WhisperModel

    model = WhisperModel(name, device=dev, compute_type=ct)
    pipe = BatchedInferencePipeline(model=model)
    t0 = time.time()
    segments, info = pipe.transcribe(
        str(audio_path),
        batch_size=bs,
        language=language,
        beam_size=beam,
        word_timestamps=True,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 300},
    )
    total = max(info.duration, 1.0)
    words = []
    for seg in segments:                       # lazy generator: consume before freeing the model
        for w in seg.words or []:
            text = w.word.strip()
            if text:
                words.append(Word(start=float(w.start), end=float(w.end), text=text))
        if on_progress:
            frac = min(1.0, seg.end / total)
            speed = seg.end / max(time.time() - t0, 0.01)
            line = f"[{seg.start:7.2f}s -> {seg.end:7.2f}s] {seg.text.strip()}"
            on_progress(frac, speed, seg.end, line)
    del pipe, model
    gc.collect()                               # free VRAM before the LLM stage
    return words, info.language


def transcribe(audio_path, model_size="auto", device="auto", compute_type="int8_float16",
               language=None, beam_size=1, batch_size=8, quality="fast", on_progress=None):
    if device in ("auto", "cuda"):
        ok, why = cuda_ready()
    else:
        ok, why = False, "CPU selected in settings"
    dev = "cuda" if ok else "cpu"
    ct = compute_type if ok else "int8"
    fallback = None if ok else why

    if not language:
        language, _ = detect_language(audio_path)
    name = pick_model(model_size, language, quality, dev)
    bs = batch_size if ok else 4

    hw.set_engine("transcribe", device=dev, model=name, compute=ct, language=language,
                  batch=bs, fallback=fallback)
    while True:
        try:
            return _run(name, dev, ct, audio_path, language, beam_size, bs, on_progress)
        except RuntimeError as e:
            if "out of memory" in str(e).lower() and bs > 1:
                bs //= 2
                gc.collect()
                log.warning("GPU OOM, retrying with batch_size=%d", bs)
                hw.set_engine("transcribe", device=dev, model=name, compute=ct,
                              language=language, batch=bs, fallback=fallback)
                continue
            if dev == "cuda":
                log.warning("GPU transcription failed (%s). Falling back to CPU.", e)
                dev, ct, bs, fallback = "cpu", "int8", 4, f"{type(e).__name__}: {e}"
                name = pick_model(model_size, language, quality, "cpu")
                hw.set_engine("transcribe", device=dev, model=name, compute=ct,
                              language=language, batch=bs, fallback=fallback)
                continue
            raise
