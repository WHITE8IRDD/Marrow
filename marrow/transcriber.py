import gc

from .models import Word
from .utils import log


def resolve_device(device: str, compute_type: str):
    """Pick a usable (device, compute_type). 'auto' and 'cuda' fall back to CPU if no GPU."""
    if device in ("auto", "cuda"):
        try:
            import ctranslate2

            if ctranslate2.get_cuda_device_count() > 0:
                return "cuda", compute_type
        except Exception:
            pass
        if device == "cuda":
            log.warning("CUDA requested but not available; using CPU.")
        return "cpu", "int8"
    if device == "cpu" and compute_type in ("float16", "int8_float16"):
        compute_type = "int8"
    return device, compute_type


def _run(model_size, device, compute_type, audio_path, language, beam_size):
    from faster_whisper import WhisperModel

    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    segments, info = model.transcribe(
        str(audio_path),
        word_timestamps=True,
        vad_filter=True,
        language=language,
        beam_size=beam_size,
        condition_on_previous_text=False,  # reduces repetition loops on long audio
    )
    words = []
    for seg in segments:  # lazy generator: must be consumed before the model is freed
        for w in seg.words or []:
            text = w.word.strip()
            if text:
                words.append(Word(start=float(w.start), end=float(w.end), text=text))
    language_detected = info.language
    del model
    gc.collect()  # free VRAM before the LLM stage
    return words, language_detected


def transcribe(audio_path, model_size="small", device="auto", compute_type="int8_float16",
               language=None, beam_size=5):
    dev, ctype = resolve_device(device, compute_type)
    try:
        return _run(model_size, dev, ctype, audio_path, language, beam_size)
    except Exception as e:
        if dev == "cuda":
            log.warning("GPU transcription failed (%s). Retrying on CPU with int8.", e)
            return _run(model_size, "cpu", "int8", audio_path, language, beam_size)
        raise
