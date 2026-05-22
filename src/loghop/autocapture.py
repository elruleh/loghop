from __future__ import annotations

from collections import deque
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypedDict

from loghop.logging import get_logger
from loghop.redact import redact_text
from loghop.store._constants import FILE_MODE, project_paths
from loghop.store._io import atomic_stream_to_file
from loghop.transcripts import (
    Turn,
    extract_decisions,
    extract_summary,
    extract_todos,
    find_loghop_block,
    get_reader,
)

if TYPE_CHECKING:
    from loghop.session_lifecycle import SessionContext, TranscriptOptions

_LOGGER = get_logger()
_MAX_CAPTURED_TURNS = 10_000
_MAX_TURN_CHARS = (
    100_000  # ~100 KB per turn; prevents massive tool dumps from bloating the transcript
)


class _CaptureResult(TypedDict, total=False):
    summary: str
    decisions: list[str]
    todos_pending: list[str]
    todos_done: list[str]
    transcript_path: str
    turns_captured: int


def capture_from_transcript(
    ctx: SessionContext,
    opts: TranscriptOptions,
) -> _CaptureResult:
    """Locate the provider's native transcript and distill it into the session.

    Best-effort. Returns an empty dict if the transcript can't be found or
    parsed; callers should treat this as optional enrichment.
    """
    reader = get_reader(ctx.provider)
    if reader is None:
        return {}

    from datetime import timedelta

    search_since = ctx.launch_ts - timedelta(seconds=2)
    transcript_root = opts.transcript_cwd or ctx.root
    log_extra = {
        "component": "autocapture",
        "session_id": ctx.session_id,
        "provider": ctx.provider,
    }
    candidates = _find_transcripts(
        reader,
        transcript_root,
        search_since,
        opts.source_path,
        log_extra,
    )
    if not candidates:
        return {}
    parsed: list[tuple[Path, list[Turn]]] = []
    for transcript_path in candidates:
        turns = _parse_transcript_turns(reader, transcript_path, log_extra)
        if turns:
            turns = _turns_since_launch(turns, search_since)
        if turns:
            parsed.append((transcript_path, turns))
    if not parsed:
        return {}
    selected = _select_transcript_candidate(
        parsed, opts.match_texts, require_match=opts.require_match
    )
    if selected is None:
        return {}
    transcript_path, turns = selected

    redacted = [Turn(role=t.role, text=redact_text(t.text), ts=t.ts) for t in turns]
    return _build_capture_result(ctx.root, ctx.session_id, redacted, transcript_path, log_extra)


def _find_transcripts(
    reader: Any,
    root: Path,
    search_since: datetime,
    source_path: Path | None,
    log_extra: dict[str, str],
) -> list[Path]:
    if source_path is not None:
        if _explicit_source_allowed(reader, root, source_path):
            return [source_path]
        _LOGGER.warning(
            "explicit transcript path rejected",
            extra={**log_extra, "stage": "validate_source", "transcript_path": str(source_path)},
        )
        return []
    try:
        find_candidates = getattr(reader, "find_candidates", None)
        if callable(find_candidates):
            return [path for path in find_candidates(root, search_since) if path is not None]
        result: Path | None = reader.find_latest(root, search_since)
        return [result] if result is not None else []
    except OSError as exc:
        _LOGGER.warning(
            "transcript discovery failed",
            extra={**log_extra, "error": str(exc), "stage": "find_latest"},
        )
        return []


def _explicit_source_allowed(reader: Any, root: Path, source_path: Path) -> bool:
    if source_path.is_symlink():
        return False
    try:
        resolved = source_path.resolve(strict=True)
    except OSError:
        return False
    candidate_roots = getattr(reader, "candidate_roots", None)
    if not callable(candidate_roots):
        return False
    for allowed in candidate_roots(root):
        try:
            resolved.relative_to(allowed.resolve(strict=False))
            return True
        except ValueError:
            continue
    return False


def _parse_transcript_turns(
    reader: Any, transcript_path: Path, log_extra: dict[str, str]
) -> list[Turn] | None:
    if transcript_path is None:
        _LOGGER.info("no transcript found within search window", extra=log_extra)
        return None
    try:
        turns = list(deque(reader.parse(transcript_path), maxlen=_MAX_CAPTURED_TURNS))
    except (OSError, ValueError) as exc:
        _LOGGER.warning(
            "transcript parse failed",
            extra={
                **log_extra,
                "error": str(exc),
                "stage": "parse",
                "transcript_path": str(transcript_path),
            },
        )
        return None
    if not turns:
        _LOGGER.info(
            "transcript yielded no turns",
            extra={**log_extra, "transcript_path": str(transcript_path)},
        )
        return None
    return turns


def _build_capture_result(
    root: Path,
    session_id: str,
    redacted: list[Turn],
    transcript_path: Path,
    log_extra: dict[str, str],
) -> _CaptureResult:
    paths = project_paths(root)
    dest = paths.sessions / f"{session_id}.transcript.jsonl"
    transcript_saved = False
    try:
        _write_redacted_transcript(dest, redacted)
        transcript_saved = True
    except OSError as exc:
        _LOGGER.warning(
            "redacted transcript write failed",
            extra={
                **log_extra,
                "error": str(exc),
                "stage": "write",
                "transcript_path": str(dest),
            },
        )

    block = find_loghop_block(redacted)
    if block:
        summary = str(block.get("summary") or "")
        decisions = _coerce_str_list(block.get("decisions"))
        pending = _coerce_str_list(block.get("todos_pending"))
        done = _coerce_str_list(block.get("todos_done"))
    else:
        summary = extract_summary(redacted)
        decisions = extract_decisions(redacted)
        pending, done = extract_todos(redacted)

    result: _CaptureResult = {"turns_captured": len(redacted)}
    if transcript_saved:
        result["transcript_path"] = str(dest.relative_to(root))
    elif summary or decisions or pending:
        _LOGGER.warning(
            "transcript write failed but metadata was extracted; transcript file missing",
            extra={**log_extra, "has_summary": bool(summary), "has_decisions": bool(decisions)},
        )
    if summary:
        result["summary"] = summary
    if decisions:
        result["decisions"] = decisions
    if pending:
        result["todos_pending"] = pending
    if done:
        result["todos_done"] = done
    return result


def _select_transcript_candidate(
    parsed: list[tuple[Path, list[Turn]]],
    match_texts: list[str] | None,
    *,
    require_match: bool = False,
) -> tuple[Path, list[Turn]] | None:
    hints = _normalized_hints(match_texts or [])
    if not hints or len(parsed) == 1:
        if (
            require_match
            and hints
            and _candidate_score(parsed[0][1], hints) <= 0
            and _has_user_turn(parsed[0][1])
        ):
            return None
        return parsed[0]

    scored = [
        (_candidate_score(turns, hints), idx, path, turns)
        for idx, (path, turns) in enumerate(parsed)
    ]
    best = max(scored, key=lambda item: (item[0], -item[1]))
    if require_match and best[0] <= 0 and _has_user_turn(best[3]):
        return None
    return best[2], best[3]


def _has_user_turn(turns: list[Turn]) -> bool:
    return any(turn.role == "user" for turn in turns)


def _turns_since_launch(turns: list[Turn], search_since: datetime) -> list[Turn]:
    parsed = [(_parse_turn_ts(turn.ts), turn) for turn in turns]
    # Some older fixtures and provider variants have timestamps that do not
    # correspond to filesystem mtimes. Only filter when there is clear evidence
    # this transcript contains turns from the current launch.
    if not any(ts is not None and ts >= search_since for ts, _turn in parsed):
        return turns
    return [turn for ts, turn in parsed if ts is None or ts >= search_since]


def _parse_turn_ts(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        from datetime import UTC

        return parsed.replace(tzinfo=UTC)
    return parsed


def _normalized_hints(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        for line in str(value).splitlines():
            hint = line.strip().lower()
            if len(hint) < 8 or hint in seen:  # noqa: PLR2004
                continue
            seen.add(hint)
            out.append(hint)
    return out


def _candidate_score(turns: list[Turn], hints: list[str]) -> int:
    haystack = "\n".join(turn.text.lower() for turn in turns[:8])
    return sum(len(hint) for hint in hints if hint in haystack)


def last_turns(
    root: Path,
    session_id: str,
    *,
    limit: int = 10,
) -> list[Turn]:
    """Read a captured `.transcript.jsonl` back as Turn objects. Empty if missing."""
    import json

    from loghop.store._io import safe_read_text

    paths = project_paths(root)
    path = paths.sessions / f"{session_id}.transcript.jsonl"
    if not path.exists():
        return []
    try:
        raw_text = safe_read_text(path)
    except OSError:
        return []
    turns: list[Turn] = []
    for line in raw_text.splitlines():
        raw = line.strip()
        if not raw:
            continue
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:
            continue
        turns.append(
            Turn(
                role=str(entry.get("role", "")),
                text=str(entry.get("text", "")),
                ts=str(entry.get("ts", "")),
            )
        )
    return turns[-limit:]


def _coerce_str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _write_redacted_transcript(dest: Path, turns: list[Turn]) -> None:
    import json

    def _truncate(text: str) -> str:
        if len(text) <= _MAX_TURN_CHARS:
            return text
        return text[:_MAX_TURN_CHARS] + "…[truncated]"

    with atomic_stream_to_file(dest, file_mode=FILE_MODE) as handle:
        for t in turns:
            line = json.dumps(
                {"role": t.role, "text": _truncate(t.text), "ts": t.ts}, ensure_ascii=False
            )
            handle.write(line + "\n")
