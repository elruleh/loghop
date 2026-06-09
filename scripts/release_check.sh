#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

mode="${1:-all}"

run_qa() {
  local audit_requirements
  audit_requirements="$(mktemp)"
  trap 'rm -f "$audit_requirements"' RETURN

  uv run --all-extras ruff format --check src tests
  uv run --all-extras ruff check src tests scripts
  uv run --all-extras mypy src
  uv run --all-extras bandit -c .bandit.yml -r src/loghop
  uv export --all-extras --dev --format requirements-txt --no-emit-project --no-hashes > "$audit_requirements"
  uv run --all-extras pip-audit -r "$audit_requirements" --desc
  uv run --all-extras pytest --cov=loghop --cov-report=term-missing --cov-fail-under=80
  # Slow TUI tests run on every release, but the developer inner loop can
  # skip them with ``pytest -m "not slow"``.
  echo "Release QA gates passed (including slow TUI suite)."
}

run_build() {
  rm -rf build dist src/loghop.egg-info
  uv run --all-extras python -m build
  uv run --all-extras twine check dist/*
}

run_artifact_smoke() {
  local wheel
  local original_home original_path
  wheel="$(echo dist/*.whl)"
  original_home="${HOME:-}"
  original_path="$PATH"

  cleanup_smoke_envs() {
    rm -rf .venv-wheel .venv-wheel-tui .venv-sdist .venv-pipx .pipx .uv-home
  }
  trap cleanup_smoke_envs RETURN

  cleanup_smoke_envs

  python3 -m venv .venv-wheel
  .venv-wheel/bin/python -m pip install "$wheel"
  python3 scripts/smoke_release.py \
    --loghop-bin .venv-wheel/bin/loghop \
    --python-bin .venv-wheel/bin/python

  python3 -m venv .venv-wheel-tui
  .venv-wheel-tui/bin/python -m pip install "${wheel}[tui]"
  python3 scripts/smoke_release.py \
    --loghop-bin .venv-wheel-tui/bin/loghop \
    --python-bin .venv-wheel-tui/bin/python \
    --expect-tui

  python3 -m venv .venv-sdist
  .venv-sdist/bin/python -m pip install dist/*.tar.gz
  python3 scripts/smoke_release.py \
    --loghop-bin .venv-sdist/bin/loghop \
    --python-bin .venv-sdist/bin/python

  python3 -m venv .venv-pipx
  .venv-pipx/bin/python -m pip install pipx
  export PIPX_HOME="$ROOT_DIR/.pipx/home"
  export PIPX_BIN_DIR="$ROOT_DIR/.pipx/bin"
  .venv-pipx/bin/python -m pipx install "$wheel"
  python3 scripts/smoke_release.py --loghop-bin "$PIPX_BIN_DIR/loghop"
  rm -rf "$PIPX_HOME" "$PIPX_BIN_DIR"

  export HOME="$ROOT_DIR/.uv-home"
  rm -rf "$HOME"
  mkdir -p "$HOME"
  export PATH="$HOME/.local/bin:$PATH"
  uv tool install "$wheel"
  python3 scripts/smoke_release.py --loghop-bin "$HOME/.local/bin/loghop"
  rm -rf "$HOME"
  export HOME="$original_home"
  export PATH="$original_path"

  uv tool run --refresh --from "$wheel" loghop --version
  uv tool run --refresh --from "$wheel" loghop --help
}

case "$mode" in
  qa)
    run_qa
    ;;
  build)
    run_build
    ;;
  artifacts)
    run_build
    run_artifact_smoke
    ;;
  all)
    run_qa
    run_build
    run_artifact_smoke
    ;;
  *)
    echo "usage: scripts/release_check.sh [qa|build|artifacts|all]" >&2
    exit 2
    ;;
esac
