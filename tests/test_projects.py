import tempfile

import pytest

from marrow.server import ApiError, App


def _app_with_project():
    app = App(tempfile.mkdtemp())
    pid = "a1b2c3d4e5"
    app.projects[pid] = {"id": pid, "name": "T", "source": "x", "source_kind": "file",
                         "status": "done", "stage": "", "progress": 1.0, "created": 0,
                         "started": 0, "finished": 1, "error": None, "video_id": None,
                         "settings": {}, "clips": [], "locked": False}
    return app, pid


def test_lock_blocks_delete():
    app, pid = _app_with_project()
    out = app.set_locked(pid, {"locked": True})
    assert out["locked"] is True
    with pytest.raises(ApiError):
        app.delete_project(pid, False)
    out = app.set_locked(pid, {"locked": False})
    assert out["locked"] is False
    assert app.delete_project(pid, False) == {"ok": True}
    assert pid not in app.projects


def test_lock_toggle_defaults():
    app, pid = _app_with_project()
    assert app.set_locked(pid, {})["locked"] is True
    assert app.set_locked(pid, {})["locked"] is False


def test_public_includes_locked():
    app, pid = _app_with_project()
    assert app.public(app.projects[pid])["locked"] is False
