import json
from pathlib import Path

from .audio_features import assign_word_energy, compute_energy
from .candidates import build_sentences, generate_candidates, score_candidates, shortlist
from .captioner import generate_ass
from .clip_selector import combine_scores, padded_bounds, select_clips
from .config import load_config
from .downloader import prepare_source
from .highlight_scorer import OllamaScorer, llm_score
from .models import Word
from .renderer import render_clip
from .transcriber import transcribe
from .utils import ensure_dir, log, probe_duration, require_ffmpeg, run_ffmpeg

PLATFORMS = ("shorts", "reels")


def _platforms(platform: str):
    p = platform.lower()
    if p == "both":
        return list(PLATFORMS)
    if p in PLATFORMS:
        return [p]
    raise ValueError("platform must be 'shorts', 'reels' or 'both'")


def _load_words(path: Path, model: str):
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("model") != model:
        return None
    return [Word(s, e, t) for s, e, t in data["words"]]


def _save_words(path: Path, model: str, words):
    path.write_text(
        json.dumps({"model": model, "words": [[w.start, w.end, w.text] for w in words]},
                   ensure_ascii=False),
        encoding="utf-8",
    )


def _fallback_title(text: str) -> str:
    snippet = " ".join(text.split()[:9])
    return snippet.rstrip(",.;:") + ("…" if len(text.split()) > 9 else "")


def run_pipeline(source, output_dir="output", config_path="config.yaml", clip_count=None,
                 clip_duration=None, platform="shorts", layout=None, use_llm=None,
                 force=False, progress=None, config=None):
    """Run the full pipeline. Returns a list of result dicts (also saved as manifest.json)."""

    def emit(stage, frac):
        log.info("[%3d%%] %s", int(frac * 100), stage)
        if progress:
            progress(stage, frac)

    cfg = config or load_config(config_path)
    plats = _platforms(platform)
    clip = cfg["clip"]
    if clip_count:
        clip["target_count"] = int(clip_count)
    if clip_duration:
        clip["min_duration"] = max(10, int(clip_duration) - 10)
        clip["max_duration"] = int(clip_duration) + 10
    if layout:
        cfg["render"]["layout"] = layout
    if use_llm is not None:
        cfg["llm"]["enabled"] = bool(use_llm)

    max_dur = min([clip["max_duration"]] + [cfg["platforms"][p]["max_duration"] for p in plats])
    min_dur = max(5, min(clip["min_duration"], max_dur - 5))

    require_ffmpeg()

    # 1. Download / locate source (cached)
    emit("Preparing source video", 0.02)
    src = prepare_source(source, cfg["cache_dir"])
    duration = probe_duration(src.path)
    if duration < min_dur:
        raise ValueError(f"Video is only {duration:.0f}s; shorter than the minimum clip length ({min_dur}s).")

    # 2. Extract audio
    audio_path = src.workdir / "audio.wav"
    if force or not audio_path.exists():
        emit("Extracting audio", 0.08)
        run_ffmpeg(["-i", src.path, "-vn", "-ac", "1", "-ar", "16000", audio_path])

    # 3. Transcribe (cached)
    wcfg = cfg["whisper"]
    words_path = src.workdir / "words.json"
    words = None if force else _load_words(words_path, wcfg["model"])
    if words is None:
        emit("Transcribing (this is the slow step)", 0.12)
        words, lang = transcribe(audio_path, wcfg["model"], wcfg["device"], wcfg["compute_type"],
                                 wcfg["language"], wcfg["beam_size"])
        _save_words(words_path, wcfg["model"], words)
    if not words:
        raise ValueError("No speech was detected in this video.")

    # 4. Energy per word
    emit("Analyzing audio energy", 0.40)
    rms, fps = compute_energy(audio_path)
    assign_word_energy(words, rms, fps)

    # 5. Sentences, optional diarization, candidates
    sentences = build_sentences(words)
    dcfg = cfg["diarization"]
    if dcfg["enabled"]:
        if not dcfg["hf_token"]:
            log.warning("Diarization enabled but no HF token set; skipping.")
        else:
            from .diarization import assign_speakers, diarize

            emit("Detecting speakers", 0.43)
            assign_speakers(sentences, diarize(audio_path, dcfg["hf_token"]))

    emit("Finding candidate clips", 0.46)
    cands = score_candidates(generate_candidates(sentences, min_dur, max_dur))
    if not cands:
        raise ValueError(f"No clip candidates between {min_dur}s and {max_dur}s. Try a wider duration range.")

    lcfg = cfg["llm"]
    scorer = OllamaScorer(lcfg["model"], lcfg["host"], lcfg["timeout"]) if lcfg["enabled"] else None
    llm_ready = bool(scorer and scorer.available())
    k = lcfg["max_candidates"] if llm_ready else clip["target_count"] * 4
    short = shortlist(cands, k)

    # 6. LLM judgment (cached)
    if llm_ready:
        cache_path = src.workdir / "llm_cache.json"
        cache = {}
        if cache_path.exists() and not force:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        for n, c in enumerate(short, 1):
            key = f"{lcfg['model']}|{c.start:.2f}|{c.end:.2f}"
            parsed = cache.get(key) or scorer.score(c.text)
            if parsed:
                cache[key] = parsed
                c.llm, c.llm_score = parsed, llm_score(parsed)
                c.title, c.reason, c.hashtags = parsed["title"], parsed["reason"], parsed["hashtags"]
            emit(f"Scoring clips with LLM ({n}/{len(short)})", 0.46 + 0.34 * n / len(short))
        cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    else:
        log.warning("LLM scoring unavailable; ranking by audio/heuristics only.")

    combine_scores(short, lcfg["weight"])
    chosen = select_clips(short, clip["target_count"])

    # 7. Captions + render
    out_dir = ensure_dir(Path(output_dir) / src.video_id)
    work_ass = ensure_dir(src.workdir / "ass")
    results = []
    total = max(1, len(chosen) * len(plats))
    done = 0
    for rank, c in enumerate(chosen, 1):
        start, end = padded_bounds(c, clip["pad_start"], clip["pad_end"], duration)
        files = {}
        for plat in plats:
            pcfg = cfg["platforms"][plat]
            ass_path = None
            if cfg["captions"]["enabled"]:
                ass_path = work_ass / f"clip_{rank:02d}_{plat}.ass"
                generate_ass(words, start, end, ass_path, cfg["captions"],
                             pcfg["res_x"], pcfg["res_y"], pcfg["caption_margin_v"])
            out_path = out_dir / f"clip_{rank:02d}_{plat}.mp4"
            render_clip(src.path, start, end, ass_path, out_path, cfg, plat)
            files[plat] = str(out_path)
            done += 1
            emit(f"Rendering clip {rank}/{len(chosen)} ({plat})", 0.80 + 0.20 * done / total)
        results.append({
            "rank": rank,
            "start": round(start, 2),
            "end": round(end, 2),
            "duration": round(end - start, 2),
            "score": round(c.final, 4),
            "title": c.title or _fallback_title(c.text),
            "reason": c.reason,
            "hashtags": c.hashtags,
            "files": files,
        })

    (out_dir / "manifest.json").write_text(
        json.dumps({"source": str(source), "title": src.title, "clips": results},
                   indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    emit("Done", 1.0)
    return results
