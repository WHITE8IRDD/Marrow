"""Sentence building, candidate-window generation and cheap heuristic scoring."""
import re

import numpy as np

from .models import Candidate, Sentence

END_PUNCT = (".", "?", "!", "…", "؟")
TRAILING_QUOTES = "\"'”’)"

AR_DIACRITICS = re.compile(r"[ً-ٟـ]")
AR_HOOK_RE = re.compile(
    r"^(هل|كيف|لماذا|ماذا|ما|من|متى|أين|السر|الحقيقة|لن تصدق|أهم|أخطر|خطأ|احذر|توقف|تخيل|شاهد)\b"
)
AR_KEYWORDS = (
    "السر", "الحقيقة", "لن تصدق", "أهم", "مذهل", "لا يصدق", "مجانا", "حصري",
    "عاجل", "أفضل", "أسوأ", "خطير", "مهم", "خطأ", "فضيحة", "صادم",
)
AR_KW_RE = re.compile(r"\b(" + "|".join(re.escape(k) for k in AR_KEYWORDS) + r")\b")


def normalize_ar(text: str) -> str:
    text = AR_DIACRITICS.sub("", text)
    return text.translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي"}))

CONJ_START = {"and", "but", "so", "because", "which", "that", "or", "then", "also", "cause", "plus"}

HOOK_RE = re.compile(
    r"^(what|why|how|when|who|did you|do you|have you|imagine|here'?s|"
    r"the (secret|truth|reason|biggest|best|worst|first)|nobody|everyone|stop|never|"
    r"don'?t|if you|you (need|should|must)|\d+)\b",
    re.IGNORECASE,
)

KEYWORDS = (
    "amazing", "crazy", "insane", "unbelievable", "secret", "hack", "mistake", "truth",
    "never", "always", "worst", "best", "incredible", "shocking", "nobody", "everyone",
    "free", "million", "billion", "changed my life", "game changer", "biggest",
)
KW_RE = re.compile(r"\b(" + "|".join(re.escape(k) for k in KEYWORDS) + r")\b", re.IGNORECASE)


def _ends_sentence(text: str) -> bool:
    return text.rstrip(TRAILING_QUOTES).endswith(END_PUNCT)


def build_sentences(words, max_gap=0.8, max_words=30, max_dur=15.0):
    """Group words into sentence-like units using punctuation, pauses and length caps."""
    sentences, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        if (
            nxt is None
            or _ends_sentence(w.text)
            or nxt.start - w.end > max_gap
            or len(cur) >= max_words
            or w.end - cur[0].start >= max_dur
        ):
            sentences.append(
                Sentence(
                    start=cur[0].start,
                    end=cur[-1].end,
                    text=" ".join(x.text for x in cur),
                    words=cur,
                )
            )
            cur = []
    return sentences


def generate_candidates(sentences, min_dur, max_dur):
    """Every sentence-aligned window whose duration is within [min_dur, max_dur]."""
    out = []
    n = len(sentences)
    for i in range(n):
        for j in range(i, n):
            dur = sentences[j].end - sentences[i].start
            if dur > max_dur:
                break
            if dur >= min_dur:
                out.append(
                    Candidate(start=sentences[i].start, end=sentences[j].end,
                              sentences=sentences[i:j + 1])
                )
    return out


def hook_score(first_sentence: str) -> float:
    s = 0.2
    if HOOK_RE.match(first_sentence.strip()):
        s += 0.5
    if AR_HOOK_RE.match(normalize_ar(first_sentence).strip()):
        s += 0.5
    if "?" in first_sentence or "؟" in first_sentence:
        s += 0.3
    return min(1.0, s)


def keyword_score(text: str) -> float:
    hits = {m.lower() for m in KW_RE.findall(text)}
    ar_hits = set(AR_KW_RE.findall(normalize_ar(text)))
    return min((len(hits) + len(ar_hits)) / 3.0, 1.0)


def score_candidate(c: Candidate) -> float:
    words = [w for s in c.sentences for w in s.words]
    if not words:
        return 0.0
    dur = max(c.end - c.start, 1e-6)
    energies = np.array([w.score for w in words], dtype=float)
    energy = float(energies.mean())
    peak = float(np.percentile(energies, 90))
    density = min(len(words) / dur / 3.0, 1.0)  # ~3 words/sec is a lively pace
    speech_ratio = min(sum(w.end - w.start for w in words) / dur, 1.0)
    first = c.sentences[0].text
    score = (
        0.30 * energy
        + 0.15 * peak
        + 0.15 * density
        + 0.10 * speech_ratio
        + 0.20 * hook_score(first)
        + 0.10 * keyword_score(c.text)
    )
    tokens = first.split()
    first_word = tokens[0].lower().strip(",.") if tokens else ""
    if first_word in CONJ_START or first[:1].islower():
        score *= 0.85  # likely starts mid-thought
    speakers = [s.speaker for s in c.sentences if s.speaker]
    switches = sum(1 for a, b in zip(speakers, speakers[1:]) if a != b)
    if switches > 4:
        score *= 0.9  # choppy back-and-forth makes a poor standalone clip
    return float(min(1.0, max(0.0, score)))


def score_candidates(cands):
    for c in cands:
        c.heuristic = score_candidate(c)
    return cands


def overlap_ratio(a, b) -> float:
    inter = min(a.end, b.end) - max(a.start, b.start)
    if inter <= 0:
        return 0.0
    return inter / max(min(a.end - a.start, b.end - b.start), 1e-6)


def shortlist(cands, k, max_overlap=0.5):
    """Top-k by heuristic, skipping windows that mostly overlap an already chosen one."""
    chosen = []
    for c in sorted(cands, key=lambda x: x.heuristic, reverse=True):
        if all(overlap_ratio(c, s) <= max_overlap for s in chosen):
            chosen.append(c)
        if len(chosen) >= k:
            break
    return chosen
