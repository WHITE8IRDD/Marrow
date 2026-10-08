import json
import shutil
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
from . import hw

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
        return None, None
    data = json.loads(path.read_text(encoding="utf-8"))
    stored = data.get("model")
    if stored != model and not (model == "auto" and isinstance(stored, str) and stored.startswith("auto:")):
        return None, None
    lang = stored.split(":", 1)[1] if isinstance(stored, str) and stored.startswith("auto:") else None
    return [Word(s, e, t) for s, e, t in data["words"]], lang


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
                 force=False, progress=None, config=None, on_source=None):
    """Run the full pipeline. Returns a list of result dicts (also saved as manifest.json)."""

    def emit(stage, frac, **kw):
        log.info("[%3d%%] %s", int(frac * 100), stage)
        if progress:
            progress(stage, frac, **kw)

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
    if on_source:
        on_source(src, duration)

    # 2. Extract audio
    audio_path = src.workdir / "audio.wav"
    if force or not audio_path.exists():
        emit("Extracting audio", 0.08)
        run_ffmpeg(["-i", src.path, "-vn", "-ac", "1", "-ar", "16000", audio_path])

    # 3. Transcribe (cached)
    wcfg = cfg["whisper"]
    words_path = src.workdir / "words.json"
    words, lang = (None, None) if force else _load_words(words_path, wcfg["model"])
    if words is None:
        def tprog(frac, speed, t=None, line=None):
            emit(f"Transcribing · {int(frac*100)}% · {speed:.1f}x realtime", 0.12 + 0.28 * frac,
                 log=line, scan={"t": round(t or 0.0, 2), "dur": round(duration, 2)} if t else None)

        words, lang = transcribe(audio_path, wcfg["model"], wcfg["device"], wcfg["compute_type"],
                                 wcfg["language"], wcfg.get("beam_size", 1),
                                 wcfg.get("batch_size", 8), wcfg.get("quality", "fast"),
                                 on_progress=tprog)
        _save_words(words_path, f"auto:{lang}" if wcfg["model"] == "auto" else wcfg["model"], words)
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
    llm_model = "qwen2.5:7b-instruct" if (lang or "").startswith("ar") else lcfg["model"]
    scorer = OllamaScorer(llm_model, lcfg["host"], lcfg["timeout"]) if lcfg["enabled"] else None
    llm_ready = bool(scorer and scorer.available())
    hw.set_engine("llm", device="gpu" if llm_ready else "off",
                  model=lcfg["model"] if llm_ready else None,
                  fallback=None if llm_ready else "Ollama unreachable or model not pulled")
    k = lcfg["max_candidates"] if llm_ready else clip["target_count"] * 4
    short = shortlist(cands, k)

    # 6. LLM judgment (cached)
    if llm_ready:
        cache_path = src.workdir / "llm_cache.json"
        cache = {}
        if cache_path.exists() and not force:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        for n, c in enumerate(short, 1):
            key = f"{llm_model}|{c.start:.2f}|{c.end:.2f}"
            parsed = cache.get(key) or scorer.score(c.text, lang)
            if parsed:
                cache[key] = parsed
                c.llm, c.llm_score = parsed, llm_score(parsed)
                c.title, c.reason, c.hashtags = parsed["title"], parsed["reason"], parsed["hashtags"]
            emit(f"Scoring clips with LLM ({n}/{len(short)})", 0.46 + 0.34 * n / len(short),
                 log=f"Scoring window {n}/{len(short)} [{c.start:.1f}s -> {c.end:.1f}s]" if parsed else None)
        cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    else:
        log.warning("LLM scoring unavailable; ranking by audio/heuristics only.")
        emit("Ranking by audio and heuristics", 0.46, log="LLM unavailable; ranking by audio/heuristics only.")

    combine_scores(short, lcfg["weight"])
    chosen = select_clips(short, clip["target_count"])
    emit("Ranked candidate moments", 0.80,
         candidates=[{"s": round(c.start, 2), "e": round(c.end, 2),
                      "score": round(c.final * 100)} for c in short],
         log=f"Scored {len(short)} windows; keeping {len(chosen)}.")

    # 7. Captions + render
    out_dir = ensure_dir(Path(output_dir) / src.video_id)
    work_ass = ensure_dir(src.workdir / "ass")
    results = []
    # Identical platform configs (same res + caption margin) render once, then copy.
    same_cfg = (
        len(plats) == 2
        and all(cfg["platforms"][plats[0]][k] == cfg["platforms"][plats[1]][k]
                for k in ("res_x", "res_y", "caption_margin_v"))
    )
    render_plats = [plats[0]] if same_cfg else list(plats)
    prog_clips = [{
        "rank": rank, "start": round(c.start, 2), "end": round(c.end, 2),
        "duration": round(c.end - c.start, 2), "score": round(c.final, 4),
        "title": c.title or _fallback_title(c.text), "reason": c.reason,
        "hashtags": c.hashtags, "status": "rendering", "files": {},
    } for rank, c in enumerate(chosen, 1)]
    emit("Rendering clips", 0.80, clips=prog_clips)

    import threading
    from concurrent.futures import ThreadPoolExecutor

    from .renderer import pick_encoder

    tasks = [(rank, c, plat) for rank, c in enumerate(chosen, 1) for plat in render_plats]
    workers = 2 if pick_encoder(cfg["render"].get("encoder", "auto")) == "h264_nvenc" else 1
    lock = threading.Lock()
    state = {"done": 0}
    finished = {}

    def one(task):
        rank, c, plat = task
        try:
            start, end = padded_bounds(c, clip["pad_start"], clip["pad_end"], duration)
            pcfg = cfg["platforms"][plat]
            ass_path = None
            if cfg["captions"]["enabled"]:
                ass_path = work_ass / f"clip_{rank:02d}_{plat}.ass"
                generate_ass(words, start, end, ass_path, cfg["captions"],
                             pcfg["res_x"], pcfg["res_y"], pcfg["caption_margin_v"])
            out_path = out_dir / f"clip_{rank:02d}_{plat}.mp4"
            render_clip(src.path, start, end, ass_path, out_path, cfg, plat)
            outcome = (start, end, str(out_path), None)
        except Exception as e:
            outcome = (None, None, None, e)
        with lock:
            state["done"] += 1
            finished[(rank, plat)] = outcome
            d = state["done"]
        emit(f"Rendering clip {rank}/{len(chosen)} ({plat})", 0.80 + 0.20 * d / max(1, len(tasks)),
             log=f"Rendered clip {rank}/{len(chosen)} ({plat})." if outcome[3] is None else None)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(one, tasks))

    for rank, c in enumerate(chosen, 1):
        files = {}
        for plat in plats:
            src_plat = plats[0] if same_cfg else plat
            start, end, fp, err = finished[(rank, src_plat)]
            if err is not None:
                raise err
            if same_cfg and plat != src_plat:
                dst = out_dir / f"clip_{rank:02d}_{plat}.mp4"
                shutil.copy(fp, dst)
                files[plat] = str(dst)
            else:
                files[plat] = fp
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
