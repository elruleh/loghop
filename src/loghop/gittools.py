from __future__ import annotations

import os
import subprocess  # nosec B404
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

_GIT_ENV_DENYLIST = {
    "GIT_EXTERNAL_DIFF",
    "GIT_PAGER",
    "GIT_CONFIG",
    "GIT_CONFIG_GLOBAL",
    "GIT_CONFIG_SYSTEM",
    "GIT_CONFIG_NOSYSTEM",
}


@dataclass
class GitSnapshot:
    git_root: str | None
    branch: str | None
    head: str | None
    default_branch: str | None
    dirty: bool
    staged: list[str]
    unstaged: list[str]
    untracked: list[str]
    changed_files: list[str]
    diff_stat: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class _V2StatusEntry:
    xy: str
    path: str
    orig_path: str | None = None


@dataclass
class _ParsedStatus:
    branch: str | None
    head: str | None
    upstream: str | None
    entries: list[_V2StatusEntry]


def _run_git(cwd: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(  # nosec
            [
                "git",
                "--no-pager",
                "-c",
                "core.fsmonitor=false",
                "-c",
                "diff.external=",
                *args,
            ],
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
            env=_safe_git_env(),
        )
    except FileNotFoundError as exc:
        raise ValueError("git is not installed or not found in PATH") from exc


def _safe_git_env() -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in _GIT_ENV_DENYLIST and not key.startswith("GIT_CONFIG_")
    }
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def _parse_v2_status(raw: str) -> _ParsedStatus:
    branch: str | None = None
    head: str | None = None
    upstream: str | None = None
    entries: list[_V2StatusEntry] = []

    parts = raw.split("\0")
    i = 0
    while i < len(parts):
        part = parts[i]
        if not part:
            i += 1
            continue
        if part.startswith("# branch.head "):
            val = part[len("# branch.head ") :]
            branch = val if val != "(detached)" else None
        elif part.startswith("# branch.oid "):
            oid = part[len("# branch.oid ") :]
            head = oid if oid != "(initial)" else None
            if head and len(head) > 10:  # noqa: PLR2004
                head = head[:10]
        elif part.startswith("# branch.upstream "):
            upstream = part[len("# branch.upstream ") :]
        elif part.startswith("1 ") or part.startswith("u "):
            fields = part.split()
            xy = fields[1]
            path = fields[-1]
            entries.append(_V2StatusEntry(xy=xy, path=path))
        elif part.startswith("2 "):
            fields = part.split()
            xy = fields[1]
            path = fields[-1]
            i += 1
            orig = parts[i] if i < len(parts) else None
            entries.append(_V2StatusEntry(xy=xy, path=path, orig_path=orig))
        elif part.startswith("? "):
            entries.append(_V2StatusEntry(xy="??", path=part[2:]))
        elif part.startswith("! "):
            entries.append(_V2StatusEntry(xy="!!", path=part[2:]))
        i += 1

    return _ParsedStatus(branch=branch, head=head, upstream=upstream, entries=entries)


def _sanitize_path(path: str) -> str:
    if not path or "\0" in path:
        raise ValueError(f"invalid path: {path!r}")
    if any(c in path for c in ("\t", "\n", "\r")):
        raise ValueError(f"invalid path: control characters in {path!r}")
    if path.startswith("-"):
        raise ValueError(f"path looks like a flag: {path!r}")
    return path


class GitRepo:
    """Encapsulates a Git repository with cached, consolidated queries.

    Uses ``git status --porcelain=v2 --branch`` to fetch branch, HEAD SHA,
    upstream, and file status in a single subprocess call.  Results are
    cached for *cache_ttl* seconds (default 2 s).
    """

    def __init__(self, root: Path, *, cache_ttl: float = 2.0) -> None:
        self.root = root
        self._cache_ttl = cache_ttl
        self._cached_status: _ParsedStatus | None = None
        self._cache_time: float = 0.0

    @classmethod
    def from_cwd(cls, cwd: Path, **kwargs: Any) -> GitRepo | None:
        """Resolve the git root from *cwd*; return ``None`` if not a repo or git is not installed."""
        try:
            result = _run_git(cwd, ["rev-parse", "--show-toplevel"])
        except ValueError:
            return None
        if result.returncode != 0:
            return None
        root = Path(result.stdout.strip())
        try:
            bare_check = _run_git(root, ["rev-parse", "--is-bare-repository"])
        except ValueError:
            return None
        if bare_check.returncode == 0 and bare_check.stdout.strip() == "true":
            return None
        return cls(root, **kwargs)

    def snapshot(self) -> GitSnapshot:
        """Return a full repo snapshot, using cached data when fresh."""
        status = self._status()
        branch: str | None = status.branch
        if branch is None and status.head is not None:
            branch = "DETACHED"

        staged: list[str] = []
        unstaged: list[str] = []
        untracked: list[str] = []
        changed: list[str] = []
        for entry in status.entries:
            if entry.xy == "??":
                untracked.append(entry.path)
            elif entry.xy == "!!":
                continue
            else:
                if entry.xy[0] not in {" ", ".", "?"}:
                    staged.append(entry.path)
                if entry.xy[1] not in {" ", ".", "?"}:
                    unstaged.append(entry.path)
            if entry.path and entry.path not in changed:
                changed.append(entry.path)

        dirty = bool(changed)
        diff_stat = self._diff_stat() if dirty else ""
        default = self._resolve_default_branch(status)

        return GitSnapshot(
            git_root=str(self.root),
            branch=branch,
            head=status.head,
            default_branch=default,
            dirty=dirty,
            staged=staged,
            unstaged=unstaged,
            untracked=untracked,
            changed_files=changed,
            diff_stat=diff_stat,
        )

    def diff_for_files(self, files: list[str], *, max_lines: int = 200) -> str:
        """Patch for *files*, reusing cached status entries."""
        if not files:
            return ""
        status = self._status()
        entry_map = {e.path: e for e in status.entries}
        chunks: list[str] = []
        line_budget = max_lines
        for raw_path in files:
            if line_budget <= 0:
                break
            path = _sanitize_path(raw_path)
            entry = entry_map.get(path)
            seen: set[str] = set()
            for args in self._build_diff_specs(path, entry):
                result = _run_git(self.root, args)
                if result.returncode not in {0, 1} or not result.stdout.strip():
                    continue
                if result.stdout in seen:
                    continue
                seen.add(result.stdout)
                file_lines = result.stdout.splitlines()
                if len(file_lines) > line_budget:
                    file_lines = file_lines[:line_budget]
                    file_lines.append("... patch truncated ...")
                chunks.append("\n".join(file_lines))
                line_budget -= len(file_lines)
                if line_budget <= 0:
                    break
        return "\n\n".join(chunks)

    def invalidate(self) -> None:
        """Force fresh data on the next query."""
        self._cached_status = None
        self._cache_time = 0.0

    def _status(self) -> _ParsedStatus:
        now = time.monotonic()
        if self._cached_status is not None and (now - self._cache_time) < self._cache_ttl:
            return self._cached_status
        result = _run_git(self.root, ["status", "--porcelain=v2", "--branch", "-z"])
        parsed = _parse_v2_status(result.stdout)
        self._cached_status = parsed
        self._cache_time = time.monotonic()
        return parsed

    def _diff_stat(self) -> str:
        return _run_git(self.root, ["diff", "--stat", "HEAD"]).stdout.strip()

    def _resolve_default_branch(self, status: _ParsedStatus) -> str | None:
        if status.upstream and "/" in status.upstream:
            return status.upstream.rsplit("/", 1)[-1]
        if status.branch in ("main", "master"):
            return status.branch
        return None

    def _build_diff_specs(self, path: str, entry: _V2StatusEntry | None) -> list[list[str]]:
        if entry is not None and entry.xy == "??":
            return [
                ["diff", "--no-ext-diff", "--no-textconv", "--no-index", "--", os.devnull, path]
            ]
        pathspec = [path]
        if entry is not None and entry.orig_path is not None:
            pathspec = [entry.orig_path, path]
        return [
            ["diff", "--no-ext-diff", "--no-textconv", "--unified=1", "--", *pathspec],
            [
                "diff",
                "--cached",
                "--no-ext-diff",
                "--no-textconv",
                "--unified=1",
                "--find-renames",
                "--",
                *pathspec,
            ],
        ]
