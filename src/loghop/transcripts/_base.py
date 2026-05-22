import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class Turn:
    role: str
    text: str
    ts: str


class TranscriptReader(Protocol):
    def find_latest(self, cwd: Path, since: datetime) -> Path | None: ...

    def parse(self, path: Path) -> Iterable[Turn]: ...


def get_reader(provider: str) -> TranscriptReader | None:
    if provider == "claude":
        from loghop.transcripts._claude import ClaudeTranscriptReader

        return ClaudeTranscriptReader()
    if provider == "codex":
        from loghop.transcripts._codex import CodexTranscriptReader

        return CodexTranscriptReader()
    return None


_PLACEHOLDER_LOG_LIKE = "(no structured summary; see transcript)"


def extract_summary(turns: Iterable[Turn], *, max_chars: int = 500) -> str:
    """Best-effort summary when the LLM did not emit a ```loghop block.

    Picks the last assistant turn but refuses to truncate clearly
    log-like output (long, mostly raw text from `[tool_result]` blocks),
    since the first 500 chars of a `find /` listing is worse than no
    summary at all.
    """
    last_assistant: Turn | None = None
    for turn in turns:
        if turn.role == "assistant":
            last_assistant = turn
    if last_assistant is None:
        return ""
    text = last_assistant.text.strip()
    if not text:
        return ""
    if _looks_like_log_output(text, max_chars=max_chars):
        return _PLACEHOLDER_LOG_LIKE
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def _looks_like_log_output(text: str, *, max_chars: int) -> bool:
    """Heuristic: does this assistant turn look like raw tool output rather than prose?

    Triggers when the turn is very long AND most of its bulk is a single
    ``[tool_result]`` block, OR when it's a giant unbroken blob with few
    sentence-like cues. Prose summaries written by the model rarely fit
    either profile, so the false-positive rate is acceptable.
    """
    # Short replies are always treated as prose — even if they look like
    # logs, truncating to 500 chars keeps everything anyway.
    if len(text) <= max_chars * 2:
        return False
    # Tool-result-dominated output is the most common failure mode. If a
    # single tool_result block carries most of the bytes, the prose around
    # it is too thin to summarize honestly.
    chunks = text.split("[tool_result]")
    tool_result_chars = sum(len(c) for c in chunks[1:])
    if tool_result_chars > len(text) * 0.5:
        return True
    # Very long, very few sentence terminators → likely a paste/dump.
    sentence_terminators = text.count(". ") + text.count("? ") + text.count("! ")
    return len(text) > max_chars * 4 and sentence_terminators < len(text) // 400


# Decision phrasing seen in the wild: "Decision:", "We decided to", "Decided",
# "Resolved", "Conclusion:", "Chose to", "Agreed to". The capture group keeps
# whatever follows the marker so the listed value is meaningful.
_DECISION_RE = re.compile(
    r"^\s*(?:"
    r"decision|decided(?:\s+to)?|we\s+decided(?:\s+to)?|"
    r"resolved|conclusion|chose(?:\s+to)?|agreed(?:\s+to)?"
    r")\s*[:\-]?\s+(.+)$",
    re.IGNORECASE,
)
_TODO_CHECK_RE = re.compile(r"^\s*[-*]\s*\[\s*\]\s*(.+)$")
# TODOs accept optional parenthetical qualifier: "TODO:", "TODO (later):",
# "Next:", "Next step", "Follow-up", "Pending:".
_TODO_PREFIX_RE = re.compile(
    r"^\s*(?:todo|next(?:\s+step)?|follow[- ]up|pending)" r"(?:\s*\([^)]*\))?\s*[:\-]\s*(.+)$",
    re.IGNORECASE,
)
_DONE_CHECK_RE = re.compile(r"^\s*[-*]\s*\[\s*[xX]\s*\]\s*(.+)$")


def find_loghop_block(turns: Iterable[Turn]) -> dict[str, object] | None:
    """Scan turns newest-to-oldest for a ```loghop fenced block.

    Returns the parsed block dict if found, or None. The block is the
    LLM-emitted structured metadata that takes precedence over regex
    heuristics when present.

    Scans all assistant turns in reverse so a brief ACK turn at the end
    ("Done.", "You're welcome.") doesn't shadow a block emitted earlier.
    """
    from loghop.transcripts._loghop_block import parse_loghop_block

    assistant_turns = [t for t in turns if t.role == "assistant"]
    for turn in reversed(assistant_turns):
        block = parse_loghop_block(turn.text)
        if block:
            return block
    return None


def extract_decisions(turns: Iterable[Turn], *, limit: int = 20) -> list[str]:
    out: list[str] = []
    for turn in turns:
        if turn.role != "assistant":
            continue
        for line in turn.text.splitlines():
            match = _DECISION_RE.match(line)
            if match:
                value = match.group(1).strip()
                if value and value not in out:
                    out.append(value)
                    if len(out) >= limit:
                        return out
    return out


def extract_todos(turns: Iterable[Turn], *, limit: int = 30) -> tuple[list[str], list[str]]:
    pending: list[str] = []
    done: list[str] = []
    for turn in turns:
        if turn.role != "assistant":
            continue
        for line in turn.text.splitlines():
            done_match = _DONE_CHECK_RE.match(line)
            if done_match:
                value = done_match.group(1).strip()
                if value and value not in done:
                    done.append(value)
                if value in pending:
                    pending.remove(value)
                continue
            check_match = _TODO_CHECK_RE.match(line)
            if check_match:
                value = check_match.group(1).strip()
                if value and value not in pending and value not in done:
                    pending.append(value)
                continue
            prefix_match = _TODO_PREFIX_RE.match(line)
            if prefix_match:
                value = prefix_match.group(1).strip()
                if value and value not in pending and value not in done:
                    pending.append(value)
    pending = [item for item in pending if item not in done]
    return pending[:limit], done[:limit]
