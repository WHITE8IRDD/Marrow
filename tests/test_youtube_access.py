"""YouTube access: the player-client chain, sign-in errors and the setup checks.

Nothing here touches YouTube. yt-dlp is replaced by a fake that refuses or accepts each
player client, so the fallback order and the messages are checked deterministically.

* a "Sign in to confirm you're not a bot" error must make Marrow try the next client,
  not stop at the metadata step with a raw DownloadError
* when every client is refused the user gets the steps that fix it
* other failures (private, removed...) keep their own message
* the setup check reports yt-dlp, the JavaScript runtime, the solver and the cookies
"""
import sys
import types

import pytest

from marrow import diagnostics, downloader, probe
from marrow.downloader import (PLAYER_CLIENT_CHAIN, YouTubeBlockedError, download_with_fallback,
                               fetch_source, is_blocked_error, resolve_source, ydl_opts)

URL = "https://www.youtube.com/watch?v=abc123"
SIGN_IN = ("ERROR: [youtube] abc123: Sign in to confirm you\u2019re not a bot. Use --cookies-from-browser "
           "or --cookies for the authentication.")


def _raise(msg):
    raise RuntimeError(msg)


def _client_of(opts):
    pc = ((opts.get("extractor_args") or {}).get("youtube") or {}).get("player_client")
    return list(pc) if pc else None


def _fake_yt_dlp(monkeypatch, behaviour):
    """behaviour(mode, client, opts) returns metadata, or raises. Every call is recorded."""
    calls = []

    class FakeYDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def extract_info(self, url, download=False):
            calls.append(("info", _client_of(self.opts), self.opts.get("format")))
            return behaviour("info", _client_of(self.opts), self.opts)

        def download(self, urls):
            calls.append(("download", _client_of(self.opts), self.opts.get("format")))
            behaviour("download", _client_of(self.opts), self.opts)

    fake = types.ModuleType("yt_dlp")
    fake.YoutubeDL = FakeYDL
    monkeypatch.setitem(sys.modules, "yt_dlp", fake)
    return calls


def test_chain_starts_with_default_then_the_v3_rotation_then_no_po_token_fallbacks():
    # yt-dlp's own default goes first (it adapts to cookies / JavaScript runtime)...
    assert PLAYER_CLIENT_CHAIN[0] is None
    # ...then the client rotation used by the V2/V3 releases. Adaptive format
    # availability varies with YouTube's current PO-token/auth policy.
    assert PLAYER_CLIENT_CHAIN[1:3] == [["web"], ["android"]]
    # The clients whose formats do not need a PO token stay as trailing fallbacks
    # (age-gated / embedded videos); they must never replace web/android.
    named = [c[0] for c in PLAYER_CLIENT_CHAIN[3:]]
    assert named == ["tv_downgraded", "web_embedded", "visionos"]
    assert not {"web_safari", "android_vr", "ios", "mweb"} & set(named)


def test_download_tries_the_client_that_worked_for_metadata_first():
    assert downloader._clients_starting_with(["android"]) == [
        ["android"], None, ["web"], ["tv_downgraded"], ["web_embedded"], ["visionos"]]
    assert downloader._clients_starting_with(None) == PLAYER_CLIENT_CHAIN


def test_ydl_opts_enables_every_js_runtime_with_a_fresh_dict():
    o = ydl_opts({})
    assert o["js_runtimes"] == {"deno": {}, "node": {}, "bun": {}}
    o["js_runtimes"].pop("deno")  # yt-dlp edits this mapping in place; the next call must not see it
    assert "deno" in ydl_opts({})["js_runtimes"]


@pytest.mark.parametrize("msg,blocked", [
    (SIGN_IN, True),
    ("HTTP Error 403: Forbidden", True),
    ("ERROR: [youtube] abc123: Video unavailable. This video has been removed.", False),
])
def test_blocked_detection(msg, blocked):
    assert is_blocked_error(RuntimeError(msg)) is blocked


def test_metadata_falls_back_to_the_next_client_and_remembers_it(tmp_path, monkeypatch):
    def behaviour(mode, client, opts):
        if client in (None, ["web"]):
            raise RuntimeError(SIGN_IN)
        return {"id": "abc123", "title": "Talk", "duration": 90}

    calls = _fake_yt_dlp(monkeypatch, behaviour)
    src = resolve_source(URL, tmp_path, {"cookies": {}})

    assert [c for kind, c, _ in calls if kind == "info"] == [None, ["web"], ["android"]]
    assert src.client == ["android"]
    assert (src.video_id, src.title) == ("abc123", "Talk")


def test_every_client_refused_gives_the_steps_not_a_raw_error(tmp_path, monkeypatch):
    _fake_yt_dlp(monkeypatch, lambda mode, client, opts: _raise(SIGN_IN))
    with pytest.raises(YouTubeBlockedError) as exc:
        resolve_source(URL, tmp_path, {"cookies": {}})
    msg = str(exc.value)
    assert exc.value.user_facing is True
    assert "not a bot" in msg
    assert 'pip install -U "yt-dlp[default,deno]"' in msg
    assert "Settings → YouTube cookies" in msg
    assert "Last error:" in msg and "Sign in to confirm" in msg


def test_403_everywhere_is_reported_as_403(tmp_path, monkeypatch):
    _fake_yt_dlp(monkeypatch, lambda mode, client, opts: _raise("HTTP Error 403: Forbidden"))
    with pytest.raises(YouTubeBlockedError) as exc:
        resolve_source(URL, tmp_path, {"cookies": {}})
    assert "403 Forbidden" in str(exc.value) and "not a bot" not in str(exc.value)


def test_other_failures_keep_their_own_message(tmp_path, monkeypatch):
    _fake_yt_dlp(monkeypatch, lambda mode, client, opts:
                 _raise("ERROR: [youtube] abc123: Video unavailable. This video has been removed."))
    with pytest.raises(RuntimeError, match="Video unavailable") as exc:
        resolve_source(URL, tmp_path, {"cookies": {}})
    assert not isinstance(exc.value, YouTubeBlockedError)


def test_download_still_pulls_via_web_android_when_other_clients_have_no_formats(tmp_path, monkeypatch):
    """Regression test for the v4.0.0 breakage: a chain without the V3 web/android rotation
    could not pull YouTube videos. The default client and the no-PO-token fallback clients
    return no downloadable formats; the web/android rotation must still fetch the video."""
    def behaviour(mode, client, opts):
        if mode == "info":
            return {"id": "abc123", "title": "Talk", "duration": 90}
        if client in (None, ["tv_downgraded"], ["web_embedded"], ["visionos"]):
            raise RuntimeError("ERROR: [youtube] abc123: Requested format is not available.")
        # web/android answer: write the file the real yt-dlp would have written
        from pathlib import Path

        Path(str(opts["outtmpl"]).replace("%(ext)s", "mp4")).write_bytes(b"video")

    calls = _fake_yt_dlp(monkeypatch, behaviour)
    src = resolve_source(URL, tmp_path, {"cookies": {}})
    src = fetch_source(src, URL, {"cookies": {}})

    assert src.path is not None and src.path.name == "source.mp4"
    assert src.audio_only is False
    downloads = [c for kind, c, _ in calls if kind == "download"]
    assert ["web"] in downloads          # the V3 rotation rescued the download
    assert ["android"] not in downloads  # web answered first, android was never needed


def test_refused_client_skips_its_other_formats_then_the_next_client(tmp_path, monkeypatch):
    def behaviour(mode, client, opts):
        if mode == "download" and client is None:
            raise RuntimeError(SIGN_IN)

    calls = _fake_yt_dlp(monkeypatch, behaviour)
    assert download_with_fallback(URL, str(tmp_path / "source.%(ext)s"), {"cookies": {}}) is True
    downloads = [(c, f) for kind, c, f in calls if kind == "download"]
    # the refused default client skips its second format, the next one is the V3 rotation's web
    assert downloads == [(None, downloader.FORMAT_LADDER[0]), (["web"], downloader.FORMAT_LADDER[0])]


def test_preview_falls_back_to_the_v3_web_android_rotation(tmp_path, monkeypatch):
    def behaviour(mode, client, opts):
        if mode == "info":
            return {"id": "abc123", "title": "Talk", "duration": 90}
        if client is None:
            raise RuntimeError("ERROR: [youtube] abc123: Requested format is not available.")
        if client == ["web"]:
            from pathlib import Path

            Path(str(opts["outtmpl"]).replace("%(ext)s", "mp4")).write_bytes(b"preview")
            return
        raise RuntimeError("unexpected client")

    calls = _fake_yt_dlp(monkeypatch, behaviour)
    probe.fetch_preview("pid-preview", URL, tmp_path, {"cookies": {}})

    downloads = [c for kind, c, _ in calls if kind == "download"]
    # The default client gets all three preview formats; then `web` succeeds on the first.
    assert downloads == [None, None, None, ["web"]]
    assert (tmp_path / "preview.mp4").read_bytes() == b"preview"


def test_preview_and_probe_use_the_same_chain_and_report_the_refusal(tmp_path, monkeypatch):
    _fake_yt_dlp(monkeypatch, lambda mode, client, opts: _raise(SIGN_IN))
    with pytest.raises(YouTubeBlockedError):
        probe.probe(URL, {"cookies": {}})
    with pytest.raises(YouTubeBlockedError):
        probe.fetch_preview("pid-x", URL, tmp_path, {"cookies": {}})


def test_a_403_from_another_site_is_not_blamed_on_youtube(tmp_path, monkeypatch):
    _fake_yt_dlp(monkeypatch, lambda mode, client, opts: _raise("HTTP Error 403: Forbidden"))
    with pytest.raises(RuntimeError, match="403") as exc:
        resolve_source("https://videos.example.com/talk.mp4", tmp_path, {"cookies": {}})
    assert not isinstance(exc.value, YouTubeBlockedError)


def test_user_facing_errors_are_shown_without_a_python_type_prefix():
    from marrow.server import error_text

    assert error_text(YouTubeBlockedError("YouTube asked to confirm")) == "YouTube asked to confirm"
    assert error_text(ValueError("x")) == "ValueError: x"


def test_js_runtime_search_prefers_deno_in_the_scripts_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(diagnostics.sysconfig, "get_path", lambda name: str(tmp_path))
    monkeypatch.setattr(diagnostics.shutil, "which", lambda name: "/usr/bin/node" if name == "node" else None)
    assert diagnostics.find_js_runtime() == {"name": "node", "path": "/usr/bin/node"}
    (tmp_path / "deno").write_text("x")
    assert diagnostics.find_js_runtime()["name"] == "deno"


def test_ytdlp_version_floor(monkeypatch):
    monkeypatch.setattr(diagnostics, "ytdlp_version", lambda: "2025.1.26")
    assert diagnostics.ytdlp_status()["new_enough"] is False
    monkeypatch.setattr(diagnostics, "ytdlp_version", lambda: "2026.8.19")
    st = diagnostics.ytdlp_status()
    assert st["new_enough"] is True and st["min_version"] == "2026.8.19"


def test_cookie_file_is_counted_without_opening_a_browser(tmp_path):
    f = tmp_path / "cookies.txt"
    future = 4102444800  # 2100-01-01
    f.write_text(
        "# Netscape HTTP Cookie File\n"
        f".youtube.com\tTRUE\t/\tTRUE\t{future}\tLOGIN_INFO\tx\n"
        f"#HttpOnly_.youtube.com\tTRUE\t/\tTRUE\t{future}\tSID\ty\n"
        ".youtube.com\tTRUE\t/\tTRUE\t1000\tOLD\tz\n"          # expired: not counted
        f".example.com\tTRUE\t/\tTRUE\t{future}\tother\tw\n"   # not YouTube: not counted
    )
    st = diagnostics.cookie_status({"from_browser": "", "cookiefile": str(f)})
    assert st["youtube_cookies"] == 2 and st["signed_in"] is True and st["ok"] is True


def test_cookie_status_variants(tmp_path):
    none = diagnostics.cookie_status({})
    assert none["source"] == "none" and none["ok"] is False
    assert diagnostics.cookie_status({"from_browser": "Firefox"})["label"] == "firefox"
    missing = diagnostics.cookie_status({"cookiefile": str(tmp_path / "nope.txt")})
    assert missing["ok"] is False and "not found" in missing["message"]
