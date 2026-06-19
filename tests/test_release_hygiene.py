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


def test_codeowners_uses_real_maintainer_handle() -> None:
    body = _repo_path(".github", "CODEOWNERS").read_text(encoding="utf-8")
    assert "@elruleh" in body
    assert "@raul" not in body


def test_contributing_links_to_issue_chooser_not_deleted_markdown_templates() -> None:
    body = _repo_path("CONTRIBUTING.md").read_text(encoding="utf-8")
    assert ".github/ISSUE_TEMPLATE/bug_report.md" not in body
    assert ".github/ISSUE_TEMPLATE/feature_request.md" not in body
    assert "https://github.com/elruleh/loghop/issues/new/choose" in body


def test_mailmap_normalizes_maintainer_identity() -> None:
    body = _repo_path(".mailmap").read_text(encoding="utf-8")
    # Old personal email must collapse to the canonical identity.
    assert "Ruleh <ruleh@proton.me>" in body
    assert "<raul90@gmail.com>" in body
    # The raw personal email must not appear in a non-mapped form.
    raw = body.count("raul90@gmail.com")
    mapped = body.count("<raul90@gmail.com>")
    assert raw == mapped, (
        f"raul90@gmail.com appears {raw}x but only {mapped}x inside <>; "
        "expected it only inside a mailmap alias line"
    )


def test_citation_cff_has_no_placeholder_orcid() -> None:
    body = _repo_path("CITATION.cff").read_text(encoding="utf-8")
    assert "0000-0000-0000-0000" not in body
    assert "orcid" not in body.lower()


def test_code_of_conduct_does_not_advertise_unowned_email() -> None:
    body = _repo_path("CODE_OF_CONDUCT.md").read_text(encoding="utf-8")
    assert "support@loghop.dev" not in body


def test_support_documents_smoke_published_script() -> None:
    body = _repo_path("README.md").read_text(encoding="utf-8")
    assert "smoke_published.sh" in body


def test_logo_banner_uses_canonical_filename() -> None:
    readme = _repo_path("README.md").read_text(encoding="utf-8")
    assert 'src="docs/img/logo-banner.svg"' in readme
    assert 'src="docs/img/logo-banner-a.svg"' not in readme


def test_used_by_section_does_not_ship_empty_placeholder() -> None:
    body = _repo_path("README.md").read_text(encoding="utf-8")
    assert "_Add your project here_" not in body


def test_pr_template_removed_stale_fixtures_line() -> None:
    body = _repo_path(".github", "PULL_REQUEST_TEMPLATE.md").read_text(encoding="utf-8")
    assert "tests/fixtures/transcripts/" not in body


def test_precommit_ruff_pin_is_modern() -> None:
    body = _repo_path(".pre-commit-config.yaml").read_text(encoding="utf-8")
    assert "ruff-pre-commit" in body
    # No raw 40-char git SHAs in the ruff pin: keep the config maintainable.
    assert not re.search(r"^\s*rev:\s*[0-9a-f]{40}\s*$", body, flags=re.MULTILINE)


def test_release_process_doc_exists_and_is_substantive() -> None:
    body = _repo_path("docs", "how-to", "release.md").read_text(encoding="utf-8")
    # The doc must exist and address both the audit and the discipline rules.
    assert "Pre-release audit" in body
    assert "Discipline rules" in body
    assert "No standalone hygiene commits" in body


def test_release_process_doc_is_linked_from_contributing() -> None:
    body = _repo_path("CONTRIBUTING.md").read_text(encoding="utf-8")
    # The release-process doc must be discoverable from the contributor guide.
    assert "docs/how-to/release.md" in body
    assert "Release process" in body
