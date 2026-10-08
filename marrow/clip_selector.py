from .candidates import overlap_ratio


def combine_scores(cands, llm_weight=0.65):
    """final = w*LLM + (1-w)*heuristic; heuristic only if the LLM did not score it."""
    for c in cands:
        if c.llm_score is None:
            c.final = c.heuristic
        else:
            c.final = llm_weight * c.llm_score + (1.0 - llm_weight) * c.heuristic
    return cands


def select_clips(cands, target_count):
    """Best-first selection of non-overlapping clips."""
    chosen = []
    for c in sorted(cands, key=lambda x: x.final, reverse=True):
        if all(overlap_ratio(c, s) == 0.0 for s in chosen):
            chosen.append(c)
        if len(chosen) >= target_count:
            break
    return chosen


def padded_bounds(c, pad_start, pad_end, source_duration):
    """Add small lead-in and tail, clamped to the source."""
    first = c.sentences[0].words[0].start
    last = c.sentences[-1].words[-1].end
    start = max(0.0, first - pad_start)
    end = min(source_duration, last + pad_end)
    return start, end
