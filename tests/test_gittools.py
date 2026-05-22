from __future__ import annotations

import subprocess
from pathlib import Path

from conftest import git_init

from loghop.gittools import GitRepo


def _commit_file(root: Path, path: str, text: str, message: str = "init") -> None:
    (root / path).write_text(text, encoding="utf-8")
    subprocess.run(["git", "add", path], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", message], cwd=root, check=True, capture_output=True
    )


def test_snapshot_normalizes_rename_paths(tmp_path: Path) -> None:
    git_init(tmp_path)
    _commit_file(tmp_path, "a.txt", "hello\n")

    subprocess.run(["git", "mv", "a.txt", "b.txt"], cwd=tmp_path, check=True)

    repo = GitRepo(tmp_path)
    snapshot = repo.snapshot()

    assert snapshot.changed_files == ["b.txt"]
    assert snapshot.staged == ["b.txt"]

    patch = repo.diff_for_files(snapshot.changed_files)
    assert "rename from a.txt" in patch
    assert "rename to b.txt" in patch


def test_diff_for_files_includes_staged_changes(tmp_path: Path) -> None:
    git_init(tmp_path)
    _commit_file(tmp_path, "tracked.txt", "hello\n")

    (tmp_path / "tracked.txt").write_text("hello\nupdated\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=tmp_path, check=True, capture_output=True)

    repo = GitRepo(tmp_path)
    snapshot = repo.snapshot()

    assert snapshot.staged == ["tracked.txt"]
    patch = repo.diff_for_files(snapshot.changed_files)
    assert "tracked.txt" in patch
    assert "+updated" in patch


def test_diff_for_files_includes_untracked_files(tmp_path: Path) -> None:
    git_init(tmp_path)
    _commit_file(tmp_path, "tracked.txt", "hello\n")

    (tmp_path / "newfile.txt").write_text("new\nline\n", encoding="utf-8")

    repo = GitRepo(tmp_path)
    snapshot = repo.snapshot()

    assert snapshot.untracked == ["newfile.txt"]
    patch = repo.diff_for_files(snapshot.changed_files)
    assert "new file mode" in patch
    assert "+++ b/newfile.txt" in patch
    assert "+new" in patch


def test_snapshot_clean_repo(tmp_path: Path) -> None:
    git_init(tmp_path)
    _commit_file(tmp_path, "a.txt", "hello\n")

    repo = GitRepo(tmp_path)
    snapshot = repo.snapshot()

    assert snapshot.dirty is False
    assert snapshot.branch is not None
    assert snapshot.head is not None
    assert snapshot.diff_stat == ""
