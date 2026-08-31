from pathlib import Path

from src.utils.media_refs import (
    classify_media_ref,
    is_remote_media_ref,
    is_stable_project_media_ref,
    resolve_local_media_path,
    to_project_media_ref,
)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_classify_local_relative_path():
    assert classify_media_ref("uploads/foo.png") == "local_path"


def test_classify_local_absolute_path_under_output():
    abs_path = str(_project_root() / "output" / "uploads" / "foo.png")
    assert classify_media_ref(abs_path) == "local_path"


def test_classify_oss_object_key(monkeypatch):
    monkeypatch.setenv("OSS_BASE_PATH", "stable-test-base")
    assert (
        classify_media_ref("stable-test-base/project_1/assets/foo.png")
        == "object_key"
    )


def test_classify_remote_url():
    assert classify_media_ref("https://example.com/a.png") == "remote_url"
    assert is_remote_media_ref("http://example.com/a.png")
    assert is_remote_media_ref("blob:https://example.com/abc")
    assert not is_stable_project_media_ref("blob:https://example.com/abc")


def test_classify_data_uri_is_not_stable_storage():
    value = "data:image/png;base64,AAAA"
    assert classify_media_ref(value) == "data_uri"
    assert not is_stable_project_media_ref(value)


def test_resolve_local_relative_path_to_absolute():
    resolved = resolve_local_media_path("uploads/foo.png")
    expected = str((_project_root() / "output" / "uploads" / "foo.png").resolve())
    assert resolved == expected


def test_resolve_local_absolute_path_under_output():
    input_path = str(_project_root() / "output" / "video" / "clip.mp4")
    expected = str((_project_root() / "output" / "video" / "clip.mp4").resolve())
    assert resolve_local_media_path(input_path) == expected


def test_classify_windows_backslash_relative_path():
    """Refs written on Windows carry backslashes; they are still local paths.

    Asset state produced by os.path.join on Windows looks like
    'assets\\props\\x.png'. Treating it as unknown made every provider that
    needs a URL-compatible source fail with a misleading "configure OSS".
    """
    assert classify_media_ref("assets\\props\\foo.png") == "local_path"


def test_resolve_windows_backslash_relative_path():
    resolved = resolve_local_media_path("uploads\\nested\\foo.png")
    expected = str(
        (_project_root() / "output" / "uploads" / "nested" / "foo.png").resolve()
    )
    assert resolved == expected


def test_classify_windows_backslash_object_key(monkeypatch):
    monkeypatch.setenv("OSS_BASE_PATH", "stable-test-base")
    assert (
        classify_media_ref("stable-test-base\\project_1\\assets\\foo.png")
        == "object_key"
    )


def test_project_media_ref_uses_posix_separators():
    """Refs persisted into project state must be POSIX, on every platform.

    os.path.relpath(path, "output") returns 'assets\\scenes\\x.png' on
    Windows. Those refs then travel into OSS object keys, provider payloads
    and cross-machine project files, where a backslash is not a separator.
    """
    abs_path = str(_project_root() / "output" / "assets" / "scenes" / "x.png")

    assert to_project_media_ref(abs_path) == "assets/scenes/x.png"


def test_project_media_ref_accepts_an_explicit_root():
    abs_path = str(_project_root() / "output" / "video" / "clip.mp4")

    assert to_project_media_ref(abs_path, root="output") == "video/clip.mp4"


def test_project_media_ref_round_trips_through_the_resolver():
    abs_path = str(_project_root() / "output" / "audio" / "dialogue" / "a.mp3")

    ref = to_project_media_ref(abs_path)

    assert classify_media_ref(ref) == "local_path"
    assert resolve_local_media_path(ref) == str(Path(abs_path).resolve())
