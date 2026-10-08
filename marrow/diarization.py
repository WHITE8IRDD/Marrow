"""Optional speaker diarization. Requires: pip install -e ".[diarization]" and a HF token."""

MODEL = "pyannote/speaker-diarization-3.1"


def diarize(audio_path, hf_token):
    from pyannote.audio import Pipeline  # lazy: heavy optional dependency

    try:
        pipeline = Pipeline.from_pretrained(MODEL, token=hf_token)
    except TypeError:  # older pyannote releases
        pipeline = Pipeline.from_pretrained(MODEL, use_auth_token=hf_token)
    result = pipeline(str(audio_path))
    annotation = getattr(result, "speaker_diarization", result)  # pyannote 4 wraps the output
    return [
        {"start": turn.start, "end": turn.end, "speaker": speaker}
        for turn, _, speaker in annotation.itertracks(yield_label=True)
    ]


def assign_speakers(sentences, turns):
    for sent in sentences:
        best, best_overlap = None, 0.0
        for t in turns:
            overlap = min(sent.end, t["end"]) - max(sent.start, t["start"])
            if overlap > best_overlap:
                best, best_overlap = t["speaker"], overlap
        sent.speaker = best
    return sentences
