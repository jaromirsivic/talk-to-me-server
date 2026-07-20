import pytest

from talk_to_me_server.storage.paths import PathEscapeError, contained_path


def test_contained_path_accepts_descendants_and_rejects_escape(tmp_path) -> None:
    root = tmp_path / "root"
    root.mkdir()

    assert contained_path(root, "job-1", "values", "000.wav") == (
        root.resolve() / "job-1" / "values" / "000.wav"
    )
    with pytest.raises(PathEscapeError):
        contained_path(root, "..", "outside.wav")
    with pytest.raises(PathEscapeError):
        contained_path(root, str((tmp_path / "outside.wav").resolve()))


def test_contained_path_rejects_symlink_escape(tmp_path) -> None:
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    link = root / "link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"symlinks unavailable: {error}")

    with pytest.raises(PathEscapeError):
        contained_path(root, "link", "file.wav")
