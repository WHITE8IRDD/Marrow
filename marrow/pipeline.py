import json
import re
import shutil
import time
from pathlib import Path

from .audio_features import assign_word_energy, compute_energy
from .candidates import build_sentences, generate_candidates, score_candidates, shortlist
from .captioner import clean_words, generate_ass
from .clip_selector import combine_scores, padded_bounds, select_clips
from .config import load_config
from .downloader import _find_source, fetch_source, prepare_source, resolve_source
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


def _fallback_reason(text: str) -> str:
    sents = re.split(r"(?<=[.!?؟…])\s+", text.strip())
    return " ".join(sents[:2])[:160]


def _fallback_tags(text: str):
    from .candidates import top_keywords

    return top_keywords(text)


def _write_manifest(output_dir, src, source, results):
    out_dir = ensure_dir(Path(output_dir) / src.video_id)
    (out_dir / "manifest.json").write_text(
        json.dumps({"source": str(source), "title": src.title, "clips": results},
                   indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return out_dir


def _fmt_span(sec):
    sec = max(0, int(round(sec)))
    m, s = divmod(sec, 60)
    return f"{m}:{s:02d}"


def run_pipeline(source, output_dir="output", config_path="config.yaml", clip_count=None,
                 clip_duration=None, platform="shorts", layout=None, use_llm=None,
                 force=False, progress=None, config=None, on_source=None, eta_holder=None):
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
    t_stage, clock = {}, [time.monotonic()]

    def tick(name):
        now = time.monotonic()
        t_stage[name] = t_stage.get(name, 0.0) + (now - clock[0])
        clock[0] = now

    # 1. Resolve source (fast, no download). A cached proxy feeds transcription
    # immediately; the full file downloads before rendering.
    emit("Preparing source video", 0.02)
    src = resolve_source(source, cfg["cache_dir"], cfg)
    proxy = src.workdir / "proxy.mp4"
    have_full, full_audio_only = _find_source(src.workdir)
    if have_full is None and src.path is not None and Path(src.path).exists():
        have_full, full_audio_only = Path(src.path), False  # local file: render from it
    if proxy.exists():
        duration = probe_duration(proxy)
    elif have_full is not None:
        duration = probe_duration(have_full)
    else:
        duration = None
    if duration is not None and duration < min_dur:
        raise ValueError(f"Video is only {duration:.0f}s; shorter than the minimum clip length ({min_dur}s).")
    if on_source and duration is not None:
        on_source(src, duration)
    eta = None
    if eta_holder is not None and duration is not None:
        from .eta import Eta
        eta = Eta(duration, clip["target_count"], max_dur, bool(cfg["llm"]["enabled"]),
                  Path(cfg["cache_dir"]) / "timings.json")
        eta_holder["eta"] = eta

    # 2. Extract audio (proxy first for speed, full source otherwise)
    audio_path = src.workdir / "audio.wav"
    if force or not audio_path.exists():
        asrc = proxy if proxy.exists() else None
        if asrc is None:
            if have_full is None:
                src = fetch_source(src, source, cfg)
                tick("download")
                if eta:
                    eta.update("download", 1.0)
                have_full, full_audio_only = _find_source(src.workdir)
            asrc = have_full
            duration = probe_duration(asrc)
            if duration < min_dur:
                raise ValueError(f"Video is only {duration:.0f}s; shorter than the minimum clip length ({min_dur}s).")
            if on_source:
                on_source(src, duration)
            if eta_holder is not None and eta is None:
                from .eta import Eta
                eta = Eta(duration, clip["target_count"], max_dur, bool(cfg["llm"]["enabled"]),
                          Path(cfg["cache_dir"]) / "timings.json")
                eta.update("download", 1.0)
                eta_holder["eta"] = eta
        emit("Extracting audio", 0.08)
        run_ffmpeg(["-i", asrc, "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", audio_path])
        tick("audio")
    if eta:
        eta.update("audio", 1.0)
    if duration is None:  # stale cache without any video file: fall back to audio length
        duration = probe_duration(audio_path)
        if duration < min_dur:
            raise ValueError(f"Video is only {duration:.0f}s; shorter than the minimum clip length ({min_dur}s).")

    # 3. Transcribe (cached)
    wcfg = cfg["whisper"]
    words_path = src.workdir / "words.json"
    words, lang = (None, None) if force else _load_words(words_path, wcfg["model"])
    if words is None:
        def tprog(frac, speed, t=None, line=None):
            if eta:
                eta.update("transcribe", frac)
            emit(f"Transcribing · {int(frac*100)}% · {speed:.1f}x realtime", 0.12 + 0.28 * frac,
                 log=line, scan={"t": round(t or 0.0, 2), "dur": round(duration, 2)} if t else None)

        words, lang = transcribe(audio_path, wcfg["model"], wcfg["device"], wcfg["compute_type"],
                                 wcfg["language"], wcfg.get("beam_size", 1),
                                 wcfg.get("batch_size", 8), wcfg.get("quality", "fast"),
                                 on_progress=tprog)
        words = clean_words(words)
        _save_words(words_path, f"auto:{lang}" if wcfg["model"] == "auto" else wcfg["model"], words)
    else:
        words = clean_words(words)
    tick("transcribe")
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

    cands = score_candidates(generate_candidates(sentences, min_dur, max_dur))
    if not cands:
        raise ValueError(f"No clip candidates between {min_dur}s and {max_dur}s. Try a wider duration range.")
    emit("Finding candidate clips", 0.46, counts={"moments": len(cands), "short": 0})

    lcfg = cfg["llm"]
    llm_model = "qwen2.5:7b-instruct" if (lang or "").startswith("ar") else lcfg["model"]
    scorer = OllamaScorer(llm_model, lcfg["host"], lcfg["timeout"]) if lcfg["enabled"] else None
    llm_ready = bool(scorer and scorer.available())
    hw.set_engine("llm", device="gpu" if llm_ready else "off",
                  model=lcfg["model"] if llm_ready else None,
                  fallback=None if llm_ready else "Ollama unreachable or model not pulled")
    k = lcfg["max_candidates"] if llm_ready else clip["target_count"] * 4
    short = shortlist(cands, k)
    prog_clips = [{
        "rank": n, "start": round(c.start, 2), "end": round(c.end, 2),
        "duration": round(c.end - c.start, 2), "score": round(c.heuristic, 4),
        "title": _fallback_title(c.text), "reason": "", "hashtags": [],
        "status": "rendering", "files": {}, "render_pct": 0.0, "render_eta": None,
    } for n, c in enumerate(short[:clip["target_count"]], 1)]
    emit("Shortlisted candidate moments", 0.46, clips=prog_clips,
         counts={"moments": len(cands), "short": len(short)})

    # 6. LLM judgment (cached, batched in groups of 20)
    if llm_ready:
        cache_path = src.workdir / "llm_cache.json"
        cache = {}
        if cache_path.exists() and not force:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        keys = [f"{llm_model}|{c.start:.2f}|{c.end:.2f}" for c in short]
        need = [i for i, (k, c) in enumerate(zip(keys, short)) if not cache.get(k)]
        for g in range(0, len(need), 20):
            group = need[g:g + 20]
            try:
                got = scorer.batch_score([short[i].text for i in group], lang)
            except Exception:
                got = [None] * len(group)
            for i, parsed in zip(group, got):
                if parsed is None:  # batch miss: retry this window alone
                    parsed = scorer.score(short[i].text, lang)
                if parsed:
                    cache[keys[i]] = parsed
        for n, (c, key) in enumerate(zip(short, keys), 1):
            parsed = cache.get(key)
            if parsed:
                c.llm, c.llm_score = parsed, llm_score(parsed)
                c.title, c.reason, c.hashtags = parsed["title"], parsed["reason"], parsed["hashtags"]
            emit(f"Scoring clips with LLM ({n}/{len(short)})", 0.46 + 0.34 * n / len(short),
                 log=f"Scoring window {n}/{len(short)} [{c.start:.1f}s -> {c.end:.1f}s]" if parsed else None)
            if eta:
                eta.update("score", n / len(short))
        cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    else:
        log.warning("LLM scoring unavailable; ranking by audio/heuristics only.")
        emit("Ranking by audio and heuristics", 0.46, log="LLM unavailable; ranking by audio/heuristics only.")
        if eta:
            eta.update("score", 1.0)

    combine_scores(short, lcfg["weight"])
    chosen = select_clips(short, clip["target_count"])
    tick("score")
    emit("Ranked candidate moments", 0.80,
         candidates=[{"s": round(c.start, 2), "e": round(c.end, 2),
                      "score": round(c.final * 100)} for c in short],
         log=f"Scored {len(short)} windows; keeping {len(chosen)}.")
    (src.workdir / "candidates.json").write_text(
        json.dumps([{"s": round(c.start, 2), "e": round(c.end, 2),
                     "heuristic": round(c.heuristic, 4),
                     "final": round(c.final, 4), "title": c.title,
                     "reason": c.reason, "hashtags": c.hashtags} for c in short],
                   ensure_ascii=False),
        encoding="utf-8",
    )

    # Full-res source for rendering (transcription may have run on the proxy).
    have_full, full_audio_only = _find_source(src.workdir)
    if have_full is None and src.path is not None and Path(src.path).exists():
        have_full, full_audio_only = Path(src.path), False
    if have_full is None:
        emit("Downloading full video", 0.78)
        full_src = fetch_source(resolve_source(source, cfg["cache_dir"], cfg), source, cfg)
        tick("download")
        if eta:
            eta.update("download", 1.0)
        have_full, full_audio_only = _find_source(src.workdir)
        duration = probe_duration(have_full)
        if on_source:
            on_source(full_src, duration)
    render_src = have_full
    if full_audio_only:
        moments = []
        for rank, c in enumerate(chosen, 1):
            moments.append({
                "rank": rank, "start": round(c.start, 2), "end": round(c.end, 2),
                "duration": round(c.end - c.start, 2), "score": round(c.final, 4),
                "title": c.title or _fallback_title(c.text),
                "reason": c.reason or _fallback_reason(c.text),
                "hashtags": c.hashtags or _fallback_tags(c.text), "files": {},
            })
        _write_manifest(output_dir, src, source, moments)
        raise RuntimeError(
            "Only audio could be downloaded (YouTube blocked the video track). "
            "The strongest moments are listed in manifest.json. Sign in to YouTube "
            "in your browser, then enable 'Use browser cookies' in Settings → "
            "Advanced → Cookies and run again.")

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
    for rank, c in enumerate(chosen, 1):
        if rank - 1 < len(prog_clips):
            prog_clips[rank - 1].update(
                start=round(c.start, 2), end=round(c.end, 2),
                duration=round(c.end - c.start, 2), score=round(c.final, 4),
                title=c.title or _fallback_title(c.text), reason=c.reason,
                hashtags=c.hashtags)
    del prog_clips[len(chosen):]
    emit("Rendering clips", 0.80, clips=prog_clips)
    try:
        from . import studio as _studio

        for rank, c in enumerate(chosen, 1):
            s, e = padded_bounds(c, clip["pad_start"], clip["pad_end"], duration)
            _studio.make_clip_thumb(src.path, s, src.workdir / f"pre_{rank:02d}.jpg")
    except Exception:
        log.debug("clip preview thumbs failed", exc_info=True)

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
            t_start = time.time()
            last_emit = [0.0]

            def rprog(frac):
                el = time.time() - t_start
                left = el / frac * (1 - frac) if frac > 0.05 else None
                with lock:
                    for pc in prog_clips:
                        if pc["rank"] == rank:
                            pc["render_pct"] = round(frac, 3)
                            pc["render_eta"] = round(left, 1) if left is not None else None
                    if el - last_emit[0] > 2.0:
                        last_emit[0] = el
                        emit(f"Rendering clip {rank}/{len(chosen)} ({plat})",
                             0.80 + 0.20 * state["done"] / max(1, len(tasks)), clips=prog_clips)

            render_clip(render_src, start, end, ass_path, out_path, cfg, plat, on_progress=rprog)
            outcome = (start, end, str(out_path), None)
        except Exception as e:
            outcome = (None, None, None, e)
        with lock:
            state["done"] += 1
            finished[(rank, plat)] = outcome
            d = state["done"]
            if outcome[3] is None:
                for pc in prog_clips:
                    if pc["rank"] == rank:
                        pc.setdefault("files", {})[plat] = outcome[2]
                        if len(pc["files"]) >= len(render_plats):
                            pc["status"] = "ready"
        if eta:
            eta.update("render", d / max(1, len(tasks)))
        emit(f"Rendering clip {rank}/{len(chosen)} ({plat})", 0.80 + 0.20 * d / max(1, len(tasks)),
             clips=prog_clips,
             log=f"Rendered clip {rank}/{len(chosen)} ({plat})." if outcome[3] is None else None)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(one, tasks))
    tick("render")

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
            "reason": c.reason or _fallback_reason(c.text),
            "hashtags": c.hashtags or _fallback_tags(c.text),
            "files": files,
        })

    _write_manifest(output_dir, src, source, results)
    xs = duration / max(t_stage.get("transcribe", 0.0), 0.01) if t_stage.get("transcribe") else 0.0
    log.info("Timings: download %s · audio %s · transcribe %s (%.1fx) · score %s · render %s · total %s",
             _fmt_span(t_stage.get("download", 0.0)), _fmt_span(t_stage.get("audio", 0.0)),
             _fmt_span(t_stage.get("transcribe", 0.0)), xs,
             _fmt_span(t_stage.get("score", 0.0)), _fmt_span(t_stage.get("render", 0.0)),
             _fmt_span(sum(t_stage.values())))
    emit("Done", 1.0)
    return results
