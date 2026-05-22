import fnmatch
from pathlib import Path

from loghop.logging import get_logger
from loghop.store._io import safe_read_text

_LOGGER = get_logger()


def _is_safe_pattern(pattern: str) -> bool:
    if not pattern:
        return False
    if pattern.startswith("/") or pattern.startswith("\\"):
        return False
    if ".." in pattern.split("/"):
        return False
    return not (len(pattern) >= 2 and pattern[1] == ":")  # noqa: PLR2004


def load_ignore_patterns(root: Path) -> list[str]:
    from loghop.store._constants import project_paths

    path = project_paths(root).ignore
    if not path.exists():
        return []
    patterns: list[str] = []
    for raw_line in safe_read_text(path).splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if not _is_safe_pattern(line):
            _LOGGER.warning(
                "ignoring unsafe .loghopignore pattern",
                extra={"component": ".loghopignore", "path": line},
            )
            continue
        patterns.append(line)
    return patterns


def _is_inside(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


def filter_paths(
    paths: list[str], ignore_patterns: list[str], root: Path | None = None
) -> list[str]:
    filtered: list[str] = []
    resolved_root = root.resolve() if root is not None else None
    for path in paths:
        if any(_matches(path, pattern) for pattern in ignore_patterns):
            continue
        if resolved_root is not None:
            candidate = (resolved_root / path).resolve()
            if not _is_inside(resolved_root, candidate):
                continue
        filtered.append(path)
    return filtered


def _matches(path: str, pattern: str) -> bool:
    if pattern.endswith("/"):
        return path == pattern[:-1] or path.startswith(pattern)
    # ``fnmatch`` does not support recursive ``**`` (it treats ``*`` as a
    # single path component).  Expand ``**/`` and ``/**`` so that patterns
    # like ``**/*.secret`` behave the way users expect from .gitignore.
    if "**" in pattern:
        expanded = _expand_doublestar(pattern)
        return any(fnmatch.fnmatch(path, alt) for alt in expanded)
    return fnmatch.fnmatch(path, pattern)


def _expand_doublestar(pattern: str) -> list[str]:
    """Expand ``**`` globs into concrete fnmatch patterns.

    ``**/*.key`` → ``*.key`` and ``*/*.key`` (covers current dir + one level).
    ``secrets/**`` → ``secrets/*`` (one level is enough for fnmatch).
    """
    # Simple heuristic: replace each ``**`` with ``*`` to cover a single
    # directory level, and also produce a version with the ``**`` segment
    # removed entirely (zero levels).
    parts = pattern.split("**")
    alternatives: list[str] = []
    for i in range(len(parts) - 1):
        # Zero-depth (skip the ** segment entirely)
        zero = "".join(parts[:i] + parts[i + 1 :])
        # One-depth (replace ** with *)
        one = "*".join(parts)
        if zero and zero not in alternatives:
            alternatives.append(zero)
        if one and one not in alternatives:
            alternatives.append(one)
    return alternatives or [pattern]
