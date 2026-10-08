from marrow.candidates import (
    build_sentences, generate_candidates, score_candidates, shortlist,
)
from marrow.captioner import generate_ass, group_words, hex_to_bgr
from marrow.clip_selector import combine_scores, select_clips
from marrow.config import DEFAULTS
from marrow.highlight_scorer import llm_score, parse_llm_json
from marrow.models import Candidate, Word
from marrow.renderer import build_filter_graph
from marrow.utils import format_ass_time


def make_words(text, start=0.0, per_word=0.4):
    words, t = [], start
    for tok in text.split():
        words.append(Word(t, t + per_word * 0.9, tok, score=0.5))
        t += per_word
    return words


def test_format_ass_time():
    assert format_ass_time(3661.5) == "1:01:01.50"
    assert format_ass_time(0.999) == "0:00:01.00"  # rounds up cleanly, never ".100"
    assert format_ass_time(-1) == "0:00:00.00"


def test_hex_to_bgr():
    assert hex_to_bgr("#FFE600") == "00E6FF"


def test_build_sentences_splits_on_punctuation():
    sents = build_sentences(make_words("Hello there. How are you? I am fine"))
    assert [s.text for s in sents] == ["Hello there.", "How are you?", "I am fine"]


def test_build_sentences_splits_on_pause():
    words = make_words("one two three") + make_words("four five six", start=10.0)
    assert len(build_sentences(words)) == 2


def _long_sentences(n=40):
    text = " ".join(f"This is sentence number {i}." for i in range(n))
    return build_sentences(make_words(text))


def test_candidates_respect_duration_bounds():
    cands = generate_candidates(_long_sentences(), min_dur=10, max_dur=20)
    assert cands
    assert all(10 <= c.duration <= 20 for c in cands)


def test_shortlist_limits_overlap():
    cands = score_candidates(generate_candidates(_long_sentences(), 10, 20))
    short = shortlist(cands, k=5, max_overlap=0.5)
    assert 1 <= len(short) <= 5
    for i, a in enumerate(short):
        for b in short[i + 1:]:
            inter = min(a.end, b.end) - max(a.start, b.start)
            assert inter <= 0.5 * min(a.duration, b.duration) + 1e-9


def _cand(start, end, final):
    c = Candidate(start=start, end=end, sentences=[])
    c.final = final
    return c


def test_select_clips_non_overlapping_best_first():
    cands = [_cand(0, 30, 0.9), _cand(20, 50, 0.95), _cand(60, 90, 0.5)]
    chosen = select_clips(cands, target_count=3)
    assert [c.final for c in chosen] == [0.95, 0.5]  # 0.9 overlaps the 0.95 clip


def test_combine_scores_falls_back_to_heuristic():
    a = _cand(0, 1, 0)
    a.heuristic, a.llm_score = 0.4, None
    b = _cand(0, 1, 0)
    b.heuristic, b.llm_score = 0.4, 1.0
    combine_scores([a, b], llm_weight=0.5)
    assert a.final == 0.4
    assert abs(b.final - 0.7) < 1e-9


def test_group_words_respects_limits():
    lines = group_words(make_words("a b c d e f g h"), max_words=3, max_chars=50)
    assert all(len(line) <= 3 for line in lines)


def test_generate_ass_is_repeatable_and_does_not_mutate(tmp_path):
    words = make_words("this is a test of the caption engine", start=10.0)
    original = [(w.start, w.end) for w in words]
    n1 = generate_ass(words, 10.0, 14.0, tmp_path / "a.ass", DEFAULTS["captions"])
    n2 = generate_ass(words, 10.0, 14.0, tmp_path / "b.ass", DEFAULTS["captions"])
    assert [(w.start, w.end) for w in words] == original
    assert n1 == n2 > 0
    assert (tmp_path / "a.ass").read_text() == (tmp_path / "b.ass").read_text()
    assert "Dialogue:" in (tmp_path / "a.ass").read_text()


def test_parse_llm_json_valid_and_invalid():
    raw = ('noise {"hook": 9, "standalone": 8, "emotion": 7, "payoff": 6, '
           '"title": "T", "reason": "r", "hashtags": ["#A", "b"]} tail')
    parsed = parse_llm_json(raw)
    assert parsed["hook"] == 9.0
    assert parsed["hashtags"] == ["a", "b"]
    assert parse_llm_json("no json here") is None
    assert parse_llm_json('{"hook": "x"}') is None


def test_llm_score_range():
    top = {"hook": 10, "standalone": 10, "emotion": 10, "payoff": 10}
    bottom = {"hook": 1, "standalone": 1, "emotion": 1, "payoff": 1}
    assert llm_score(top) == 1.0
    assert llm_score(bottom) == 0.0


def test_filter_graph_layouts():
    z = DEFAULTS["zoom"]
    crop = build_filter_graph("crop", 1080, 1920, 30, z, "clip.ass")
    assert "crop=" in crop and "ass=clip.ass:fontsdir=fonts[v]" in crop
    blur = build_filter_graph("blur_fit", 1080, 1920, 30, z, "clip.ass")
    assert "overlay" in blur and "boxblur" in blur
    assert build_filter_graph("crop", 1080, 1920, 30, z, None).endswith("[base]null[v]")
