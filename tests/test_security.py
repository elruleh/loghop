from __future__ import annotations

from pathlib import Path

from loghop.store._security import _is_safe_pattern, _matches, filter_paths, load_ignore_patterns


class TestIsSafePattern:
    def test_normal_pattern(self) -> None:
        assert _is_safe_pattern("*.log") is True
        assert _is_safe_pattern("secrets/") is True
        assert _is_safe_pattern(".env") is True

    def test_empty_pattern(self) -> None:
        assert _is_safe_pattern("") is False

    def test_absolute_path_slash(self) -> None:
        assert _is_safe_pattern("/etc/passwd") is False

    def test_absolute_path_backslash(self) -> None:
        assert _is_safe_pattern("\\\\server\\share") is False

    def test_parent_traversal(self) -> None:
        assert _is_safe_pattern("../secret") is False
        assert _is_safe_pattern("foo/../bar") is False

    def test_drive_letter(self) -> None:
        assert _is_safe_pattern("C:\\Windows") is False
        assert _is_safe_pattern("D:\\data") is False

    def test_valid_nested_path(self) -> None:
        assert _is_safe_pattern("subdir/file.txt") is True

    def test_solidus_pattern(self) -> None:
        assert _is_safe_pattern("node_modules/") is True


class TestMatches:
    def test_exact_match(self) -> None:
        assert _matches(".env", ".env") is True

    def test_glob_match(self) -> None:
        assert _matches("file.log", "*.log") is True
        assert _matches("file.txt", "*.log") is False

    def test_directory_pattern(self) -> None:
        assert _matches("node_modules", "node_modules/") is True
        assert _matches("node_modules/package.json", "node_modules/") is True
        assert _matches("other/file.txt", "node_modules/") is False

    def test_no_match(self) -> None:
        assert _matches("app.py", "*.log") is False

    def test_nested_glob(self) -> None:
        assert _matches("dir/secret.txt", "*.txt") is True


class TestFilterPaths:
    def test_no_patterns(self) -> None:
        paths = ["a.py", "b.py"]
        assert filter_paths(paths, []) == paths

    def test_filters_matching(self) -> None:
        paths = ["app.py", "secret.key", "config.toml"]
        patterns = ["*.key"]
        assert filter_paths(paths, patterns) == ["app.py", "config.toml"]

    def test_filters_directory(self) -> None:
        paths = ["app.py", "node_modules", "node_modules/react/index.js"]
        patterns = ["node_modules/"]
        assert filter_paths(paths, patterns) == ["app.py"]

    def test_multiple_patterns(self) -> None:
        paths = ["app.py", ".env", "secret.key", "node_modules/foo"]
        patterns = [".env", "*.key", "node_modules/"]
        assert filter_paths(paths, patterns) == ["app.py"]

    def test_no_match_returns_all(self) -> None:
        paths = ["a.py", "b.py"]
        patterns = ["*.log"]
        assert filter_paths(paths, patterns) == paths

    def test_path_traversal_blocked(self, tmp_path: Path) -> None:
        paths = ["safe.py", "../../etc/passwd"]
        assert filter_paths(paths, [], root=tmp_path) == ["safe.py"]

    def test_root_parameter(self, tmp_path: Path) -> None:
        (tmp_path / "sub").mkdir()
        paths = ["sub/file.txt", "outside.txt"]
        result = filter_paths(paths, [], root=tmp_path)
        assert "sub/file.txt" in result


class TestLoadIgnorePatterns:
    def test_no_file(self, tmp_path: Path) -> None:
        assert load_ignore_patterns(tmp_path) == []

    def test_reads_patterns(self, tmp_path: Path) -> None:
        import subprocess

        from loghop.store import init_project, project_paths

        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.email", "dev@example.com"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.name", "Dev"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=tmp_path, check=True)
        (tmp_path / "x").write_text("x")
        subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-qm", "i"], cwd=tmp_path, check=True)
        init_project(tmp_path)
        paths = project_paths(tmp_path)
        paths.ignore.write_text("*.log\n# comment\n.env\n", encoding="utf-8")
        patterns = load_ignore_patterns(tmp_path)
        assert "*.log" in patterns
        assert ".env" in patterns
        assert len(patterns) == 2

    def test_skips_unsafe_patterns(self, tmp_path: Path) -> None:
        import subprocess

        from loghop.store import init_project, project_paths

        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.email", "dev@example.com"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.name", "Dev"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=tmp_path, check=True)
        (tmp_path / "x").write_text("x")
        subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-qm", "i"], cwd=tmp_path, check=True)
        init_project(tmp_path)
        paths = project_paths(tmp_path)
        paths.ignore.write_text("safe.txt\n../../etc/passwd\n*.log\n", encoding="utf-8")
        patterns = load_ignore_patterns(tmp_path)
        assert "../../etc/passwd" not in patterns
        assert "safe.txt" in patterns
        assert "*.log" in patterns
