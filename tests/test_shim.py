from __future__ import annotations

import stat
from pathlib import Path

import pytest

from loghop.install._shim import (
    _is_loghop_shim,
    _shim_body,
    codex_shim_installed,
    install_codex_shim,
)


class TestShimBody:
    def test_contains_loghop_marker(self) -> None:
        body = _shim_body("codex", "/usr/local/bin/codex")
        assert "Managed by loghop install-shims" in body

    def test_contains_wrap_command(self) -> None:
        body = _shim_body("codex", "/usr/local/bin/codex")
        assert "loghop wrap codex" in body

    def test_exports_real_path(self) -> None:
        body = _shim_body("codex", "/usr/local/bin/codex")
        assert "LOGHOP_REAL_CODEX" in body

    def test_is_shell_script(self) -> None:
        body = _shim_body("codex", "/usr/bin/codex")
        assert body.startswith("#!/bin/sh")


class TestIsLoghopShim:
    def test_valid_shim(self, tmp_path: Path) -> None:
        shim = tmp_path / "codex"
        shim.write_text("#!/bin/sh\n# Managed by loghop install-shims\necho hi\n")
        assert _is_loghop_shim(shim) is True

    def test_non_loghop_file(self, tmp_path: Path) -> None:
        shim = tmp_path / "codex"
        shim.write_text("#!/bin/sh\necho 'I am something else'\n")
        assert _is_loghop_shim(shim) is False

    def test_missing_file(self, tmp_path: Path) -> None:
        assert _is_loghop_shim(tmp_path / "nonexistent") is False


class TestCodexShimInstalled:
    def test_not_installed(self, tmp_path: Path) -> None:
        assert codex_shim_installed(prefix=tmp_path, binary="codex") is False

    def test_installed(self, tmp_path: Path) -> None:
        shim = tmp_path / "codex"
        shim.write_text("#!/bin/sh\n# Managed by loghop install-shims\necho hi\n")
        assert codex_shim_installed(prefix=tmp_path, binary="codex") is True

    def test_wrong_binary_name(self, tmp_path: Path) -> None:
        shim = tmp_path / "codex"
        shim.write_text("#!/bin/sh\n# Managed by loghop install-shims\necho hi\n")
        assert codex_shim_installed(prefix=tmp_path, binary="claude") is False


class TestInstallCodexShim:
    def test_install_creates_shim(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        install_dir = tmp_path / "shim"
        install_dir.mkdir()
        real_dir = tmp_path / "real"
        real_dir.mkdir()
        real_codex = real_dir / "codex"
        real_codex.write_text("#!/bin/sh\necho real\n")
        real_codex.chmod(real_codex.stat().st_mode | stat.S_IEXEC)
        monkeypatch.setenv("PATH", f"{install_dir}:{real_dir}")

        result = install_codex_shim(prefix=install_dir, binary="codex")
        assert result.action in ("created", "unchanged", "updated")

    def test_uninstall_removes_shim(self, tmp_path: Path) -> None:
        shim = tmp_path / "codex"
        shim.write_text("#!/bin/sh\n# Managed by loghop install-shims\necho hi\n")
        result = install_codex_shim(prefix=tmp_path, binary="codex", uninstall=True)
        assert result.action == "removed"
        assert not shim.exists()

    def test_uninstall_no_shim(self, tmp_path: Path) -> None:
        result = install_codex_shim(prefix=tmp_path, binary="codex", uninstall=True)
        assert result.action == "unchanged"

    def test_uninstall_non_loghop_file(self, tmp_path: Path) -> None:
        shim = tmp_path / "codex"
        shim.write_text("#!/bin/sh\necho 'not loghop'\n")
        result = install_codex_shim(prefix=tmp_path, binary="codex", uninstall=True)
        assert result.action == "skipped"
        assert shim.exists()

    def test_dry_run_does_not_write(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        install_dir = tmp_path / "shim"
        install_dir.mkdir()
        real_dir = tmp_path / "real"
        real_dir.mkdir()
        real_codex = real_dir / "codex"
        real_codex.write_text("#!/bin/sh\necho real\n")
        real_codex.chmod(real_codex.stat().st_mode | stat.S_IEXEC)
        monkeypatch.setenv("PATH", f"{install_dir}:{real_dir}")
        result = install_codex_shim(prefix=install_dir, binary="codex", dry_run=True)
        assert result.action.startswith("would-")
        assert not (install_dir / "codex").exists()

    def test_idempotent_install(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        install_dir = tmp_path / "shim"
        install_dir.mkdir()
        real_dir = tmp_path / "real"
        real_dir.mkdir()
        real_codex = real_dir / "codex"
        real_codex.write_text("#!/bin/sh\necho real\n")
        real_codex.chmod(real_codex.stat().st_mode | stat.S_IEXEC)
        monkeypatch.setenv("PATH", f"{install_dir}:{real_dir}")
        install_codex_shim(prefix=install_dir, binary="codex")
        result = install_codex_shim(prefix=install_dir, binary="codex")
        assert result.action == "unchanged"

    def test_refuses_overwrite_non_loghop(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        install_dir = tmp_path / "shim"
        install_dir.mkdir()
        (install_dir / "codex").write_text("#!/bin/sh\necho original\n")
        real_dir = tmp_path / "real"
        real_dir.mkdir()
        real_codex = real_dir / "codex"
        real_codex.write_text("#!/bin/sh\necho real\n")
        real_codex.chmod(real_codex.stat().st_mode | stat.S_IEXEC)
        monkeypatch.setenv("PATH", f"{install_dir}:{real_dir}")
        result = install_codex_shim(prefix=install_dir, binary="codex")
        assert result.action == "skipped"
