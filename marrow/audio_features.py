import librosa
import numpy as np

HOP = 512


def compute_energy(audio_path, sr=16000):
    """Return (rms_per_frame normalized to the 95th percentile, frames_per_second)."""
    y, _ = librosa.load(str(audio_path), sr=sr, mono=True)
    rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=HOP)[0]
    ref = np.percentile(rms, 95) if len(rms) else 0.0
    if ref > 0:
        rms = np.clip(rms / ref, 0.0, 1.0)
    return rms, sr / HOP


def assign_word_energy(words, rms, fps):
    """Mean energy over each word's own time span (more accurate than a midpoint sample)."""
    for w in words:
        a = int(w.start * fps)
        b = max(a + 1, int(w.end * fps))
        chunk = rms[a:b]
        w.score = float(chunk.mean()) if len(chunk) else 0.0
    return words
