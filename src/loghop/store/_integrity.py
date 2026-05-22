"""Lightweight integrity verification for loghop artifacts.

Computes an HMAC over handoff and session markdown files using a private
per-project key.  The HMAC covers the frontmatter (minus the ``_signature``
field) and the markdown body so both metadata and prompt context tampering are
detected.

The HMAC is stored as a ``_signature`` field in the YAML frontmatter and
verified on read.  A mismatch produces a warning but does not block operation —
this is defense-in-depth, not a security gate.
"""

import hashlib
import hmac
import secrets
from pathlib import Path

from loghop.logging import get_logger
from loghop.store._io import atomic_write_private_text, safe_read_text

_LOGGER = get_logger()
_INTEGRITY_KEY_BYTES = 32


def _derive_key(project_root: Path) -> bytes:
    """Return the per-project HMAC key, creating it on first use."""
    key_path = project_root / ".loghop" / "integrity.key"
    if key_path.is_symlink():
        raise ValueError("refusing to use symlinked integrity key")
    if key_path.exists():
        raw = safe_read_text(key_path).strip()
        try:
            key = bytes.fromhex(raw)
        except ValueError as exc:
            raise ValueError("invalid integrity key") from exc
        if len(key) != _INTEGRITY_KEY_BYTES:
            raise ValueError("invalid integrity key length")
        return key
    key = secrets.token_bytes(_INTEGRITY_KEY_BYTES)
    atomic_write_private_text(key_path, key.hex() + "\n")
    return key


def _clean_frontmatter_lines(frontmatter_text: str) -> list[str]:
    return [line for line in frontmatter_text.splitlines() if not line.startswith("_signature:")]


def _signature_payload(frontmatter_text: str, body_text: str = "") -> bytes:
    clean_frontmatter = "\n".join(_clean_frontmatter_lines(frontmatter_text))
    if body_text:
        return f"{clean_frontmatter}\n---\n{body_text}".encode()
    return clean_frontmatter.encode()


def compute_signature(project_root: Path, frontmatter_text: str, body_text: str = "") -> str:
    """Return an HMAC-SHA256 hex digest for an artifact payload."""
    return hmac.new(
        _derive_key(project_root),
        _signature_payload(frontmatter_text, body_text),
        hashlib.sha256,
    ).hexdigest()[:16]


def embed_signature(project_root: Path, frontmatter_text: str, body_text: str = "") -> str:
    """Append a ``_signature`` field to frontmatter and return it.

    Re-signing is idempotent: an existing ``_signature`` field is removed before
    computing the new value.  When *body_text* is supplied, the signature covers
    both metadata and body content.
    """
    clean_lines = _clean_frontmatter_lines(frontmatter_text)
    sig = compute_signature(project_root, "\n".join(clean_lines), body_text)
    clean_lines.append(f"_signature: {sig}")
    return "\n".join(clean_lines)


def verify_signature(project_root: Path, frontmatter_text: str, body_text: str = "") -> bool:
    """Return True if the embedded ``_signature`` matches the computed one.

    Missing signatures are treated as valid for backward compatibility.  Legacy
    signatures that covered only frontmatter are also accepted; newly written
    artifacts include *body_text* in the signature.
    """
    embedded: str | None = None
    clean_lines: list[str] = []
    for line in frontmatter_text.splitlines():
        if line.startswith("_signature:"):
            embedded = line.split(":", 1)[1].strip()
        else:
            clean_lines.append(line)
    if embedded is None:
        return True
    clean_frontmatter = "\n".join(clean_lines)
    expected = compute_signature(project_root, clean_frontmatter, body_text)
    if hmac.compare_digest(embedded, expected):
        return True
    if body_text:
        legacy_expected = compute_signature(project_root, clean_frontmatter)
        return hmac.compare_digest(embedded, legacy_expected)
    return False


def sign_markdown(project_root: Path, markdown: str) -> str:
    """Return *markdown* with a full-artifact integrity signature embedded."""
    lines = markdown.splitlines()
    if not lines or lines[0].strip() != "---":
        return markdown
    end_idx = -1
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end_idx = idx
            break
    if end_idx < 0:
        return markdown
    frontmatter_text = "\n".join(lines[1:end_idx])
    body_lines = lines[end_idx + 1 :]
    body_text = "\n".join(body_lines)
    signed_frontmatter = embed_signature(project_root, frontmatter_text, body_text)
    signed = "\n".join(["---", signed_frontmatter, "---", *body_lines])
    return signed + ("\n" if markdown.endswith("\n") else "")


def check_signature_warn(
    project_root: Path,
    frontmatter_text: str,
    path: Path,
    body_text: str = "",
) -> None:
    """Log a warning if the artifact signature does not match."""
    if not verify_signature(project_root, frontmatter_text, body_text):
        _LOGGER.warning(
            "artifact signature mismatch — file may have been tampered with",
            extra={
                "component": "integrity",
                "path": str(path),
            },
        )
