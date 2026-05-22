from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

import loghop.gittools as gt


def _cp(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["git"], returncode=returncode, stdout=stdout, stderr=""
    )


class TestGitRepoFromCwd:
    def test_found(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake_run(cwd: Path, args: list[str]) -> Any:
            if args[0] == "rev-parse" and "--show-toplevel" in args:
                return _cp(stdout=str(tmp_path) + "\n")
            if args[0] == "rev-parse" and "--is-bare-repository" in args:
                return _cp(stdout="false\n")
            return _cp(stdout=str(tmp_path) + "\n")

        monkeypatch.setattr(gt, "_run_git", fake_run)
        repo = gt.GitRepo.from_cwd(tmp_path)
        assert repo is not None
        assert repo.root == tmp_path

    def test_not_found(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(gt, "_run_git", lambda cwd, args: _cp(returncode=128))
        assert gt.GitRepo.from_cwd(tmp_path) is None

    def test_git_not_installed_returns_none(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def raise_no_git(cwd: Path, args: list[str]) -> Any:
            raise ValueError("git is not installed or not found in PATH")

        monkeypatch.setattr(gt, "_run_git", raise_no_git)
        assert gt.GitRepo.from_cwd(tmp_path) is None

    def test_bare_repo_returns_none(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake_run(cwd: Path, args: list[str]) -> Any:
            if "--is-bare-repository" in args:
                return _cp(stdout="true\n")
            return _cp(stdout=str(tmp_path) + "\n")

        monkeypatch.setattr(gt, "_run_git", fake_run)
        assert gt.GitRepo.from_cwd(tmp_path) is None


class TestGitRepoSnapshotCaching:
    def test_second_snapshot_uses_cache(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        git_calls: list[str] = []

        def fake_run(cwd: Path, args: list[str]) -> Any:
            git_calls.append(args[0])
            if args[0] == "status":
                return _cp("# branch.oid abc1234567\x00# branch.head main\x00")
            return _cp(stdout="")

        monkeypatch.setattr(gt, "_run_git", fake_run)
        repo = gt.GitRepo(tmp_path, cache_ttl=60.0)
        repo.snapshot()
        status_count = git_calls.count("status")
        repo.snapshot()
        assert git_calls.count("status") == status_count

    def test_cache_expires(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        call_count = {"n": 0}

        def fake_run(cwd: Path, args: list[str]) -> Any:
            call_count["n"] += 1
            if args[0] == "status":
                return _cp("# branch.oid abc\x00# branch.head main\x00")
            return _cp(stdout="")

        monkeypatch.setattr(gt, "_run_git", fake_run)
        repo = gt.GitRepo(tmp_path, cache_ttl=0.0)
        repo.snapshot()
        call_count["n"] = 0
        repo.snapshot()
        assert call_count["n"] > 0

    def test_invalidate_clears_cache(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        call_count = {"n": 0}

        def fake_run(cwd: Path, args: list[str]) -> Any:
            call_count["n"] += 1
            if args[0] == "status":
                return _cp("# branch.oid abc\x00# branch.head main\x00")
            return _cp(stdout="")

        monkeypatch.setattr(gt, "_run_git", fake_run)
        repo = gt.GitRepo(tmp_path, cache_ttl=600.0)
        repo.snapshot()
        repo.invalidate()
        call_count["n"] = 0
        repo.snapshot()
        assert call_count["n"] > 0


class TestGitRepoSnapshotData:
    def test_clean_repo(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake_run(cwd: Path, args: list[str]) -> Any:
            if args[0] == "status":
                return _cp("# branch.oid abc1234567\x00# branch.head main\x00")
            return _cp(stdout="")

        monkeypatch.setattr(gt, "_run_git", fake_run)
        repo = gt.GitRepo(tmp_path, cache_ttl=600.0)
        snap = repo.snapshot()
        assert snap.git_root == str(tmp_path)
        assert snap.branch == "main"
        assert snap.head == "abc1234567"
        assert snap.dirty is False
        assert snap.staged == []
        assert snap.diff_stat == ""

    def test_dirty_no_diff_stat_when_clean(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        diff_called = {"v": False}

        def fake_run(cwd: Path, args: list[str]) -> Any:
            if args[0] == "diff" and "--stat" in args:
                diff_called["v"] = True
            if args[0] == "status":
                return _cp("# branch.oid abc\x00# branch.head main\x00")
            return _cp(stdout="")

        monkeypatch.setattr(gt, "_run_git", fake_run)
        repo = gt.GitRepo(tmp_path, cache_ttl=600.0)
        snap = repo.snapshot()
        assert snap.dirty is False
        assert diff_called["v"] is False

    def test_modified_files(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake_run(cwd: Path, args: list[str]) -> Any:
            if args[0] == "status":
                return _cp(
                    "# branch.oid abc\x00# branch.head main\x00"
                    "1 .M N... 100644 100644 a b file.py\x00"
                )
            if args[0] == "diff" and "--stat" in args:
                return _cp("1 file changed, 2 insertions(+)\n")
            return _cp(stdout="")

        monkeypatch.setattr(gt, "_run_git", fake_run)
        repo = gt.GitRepo(tmp_path, cache_ttl=600.0)
        snap = repo.snapshot()
        assert snap.dirty is True
        assert "file.py" in snap.changed_files
        assert "file.py" in snap.unstaged
        assert snap.staged == []

    def test_staged_files(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake_run(cwd: Path, args: list[str]) -> Any:
            if args[0] == "status":
                return _cp(
                    "# branch.oid abc\x00# branch.head main\x00"
                    "1 AM N... 100644 100644 a b new.py\x00"
                )
            if args[0] == "diff" and "--stat" in args:
                return _cp("1 file changed\n")
            return _cp(stdout="")

        monkeypatch.setattr(gt, "_run_git", fake_run)
        repo = gt.GitRepo(tmp_path, cache_ttl=600.0)
        snap = repo.snapshot()
        assert "new.py" in snap.staged

    def test_untracked(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake_run(cwd: Path, args: list[str]) -> Any:
            if args[0] == "status":
                return _cp("# branch.oid abc\x00# branch.head main\x00? mystery.txt\x00")
            if args[0] == "diff" and "--stat" in args:
                return _cp("1 file changed\n")
            return _cp(stdout="")

        monkeypatch.setattr(gt, "_run_git", fake_run)
        repo = gt.GitRepo(tmp_path, cache_ttl=600.0)
        snap = repo.snapshot()
        assert "mystery.txt" in snap.untracked
        assert "mystery.txt" in snap.changed_files

    def test_detached_head(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake_run(cwd: Path, args: list[str]) -> Any:
            if args[0] == "status":
                return _cp("# branch.oid abc1234567\x00# branch.head (detached)\x00")
            return _cp(stdout="")

        monkeypatch.setattr(gt, "_run_git", fake_run)
        repo = gt.GitRepo(tmp_path, cache_ttl=600.0)
        snap = repo.snapshot()
        assert snap.branch == "DETACHED"
        assert snap.head == "abc1234567"


class TestGitRepoDefaultBranch:
    def test_from_upstream(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake_run(cwd: Path, args: list[str]) -> Any:
            return _cp(
                "# branch.oid abc\x00# branch.head main\x00# branch.upstream origin/main\x00"
            )

        monkeypatch.setattr(gt, "_run_git", fake_run)
        repo = gt.GitRepo(tmp_path, cache_ttl=600.0)
        snap = repo.snapshot()
        assert snap.default_branch == "main"

    def test_no_upstream_main_branch(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake_run(cwd: Path, args: list[str]) -> Any:
            return _cp("# branch.oid abc\x00# branch.head main\x00")

        monkeypatch.setattr(gt, "_run_git", fake_run)
        repo = gt.GitRepo(tmp_path, cache_ttl=600.0)
        snap = repo.snapshot()
        assert snap.default_branch == "main"

    def test_no_upstream_feature_branch(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fake_run(cwd: Path, args: list[str]) -> Any:
            return _cp("# branch.oid abc\x00# branch.head feature-x\x00")

        monkeypatch.setattr(gt, "_run_git", fake_run)
        repo = gt.GitRepo(tmp_path, cache_ttl=600.0)
        snap = repo.snapshot()
        assert snap.default_branch is None


class TestGitRepoDiffForFiles:
    def test_uses_cached_status(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        status_calls = {"n": 0}

        def fake_run(cwd: Path, args: list[str]) -> Any:
            if args[0] == "status":
                status_calls["n"] += 1
                return _cp(
                    "# branch.oid abc\x00# branch.head main\x00"
                    "1 .M N... 100644 100644 a b file.py\x00"
                )
            if args[0] == "diff" and "--stat" in args:
                return _cp("1 file changed\n")
            if args[0] == "diff":
                return _cp("diff --git a/file.py b/file.py\n+new line\n")
            return _cp(stdout="")

        monkeypatch.setattr(gt, "_run_git", fake_run)
        repo = gt.GitRepo(tmp_path, cache_ttl=600.0)
        repo.snapshot()
        count_before = status_calls["n"]
        repo.diff_for_files(["file.py"])
        assert status_calls["n"] == count_before

    def test_empty_files_returns_empty(self, tmp_path: Path) -> None:
        repo = gt.GitRepo(tmp_path)
        assert repo.diff_for_files([]) == ""

    def test_rejects_invalid_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake_run(cwd: Path, args: list[str]) -> Any:
            return _cp("# branch.oid abc\x00# branch.head main\x00")

        monkeypatch.setattr(gt, "_run_git", fake_run)
        repo = gt.GitRepo(tmp_path, cache_ttl=600.0)
        with pytest.raises(ValueError, match="flag"):
            repo.diff_for_files(["--dangerous"])


class TestGitRepoSnapshotToDict:
    def test_to_dict(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake_run(cwd: Path, args: list[str]) -> Any:
            if args[0] == "status":
                return _cp(
                    "# branch.oid abc\x00# branch.head main\x00# branch.upstream origin/main\x00"
                )
            return _cp(stdout="")

        monkeypatch.setattr(gt, "_run_git", fake_run)
        repo = gt.GitRepo(tmp_path, cache_ttl=600.0)
        d = repo.snapshot().to_dict()
        assert d["branch"] == "main"
        assert d["default_branch"] == "main"
        assert d["dirty"] is False


class TestRunGit:
    def test_sanitizes_dangerous_environment(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, object] = {}

        def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            captured["argv"] = argv
            captured["env"] = kwargs.get("env")
            return _cp(stdout=str(tmp_path) + "\n")

        monkeypatch.setenv("GIT_EXTERNAL_DIFF", "evil")
        monkeypatch.setenv("GIT_PAGER", "evil")
        monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/tmp/evil")
        monkeypatch.setattr("loghop.gittools.subprocess.run", fake_run)

        result = gt._run_git(tmp_path, ["rev-parse", "--show-toplevel"])

        assert result.returncode == 0
        assert captured["argv"] == [
            "git",
            "--no-pager",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "diff.external=",
            "rev-parse",
            "--show-toplevel",
        ]
        env = captured["env"]
        assert isinstance(env, dict)
        assert "GIT_EXTERNAL_DIFF" not in env
        assert "GIT_PAGER" not in env
        assert "GIT_CONFIG_GLOBAL" not in env
