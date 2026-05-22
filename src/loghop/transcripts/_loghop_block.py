import re

_FENCE_RE = re.compile(
    r"```loghop\s*\n(.*?)\n```",
    re.DOTALL | re.IGNORECASE,
)


def parse_loghop_block(text: str) -> dict[str, object] | None:
    """Find a ```loghop fenced block in `text` and parse it.

    The expected shape is:
        ```loghop
        summary: <free text, may span lines until next key>
        decisions:
          - item one
          - item two
        todos_done:
          - ...
        todos_pending:
          - ...
        ```

    Returns a dict with whichever keys were present, or None if no block
    is found. Tolerant: extra keys are ignored, missing keys are omitted,
    malformed input still produces what could be salvaged.
    """
    if not text:
        return None
    matches = list(_FENCE_RE.finditer(text))
    if not matches:
        return None
    body = matches[-1].group(1)
    return _parse_body(body)


_KNOWN_KEYS = {"summary", "decisions", "todos_done", "todos_pending"}
_LIST_KEYS = {"decisions", "todos_done", "todos_pending"}


def _parse_body(body: str) -> dict[str, object]:
    out: dict[str, object] = {}
    current_key: str | None = None
    summary_lines: list[str] = []

    for raw_line in body.splitlines():
        line = raw_line.rstrip()
        stripped = line.lstrip()

        if not stripped:
            if current_key == "summary":
                summary_lines.append("")
            continue

        if stripped.startswith("- ") or stripped.startswith("* "):
            current_key = _handle_list_item(out, current_key, stripped)
            continue

        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$", line)
        if match:
            current_key, summary_lines = _handle_key_line(
                out,
                current_key,
                summary_lines,
                match.group(1).lower(),
                match.group(2).strip(),
                stripped,
            )
            continue

        if current_key == "summary":
            summary_lines.append(stripped)

    if current_key == "summary" and summary_lines:
        out["summary"] = "\n".join(summary_lines).strip()

    return out


def _handle_list_item(out: dict[str, object], current_key: str | None, stripped: str) -> str | None:
    if current_key in _LIST_KEYS:
        value = stripped[2:].strip()
        if value:
            bucket = out.setdefault(current_key, [])
            if isinstance(bucket, list):
                bucket.append(value)
    return current_key


def _handle_key_line(
    out: dict[str, object],
    current_key: str | None,
    summary_lines: list[str],
    new_key: str,
    value: str,
    stripped: str,
) -> tuple[str | None, list[str]]:
    if new_key in _KNOWN_KEYS:
        if current_key == "summary" and summary_lines:
            out["summary"] = "\n".join(summary_lines).strip()
            summary_lines = []
        if new_key == "summary":
            if value:
                summary_lines.append(value)
        elif new_key in _LIST_KEYS:
            out.setdefault(new_key, [])
            if value:
                bucket = out[new_key]
                if isinstance(bucket, list):
                    bucket.append(value)
        return new_key, summary_lines
    if current_key == "summary":
        summary_lines.append(stripped)
        return current_key, summary_lines
    return None, summary_lines
