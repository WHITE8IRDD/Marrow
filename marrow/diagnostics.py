"""Setup checks for YouTube downloads: yt-dlp version, JavaScript runtime, solver and cookies.

Everything here is local and cheap (file checks, no network), so it can run on every
/api/system call and be quoted in error messages.
"""
from __future__ import annotations

import importlib.metadata
import importlib.util
import re
import shutil
import sysconfig
import time
from pathlib import Path

# Newest yt-dlp this build was tested with. The player-client chain in downloader.py relies on
# client names that older releases do not have, so the dependency floor is set to this too.
MIN_YTDLP = (2026, 8, 19)
MIN_YTDLP_TEXT = "2026.8.19"
JS_RUNTIMES = ("deno", "node", "bun")
SIGNED_IN_COOKIES = {"SID", "__Secure-1PSID", "__Secure-3PSID", "LOGIN_INFO"}


def _version_tuple(text):
    return tuple(int(x) for x in re.findall(r"\d+", text or "")[:3])


def ytdlp_version():
    try:
        return importlib.metadata.version("yt-dlp")
    except importlib.metadata.PackageNotFoundError:
        return None


def find_js_runtime():
    """The first JavaScript runtime yt-dlp can use, in the order deno, node, bun.

    pip installs deno into the Python scripts folder, which yt-dlp also searches, so a
    virtualenv does not need to be activated for it to be found.
    """
    scripts = Path(sysconfig.get_path("scripts") or "")
    for name in JS_RUNTIMES:
        for cand in (scripts / name, scripts / (name + ".exe")):
            if cand.is_file():
                return {"name": name, "path": str(cand)}
        exe = shutil.which(name)
        if exe:
            return {"name": name, "path": exe}
    return None


def ytdlp_status():
    version = ytdlp_version()
    runtime = find_js_runtime()
    return {
        "version": version,
        "min_version": MIN_YTDLP_TEXT,
        "new_enough": bool(version) and _version_tuple(version) >= MIN_YTDLP,
        "js_runtime": runtime["name"] if runtime else None,
        "js_runtime_path": runtime["path"] if runtime else None,
        "solver": importlib.util.find_spec("yt_dlp_ejs") is not None,
    }


def _count_cookies(path):
    """(YouTube/Google cookies that have not expired, whether a sign-in cookie is among them)."""
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return 0, False
    now = time.time()
    count, signed_in = 0, False
    for line in lines:
        # Netscape format: domain, include-subdomains, path, secure, expiry, name, value.
        if not line.strip() or (line.startswith("#") and not line.startswith("#HttpOnly_")):
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        domain = parts[0].replace("#HttpOnly_", "").lstrip(".")
        if "youtube.com" not in domain and "google.com" not in domain:
            continue
        try:
            expires = int(float(parts[4] or 0))
        except ValueError:
            expires = 0
        if expires and expires < now:
            continue
        count += 1
        if parts[5] in SIGNED_IN_COOKIES:
            signed_in = True
    return count, signed_in


def cookie_status(cookies):
    """Describe the YouTube cookie setting without reading any browser database."""
    ck = cookies if isinstance(cookies, dict) else {}
    browser = str(ck.get("from_browser") or "").strip().lower()
    cookie_file = str(ck.get("cookiefile") or "").strip()
    if browser:
        return {"source": "browser", "label": browser, "ok": True, "youtube_cookies": None,
                "signed_in": None,
                "message": f"read from {browser} each time Marrow downloads"}
    if cookie_file:
        path = Path(cookie_file).expanduser()
        if not path.is_file():
            return {"source": "file", "label": "file", "ok": False, "youtube_cookies": 0,
                    "signed_in": False, "message": "cookies.txt not found at the saved path"}
        count, signed_in = _count_cookies(path)
        if count == 0:
            message = "no YouTube cookies in this file; export again while signed in"
        elif not signed_in:
            message = f"{count} YouTube cookies, but no sign-in cookie; sign in and export again"
        else:
            message = f"signed in · {count} YouTube cookies in cookies.txt"
        return {"source": "file", "label": "file", "ok": count > 0 and signed_in,
                "youtube_cookies": count, "signed_in": signed_in, "message": message}
    return {"source": "none", "label": "none", "ok": False, "youtube_cookies": 0,
            "signed_in": False, "message": "not set"}


def summary(cookies=None):
    """One line for error messages, e.g. what was checked when a download failed."""
    st = ytdlp_status()
    ck = cookie_status(cookies)
    return (f"yt-dlp {st['version'] or 'not installed'}, "
            f"JavaScript runtime {st['js_runtime'] or 'none'}, "
            f"YouTube solver {'yes' if st['solver'] else 'no'}, "
            f"cookies {ck['label']}")
