import importlib.util
from pathlib import Path

from marrow.captioner import clean_words, generate_ass
from marrow.models import Word

ASS_CHECK = Path(__file__).resolve().parents[1] / "scripts" / "ass_check.py"


def _load_ass_check():
    spec = importlib.util.spec_from_file_location("ass_check", ASS_CHECK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _words(text, per_word=0.4, dup_at=None):
    toks = text.split()
    if dup_at is not None:
        toks.insert(dup_at + 1, toks[dup_at])  # simulated batched-transcription repeat
    return [Word(i * per_word, i * per_word + per_word * 0.9, t, score=0.5)
            for i, t in enumerate(toks)]


def test_clean_words_merges_duplicates():
    words = _words("hello big world", dup_at=0)
    assert len(words) == 4
    cleaned = clean_words(words)
    assert [w.text for w in cleaned] == ["hello", "big", "world"]
    assert cleaned[0].end >= words[0].end


def test_clean_words_trims_overlaps():
    words = [Word(0.0, 0.5, "a", score=0.5), Word(0.4, 0.9, "b", score=0.5)]
    cleaned = clean_words(words)
    assert cleaned[0].end <= cleaned[1].start


def test_one_word_events_have_single_active_word(tmp_path):
    out = tmp_path / "one.ass"
    n = generate_ass(_words("make it go viral now"), 0.0, 3.0, out,
                     {"preset": "one-word", "overrides": {}})
    assert n == 5
    mod = _load_ass_check()
    assert mod.check_file(str(out)) == []
    text = out.read_text(encoding="utf-8")
    assert "VIRAL" in text  # uppercase kept for the latin one-word preset


def test_one_word_arabic_stays_connected(tmp_path):
    out = tmp_path / "arone.ass"
    words = _words("هل تعلم ما هو السر")
    n = generate_ass(words, 0.0, 3.0, out, {"preset": "one-word", "overrides": {}})
    assert n == 5
    mod = _load_ass_check()
    assert mod.check_file(str(out)) == []
    text = out.read_text(encoding="utf-8")
    assert "السر" in text and ",Cairo," in text


def test_line_mode_with_dup_words_has_no_overlaps(tmp_path):
    out = tmp_path / "dup.ass"
    n = generate_ass(_words("this is is a test", dup_at=2), 0.0, 3.0, out,
                     {"preset": "bold-pop", "overrides": {}})
    assert n > 0
    mod = _load_ass_check()
    assert mod.check_file(str(out)) == []


def test_eta_remaining_falls_as_stage_progresses(tmp_path):
    import time

    from marrow.eta import Eta

    store = tmp_path / "timings.json"
    e = Eta(600, 5, 45, True, store)
    e.update("download", 1.0)
    e.update("audio", 1.0)
    e.update("transcribe", 0.2)
    time.sleep(0.2)
    r1 = e.remaining()
    e.update("transcribe", 0.8)
    time.sleep(0.2)
    r2 = e.remaining()
    assert r2 < r1
    e.update("score", 1.0)
    e.update("render", 0.5)
    time.sleep(0.05)
    e.update("render", 1.0)
    e.finish()
    import json

    h = json.loads(store.read_text(encoding="utf-8"))
    assert "transcribe_x" in h and "render_x" in h


def test_settings_migration_small_to_auto(tmp_path):
    import json

    from marrow.server import App

    (tmp_path / "settings.json").write_text(json.dumps({"whisper": {"model": "small"}}))
    app = App(str(tmp_path))
    assert app.saved_settings["whisper"]["model"] == "auto"
    assert app.saved_settings["settings_version"] == 1
    assert json.loads((tmp_path / "settings.json").read_text())["whisper"]["model"] == "auto"
