import json
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

from loghop.transcripts._base import Turn
from loghop.transcripts._drift import DriftObserver

# Top-level ``type`` values we expect to see in Claude's JSONL transcripts.
# "user" and "assistant" carry turns; the rest are knowingly ignored. Any
# value outside this set is reported as schema drift.
_KNOWN_TOP_TYPES = frozenset(
    {
        "user",
        "assistant",
        "system",
        "summary",
        "tool_use",  # standalone meta records (not block-embedded)
        "tool_result",
        "permission-mode",
        "attachment",
        "last-prompt",
        "ai-title",
    }
)

# Content-block ``type`` values inside an assistant message.
_KNOWN_BLOCK_TYPES = frozenset(
    {
        "text",
        "tool_use",
        "tool_result",
        "thinking",  # extended-thinking blocks; we drop them by design
        "image",
    }
)


def _claude_projects_root() -> Path:
    return Path.home() / ".claude" / "projects"


def _slug_for_cwd(cwd: Path) -> str:
    return str(cwd.resolve()).replace("/", "-")


class ClaudeTranscriptReader:
    provider = "claude"

    def candidate_roots(self, cwd: Path) -> list[Path]:
        return [_claude_projects_root() / _slug_for_cwd(cwd)]

    def find_latest(self, cwd: Path, since: datetime) -> Path | None:
        candidates = self.find_candidates(cwd, since)
        return candidates[0] if candidates else None

    def find_candidates(self, cwd: Path, since: datetime) -> list[Path]:
        root = _claude_projects_root() / _slug_for_cwd(cwd)
        if not root.is_dir():
            return []
        since_ts = since.timestamp()
        candidates: list[tuple[float, Path]] = []
        for path in root.glob("*.jsonl"):
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            if mtime < since_ts:
                continue
            candidates.append((mtime, path))
        candidates.sort(key=lambda item: item[0], reverse=True)
        return [path for _mtime, path in candidates]

    def parse(self, path: Path) -> Iterable[Turn]:
        observer = DriftObserver(
            provider=self.provider,
            path=path,
            known_top_types=_KNOWN_TOP_TYPES,
            known_block_types=_KNOWN_BLOCK_TYPES,
        )
        try:
            with path.open("r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    raw = line.strip()
                    if not raw:
                        continue
                    try:
                        entry = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    observer.observe_top(entry.get("type") if isinstance(entry, dict) else None)
                    if isinstance(entry, dict):
                        message = entry.get("message")
                        if isinstance(message, dict):
                            content = message.get("content")
                            if isinstance(content, list):
                                observer.observe_blocks(
                                    block.get("type")
                                    for block in content
                                    if isinstance(block, dict)
                                )
                    if isinstance(entry, dict):
                        turn = _turn_from_entry(entry)
                        if turn is not None:
                            yield turn
        except OSError:
            return
        finally:
            observer.report()


def _turn_from_entry(entry: dict[str, Any]) -> Turn | None:
    kind = entry.get("type")
    if kind not in ("user", "assistant"):
        return None
    message = entry.get("message") or {}
    if not isinstance(message, dict):
        return None
    role = message.get("role") or kind
    if role not in ("user", "assistant"):
        return None
    content = message.get("content")
    text = _extract_text(content)
    if not text:
        return None
    ts = str(entry.get("timestamp") or "")
    return Turn(role=role, text=text, ts=ts)


def _extract_text(content: object) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
                continue
            if not isinstance(block, dict):
                continue
            parts.append(_extract_block_text(block))
        return "\n".join(p for p in parts if p)
    return ""


def _extract_block_text(block: dict[str, Any]) -> str:
    block_type = block.get("type")
    if block_type == "text":
        value = block.get("text")
        return value if isinstance(value, str) else ""
    if block_type == "tool_use":
        return f"[tool_use: {block.get('name')}]"
    if block_type == "tool_result":
        value = block.get("content")
        if isinstance(value, str):
            return f"[tool_result] {value}"
        if isinstance(value, list):
            return f"[tool_result] {_extract_text(value)}"
    return ""
