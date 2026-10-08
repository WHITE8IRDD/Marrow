"""Missing browser-cookie database fallback.

If the saved browser is not installed, yt-dlp raises (wrapped in CookieLoadError)
``could not find <browser> cookies database in ...``. Marrow must retry the same
metadata, preview, or download operation without ``cookiesfrombrowser`` instead of
failing, stay on the no-browser path for the rest of that operation, and keep a
valid ``cookies.txt`` setting intact. Cookies stay optional throughout.
"""
import sys
import types

from marrow import downloader, probe
from marrow.downloader import (is_missing_browser_db, resolve_source,
                               download_with_fallback, ydl_opts)
from marrow.server import clean_global_settings

URL = "https://www.youtube.com/watch?v=abc123"
MISSING_CHROME = 'could not find chrome cookies database in "/home/user/.config/google-chrome"'


def _client_of(opts):
    pc = ((opts.get("extractor_args") or {}).get("youtube") or {}).get("player_client")
    return list(pc) if pc else None


def _fake_yt_dlp(monkeypatch, behaviour):
    """behaviour(mode, client, opts) returns metadata / None, or raises."""
    calls = []

    class FakeYDL:
        def __init__(self, opts):
            self.opts = dict(opts)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def extract_info(self, url, download=False):
            calls.append(("info", _client_of(self.opts), dict(self.opts)))
            return behaviour("info", _client_of(self.opts), self.opts)

        def download(self, urls):
            calls.append(("download", _client_of(self.opts), dict(self.opts)))
            behaviour("download", _client_of(self.opts), self.opts)

    fake = types.ModuleType("yt_dlp")
    fake.YoutubeDL = FakeYDL
    monkeypatch.setitem(sys.modules, "yt_dlp", fake)
    return calls


def _missing_db_error():
    # Real shape: CookieLoadError("failed to load cookies") with the FileNotFoundError
    # as __context__. The detector must see through the wrapper.
    err = RuntimeError("failed to load cookies")
    err.__context__ = FileNotFoundError(MISSING_CHROME)
    return err


def test_missing_db_detection_sees_through_the_wrapper():
    assert is_missing_browser_db(RuntimeError(MISSING_CHROME)) is True
    assert is_missing_browser_db(_missing_db_error()) is True
    # A locked database is a different problem and must NOT trigger the fallback.
    assert is_missing_browser_db(RuntimeError("Could not copy Chrome cookie database")) is False
    assert is_missing_browser_db(RuntimeError("Sign in to confirm you're not a bot")) is False


def test_metadata_retries_without_browser_cookies_and_stays_there(tmp_path, monkeypatch):
    """resolve_source: missing DB -> same client retried without cookies, rest stays clean."""
    SIGN_IN = "Sign in to confirm you're not a bot"

    def behaviour(mode, client, opts):
        if opts.get("cookiesfrombrowser"):
            raise _missing_db_error()
        if client is None:
            raise RuntimeError(SIGN_IN)  # default client refused even without cookies
        return {"id": "abc123", "title": "Talk", "duration": 90}

    calls = _fake_yt_dlp(monkeypatch, behaviour)
    cfg = {"cookies": {"from_browser": "chrome", "cookiefile": ""}}
    src = resolve_source(URL, tmp_path, cfg)

    assert (src.video_id, src.title, src.client) == ("abc123", "Talk", ["web"])
    # First try scans the missing database, the immediate retry and every later client do not.
    assert [c for _, c, _ in calls] == [None, None, ["web"]]
    assert calls[0][2].get("cookiesfrombrowser") == ("chrome",)
    assert all("cookiesfrombrowser" not in opts for _, _, opts in calls[1:])
    # The saved setting is untouched; only this operation went without browser cookies.
    assert cfg == {"cookies": {"from_browser": "chrome", "cookiefile": ""}}


def test_probe_metadata_retries_without_browser_cookies(tmp_path, monkeypatch):
    def behaviour(mode, client, opts):
        if opts.get("cookiesfrombrowser"):
            raise RuntimeError(MISSING_CHROME)
        return {"id": "abc123", "title": "Talk", "channel": "ch", "duration": 90,
                "thumbnail": None, "is_live": False, "webpage_url": URL}

    calls = _fake_yt_dlp(monkeypatch, behaviour)
    info = probe.probe(URL, {"cookies": {"from_browser": "chrome", "cookiefile": ""}})

    assert info["video_id"] == "abc123"
    assert len(calls) == 2
    assert calls[0][2].get("cookiesfrombrowser") == ("chrome",)
    assert "cookiesfrombrowser" not in calls[1][2]


def test_preview_retries_without_browser_cookies_but_keeps_cookiefile(tmp_path, monkeypatch):
    from pathlib import Path

    def behaviour(mode, client, opts):
        if opts.get("cookiesfrombrowser"):
            raise _missing_db_error()
        # The no-browser retry writes the file the real yt-dlp would have written.
        Path(str(opts["outtmpl"]).replace("%(ext)s", "mp4")).write_bytes(b"preview")

    calls = _fake_yt_dlp(monkeypatch, behaviour)
    cookiefile = str(tmp_path / "cookies.txt")
    Path(cookiefile).write_bytes(b"# Netscape HTTP Cookie File\n")
    cfg = {"cookies": {"from_browser": "chrome", "cookiefile": cookiefile}}
    probe.fetch_preview("pid-missing-db", URL, tmp_path, cfg)

    assert (tmp_path / "preview.mp4").read_bytes() == b"preview"
    assert len(calls) == 2
    assert calls[0][2].get("cookiesfrombrowser") == ("chrome",)
    assert "cookiesfrombrowser" not in calls[1][2]
    # A valid cookies.txt setting survives the fallback on every attempt.
    assert all(o.get("cookiefile") == cookiefile for _, _, o in calls)


def test_full_download_retries_without_browser_cookies(tmp_path, monkeypatch):
    def behaviour(mode, client, opts):
        if opts.get("cookiesfrombrowser"):
            raise RuntimeError(MISSING_CHROME)
        return None  # download succeeded without browser cookies

    calls = _fake_yt_dlp(monkeypatch, behaviour)
    ok = download_with_fallback(URL, str(tmp_path / "source.%(ext)s"),
                                {"cookies": {"from_browser": "chrome", "cookiefile": ""}})

    assert ok is True
    assert len(calls) == 2
    assert calls[0][2].get("cookiesfrombrowser") == ("chrome",)
    assert "cookiesfrombrowser" not in calls[1][2]
    # Same client + format retried, not skipped: both hits are default + first ladder rung.
    assert calls[0][1] == calls[1][1] is None
    assert calls[0][2]["format"] == calls[1][2]["format"] == downloader.FORMAT_LADDER[0]


def test_chromium_accepted_firefox_kept_cookies_stay_optional(tmp_path):
    assert clean_global_settings(
        {"cookies": {"from_browser": "chromium", "cookiefile": ""}})["cookies"]["from_browser"] == "chromium"
    assert clean_global_settings(
        {"cookies": {"from_browser": "Chromium", "cookiefile": ""}})["cookies"]["from_browser"] == "chromium"
    assert clean_global_settings(
        {"cookies": {"from_browser": "firefox", "cookiefile": ""}})["cookies"]["from_browser"] == "firefox"
    # Unknown browsers are cleared, never required; empty stays empty.
    assert clean_global_settings(
        {"cookies": {"from_browser": "helium", "cookiefile": ""}})["cookies"]["from_browser"] == ""
    assert clean_global_settings(
        {"cookies": {"from_browser": "", "cookiefile": ""}})["cookies"]["from_browser"] == ""
    # The option reaches yt-dlp unchanged.
    assert ydl_opts({"cookies": {"from_browser": "chromium", "cookiefile": ""}})["cookiesfrombrowser"] == ("chromium",)
    o = ydl_opts({"cookies": {"from_browser": "", "cookiefile": ""}})
    assert "cookiesfrombrowser" not in o and "cookiefile" not in o


def test_v2_v3_web_android_rotation_survives_the_cookie_fallback():
    # The PR #2 fallback must still be there: default, then web/android, then no-PO-token clients.
    assert downloader.PLAYER_CLIENT_CHAIN[0] is None
    assert downloader.PLAYER_CLIENT_CHAIN[1:3] == [["web"], ["android"]]
    assert probe.PLAYER_CLIENTS is downloader.PLAYER_CLIENT_CHAIN
