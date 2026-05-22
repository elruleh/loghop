from __future__ import annotations

import re
from pathlib import Path

from loghop import __version__

_ROOT = Path(__file__).resolve().parents[1]


def _repo_path(*parts: str) -> Path:
    return _ROOT.joinpath(*parts)


def test_readme_local_image_assets_exist() -> None:
    readme = _repo_path("README.md").read_text(encoding="utf-8")
    paths = re.findall(r'<img[^>]+src="([^"]+)"', readme) + re.findall(
        r"!\[[^\]]*\]\(([^)]+)\)", readme
    )
    local_paths = [path for path in paths if not path.startswith("http")]
    assert local_paths
    missing = [path for path in local_paths if not _repo_path(path).exists()]
    assert not missing


def test_smoke_release_uses_supported_install_commands() -> None:
    body = _repo_path("scripts", "smoke_release.py").read_text(encoding="utf-8")
    assert '"install-hooks", "--claude"' not in body
    assert '"install-hooks", "--scope", "project", "--claude"' not in body


def test_release_check_audits_exported_requirements_without_editable_project() -> None:
    body = _repo_path("scripts", "release_check.sh").read_text(encoding="utf-8")
    assert "uv export --all-extras --dev --format requirements-txt --no-emit-project" in body
    assert "pip-audit -r" in body


def test_release_check_uses_venv_local_pip_for_artifact_installs() -> None:
    body = _repo_path("scripts", "release_check.sh").read_text(encoding="utf-8")
    assert '\n  pip install "$wheel"' not in body
    assert '\n  pip install "${wheel}[tui]"' not in body
    assert "\n  pip install dist/*.tar.gz" not in body
    assert "\n  pip install pipx" not in body
    assert '.venv-wheel/bin/python -m pip install "$wheel"' in body
    assert '.venv-wheel-tui/bin/python -m pip install "${wheel}[tui]"' in body
    assert ".venv-sdist/bin/python -m pip install dist/*.tar.gz" in body
    assert ".venv-pipx/bin/python -m pip install pipx" in body


def test_operations_doc_uses_supported_manual_commands() -> None:
    body = _repo_path("docs", "operations.md").read_text(encoding="utf-8")
    assert "loghop install-hooks --claude" not in body
    assert "loghop install-hooks --scope project --claude" not in body


def test_security_supported_versions_match_current_release() -> None:
    body = _repo_path("SECURITY.md").read_text(encoding="utf-8")
    major, minor, _patch = __version__.split(".")
    assert f"| {major}.{minor}.x   | Yes" in body


def test_changelog_has_single_current_version_heading() -> None:
    body = _repo_path("CHANGELOG.md").read_text(encoding="utf-8")
    assert body.count(f"## [{__version__}]") == 1
