import json
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

from loghop.logging import get_logger
from loghop.transcripts._base import Turn
from loghop.transcripts._drift import DriftObserver

_LOGGER = get_logger()

# Top-level ``type`` values seen in Codex rollout JSONL files. The parser
# only consumes ``response_item`` for turn extraction; everything else is
# knowingly ignored. Anything outside this set flags schema drift.
_KNOWN_TOP_TYPES = frozenset(
    {
        "session_meta",
        "response_item",
        "event",
        "event_msg",
        "turn_context",
        "tool_call",
        "tool_result",
    }
)

# Content-block ``type`` values inside response_item messages.
_KNOWN_BLOCK_TYPES = frozenset(
    {
        "input_text",
        "output_text",
        "text",
        "image",
        "tool_use",
        "tool_result",
    }
)


def _codex_sessions_root() -> Path:
    return Path.home() / ".codex" / "sessions"


class CodexTranscriptReader:
    provider = "codex"

    def candidate_roots(self, _cwd: Path) -> list[Path]:
        return [_codex_sessions_root()]

    def find_latest(self, cwd: Path, since: datetime) -> Path | None:
        candidates = self.find_candidates(cwd, since)
        return candidates[0] if candidates else None

    def find_candidates(self, cwd: Path, since: datetime) -> list[Path]:
        root = _codex_sessions_root()
        if not root.is_dir():
            return []
        since_ts = since.timestamp()
        cwd_str = str(cwd.resolve())
        candidates: list[tuple[float, Path]] = []
        for path in root.rglob("rollout-*.jsonl"):
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            if mtime < since_ts:
                continue
            if not _matches_cwd(path, cwd_str):
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
                        payload = entry.get("payload")
                        if isinstance(payload, dict):
                            content = payload.get("content")
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


_MATCH_CWD_SCAN_LIMIT = 32


def _matches_cwd(path: Path, cwd_str: str) -> bool:
    """Return True iff the rollout's session_meta cwd matches.

    Tolerates malformed lines and non-session_meta lines: scans up to the
    first ``_MATCH_CWD_SCAN_LIMIT`` valid JSON lines looking for the meta
    record. A single corrupted line earlier in the file no longer rejects
    the whole transcript.

    Logs at INFO when a rollout is rejected so operators debugging
    "why didn't loghop pick up my session?" have a breadcrumb.
    """
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            scanned = 0
            for line in f:
                if scanned >= _MATCH_CWD_SCAN_LIMIT:
                    _LOGGER.info(
                        "codex rollout rejected: session_meta not in first %d lines",
                        _MATCH_CWD_SCAN_LIMIT,
                        extra={"component": "transcripts.codex", "path": str(path)},
                    )
                    return False
                raw = line.strip()
                if not raw:
                    continue
                try:
                    entry = json.loads(raw)
                except json.JSONDecodeError:
                    scanned += 1
                    continue
                scanned += 1
                if entry.get("type") != "session_meta":
                    continue
                payload = entry.get("payload") or {}
                rollout_cwd = str(payload.get("cwd") or "")
                if rollout_cwd == cwd_str:
                    return True
                _LOGGER.info(
                    "codex rollout rejected: cwd mismatch",
                    extra={
                        "component": "transcripts.codex",
                        "path": str(path),
                        "rollout_cwd": rollout_cwd,
                        "expected_cwd": cwd_str,
                    },
                )
                return False
    except OSError as exc:
        _LOGGER.warning(
            "codex rollout could not be read",
            extra={"component": "transcripts.codex", "path": str(path), "error": str(exc)},
        )
        return False
    return False


def _turn_from_entry(entry: dict[str, Any]) -> Turn | None:
    if entry.get("type") != "response_item":
        return None
    payload = entry.get("payload") or {}
    if not isinstance(payload, dict):
        return None
    payload_type = payload.get("type")
    if payload_type not in ("message", "agent_message", "user_message"):
        return None
    role = payload.get("role")
    if role is None:
        role = _role_for_payload_type(str(payload_type))
    if role not in ("user", "assistant"):
        return None
    text = _extract_text(payload.get("content") or payload.get("message"))
    if not text:
        return None
    ts = str(entry.get("timestamp") or "")
    return Turn(role=role, text=text, ts=ts)


def _role_for_payload_type(payload_type: str) -> str:
    if payload_type == "agent_message":
        return "assistant"
    if payload_type == "user_message":
        return "user"
    return ""


def _extract_text(content: object) -> str:
    """Flatten a Codex content array into text, including tool I/O.

    Mirrors the Claude reader so summaries/heuristics see the same shape
    regardless of provider. tool_use → ``[tool_use: name]``, tool_result →
    ``[tool_result] <content>`` (recurses for nested block lists).
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
            continue
        if not isinstance(block, dict):
            continue
        parts.append(_extract_codex_block(block))
    return "\n".join(p for p in parts if p)


def _extract_codex_block(block: dict[str, Any]) -> str:
    block_type = block.get("type")
    if block_type in ("input_text", "output_text", "text"):
        value = block.get("text")
        return value if isinstance(value, str) else ""
    if block_type == "tool_use":
        name = block.get("name") or block.get("tool") or "?"
        return f"[tool_use: {name}]"
    if block_type == "tool_result":
        value = block.get("content")
        if isinstance(value, str):
            return f"[tool_result] {value}"
        if isinstance(value, list):
            return f"[tool_result] {_extract_text(value)}"
    return ""
