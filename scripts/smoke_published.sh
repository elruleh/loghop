#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

version=""
repository=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --version)
      version="$2"
      shift 2
      ;;
    --repository)
      repository="$2"
      shift 2
      ;;
    *)
      echo "unknown arg: $1" >&2
      exit 2
      ;;
  esac
done

if [[ -z "$version" || -z "$repository" ]]; then
  echo "usage: scripts/smoke_published.sh --version X.Y.Z --repository {testpypi|pypi}" >&2
  exit 2
fi

if [[ "$repository" == "testpypi" ]]; then
  pip_args=(--index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple)
  uv_args=(--default-index https://test.pypi.org/simple/ --index https://pypi.org/simple)
  pipx_pip_args="--index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple"
else
  pip_args=()
  uv_args=()
  pipx_pip_args=""
fi

rm -rf .venv-published .venv-published-tui .pipx .uv-home

python3 -m venv .venv-published
. .venv-published/bin/activate
for attempt in 1 2 3 4 5; do
  if pip install "${pip_args[@]}" "loghop==${version}"; then
    break
  fi
  if [[ "$attempt" -eq 5 ]]; then
    exit 1
  fi
  sleep 15
done
python3 scripts/smoke_release.py \
  --loghop-bin .venv-published/bin/loghop \
  --python-bin .venv-published/bin/python
deactivate

python3 -m venv .venv-published-tui
. .venv-published-tui/bin/activate
for attempt in 1 2 3 4 5; do
  if pip install "${pip_args[@]}" "loghop[tui]==${version}"; then
    break
  fi
  if [[ "$attempt" -eq 5 ]]; then
    exit 1
  fi
  sleep 15
done
python3 scripts/smoke_release.py \
  --loghop-bin .venv-published-tui/bin/loghop \
  --python-bin .venv-published-tui/bin/python \
  --expect-tui
deactivate

python3 -m venv .venv-pipx
. .venv-pipx/bin/activate
pip install pipx
export PIPX_HOME="$ROOT_DIR/.pipx/home"
export PIPX_BIN_DIR="$ROOT_DIR/.pipx/bin"
for attempt in 1 2 3 4 5; do
  if [[ -n "$pipx_pip_args" ]]; then
    python3 -m pipx install --pip-args="$pipx_pip_args" "loghop==${version}"
  else
    python3 -m pipx install "loghop==${version}"
  fi
  if [[ -x "$PIPX_BIN_DIR/loghop" ]]; then
    break
  fi
  if [[ "$attempt" -eq 5 ]]; then
    exit 1
  fi
  sleep 15
done
python3 scripts/smoke_release.py --loghop-bin "$PIPX_BIN_DIR/loghop"
deactivate
rm -rf .venv-pipx

export HOME="$ROOT_DIR/.uv-home"
mkdir -p "$HOME"
export PATH="$HOME/.local/bin:$PATH"
for attempt in 1 2 3 4 5; do
  if uv tool install "${uv_args[@]}" "loghop==${version}"; then
    break
  fi
  if [[ "$attempt" -eq 5 ]]; then
    exit 1
  fi
  sleep 15
done
python3 scripts/smoke_release.py --loghop-bin "$HOME/.local/bin/loghop"
