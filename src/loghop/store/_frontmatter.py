import dataclasses
import json
from pathlib import Path
from typing import Any

import yaml

from loghop.logging import get_logger
from loghop.store._io import project_lock, safe_read_text

_LOGGER = get_logger()


def _frontmatter_end_index(lines: list[str]) -> int | None:
    if not lines or lines[0].strip() != "---":
        return None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            return idx
    return -1


def parse_frontmatter_text(md_path: Path) -> tuple[dict[str, Any], list[str]]:
    """Parse a markdown file with YAML/JSON frontmatter.

    Returns (metadata_dict, all_lines).
    """
    text = safe_read_text(md_path)
    lines = text.splitlines()
    end_idx = _frontmatter_end_index(lines)
    if end_idx is None or end_idx < 0:
        return {}, lines

    # Integrity check: verify signature if present.
    from loghop.store._integrity import check_signature_warn

    # Derive project root from the file path.
    # .loghop/{handoffs,sessions}/*.md → parent.parent is the .loghop dir.
    # parent of .loghop is the project root.
    try:
        dot_dir = md_path.parent.parent
        if dot_dir.name == ".loghop":
            project_root = dot_dir.parent
            fm_text = "\n".join(lines[1:end_idx])
            body_text = "\n".join(lines[end_idx + 1 :])
            check_signature_warn(project_root, fm_text, md_path, body_text)
    except (ValueError, OSError):
        pass  # Non-critical; don't block parsing.

    meta = parse_metadata_lines(lines[1:end_idx])
    return meta, lines


def parse_metadata_lines(lines: list[str]) -> dict[str, Any]:
    """Parse frontmatter content lines (between --- delimiters) as JSON or YAML."""
    joined = "\n".join(lines).strip()
    if joined.startswith("{"):
        try:
            raw = json.loads(joined)
        except json.JSONDecodeError:
            return {}
        if isinstance(raw, dict):
            return {str(k): v for k, v in raw.items()}
        return {}
    try:
        parsed = yaml.safe_load(joined)
        if isinstance(parsed, dict):
            return {str(k): v for k, v in parsed.items()}
    except Exception:  # noqa: BLE001
        _LOGGER.debug("YAML frontmatter parse failed", exc_info=True)
    return {}


def meta_to_dataclass(meta: dict[str, Any], dataclass_type: type) -> dict[str, Any]:
    """Build kwargs suitable for a dataclass constructor from a metadata dict."""
    kwargs: dict[str, Any] = {}
    for f in dataclasses.fields(dataclass_type):
        if f.name in meta:
            kwargs[f.name] = meta[f.name]
    return kwargs


def rewrite_frontmatter(
    md_path: Path,
    updates: dict[str, Any],
) -> dict[str, Any]:
    """Parse frontmatter from *md_path*, merge *updates*, and rewrite the file.

    Returns the merged metadata dict.  Raises ``ValueError`` if the file has
    no parseable frontmatter.
    """
    from loghop.store._io import atomic_write_private_text

    all_lines = safe_read_text(md_path).splitlines()
    end_idx = _frontmatter_end_index(all_lines)
    if end_idx is None:
        raise ValueError(f"file has no frontmatter: {md_path}")
    if end_idx < 0:
        raise ValueError(f"file has unterminated frontmatter: {md_path}")

    meta_lines = all_lines[1:end_idx]
    meta = parse_metadata_lines(meta_lines)
    if any(line.strip() for line in meta_lines) and not meta:
        raise ValueError(f"file has malformed frontmatter: {md_path}")

    meta.update({k: v for k, v in updates.items() if v is not None})
    meta.pop("_signature", None)

    new_fm = yaml.dump(meta, sort_keys=True, allow_unicode=True, default_flow_style=False).rstrip()
    body = all_lines[end_idx + 1 :]
    unsigned_markdown = "\n".join(["---", new_fm, "---", *body]).rstrip() + "\n"

    # Embed integrity signature for handoff/session files inside .loghop/.
    try:
        dot_dir = md_path.parent.parent
        if dot_dir.name == ".loghop":
            from loghop.store._integrity import sign_markdown

            project_root = dot_dir.parent
            unsigned_markdown = sign_markdown(project_root, unsigned_markdown)
    except (ValueError, OSError):
        pass

    lock_path = md_path.parent.parent / ".lock"
    with project_lock(lock_path):
        atomic_write_private_text(md_path, unsigned_markdown)
    return meta
