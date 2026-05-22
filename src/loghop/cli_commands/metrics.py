from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
from typing import Any

from loghop.store import (
    find_project_root,
    list_handoffs,
    list_sessions,
    list_timeline_events,
    project_paths,
)
from loghop.terminal import Terminal


def handle_metrics(args: argparse.Namespace, term: Terminal) -> int:
    root = find_project_root(Path.cwd())
    if root is None:
        term.error("loghop is not initialized in this directory")
        term.capture_result({"initialized": False})
        return 20
    metrics = collect_metrics(root)
    fmt = getattr(args, "format", "summary")
    if fmt == "prometheus":
        text = render_prometheus(metrics)
        term.line(text.rstrip())
        term.capture_result({**metrics, "text": text})
        return 0
    if fmt == "json":
        import json

        text = json.dumps(metrics, indent=2, sort_keys=True)
        term.line(text)
        term.capture_result({**metrics, "text": text})
        return 0
    if fmt == "yaml":
        import yaml

        text = yaml.safe_dump(metrics, sort_keys=True)
        term.line(text.rstrip())
        term.capture_result({**metrics, "text": text})
        return 0
    rows = [(key, str(value)) for key, value in metrics.items() if not isinstance(value, dict)]
    term.section("loghop metrics", rows)
    term.capture_result(metrics)
    return 0


def collect_metrics(root: Path) -> dict[str, Any]:
    paths = project_paths(root)
    sessions = list_sessions(paths)
    handoffs = list_handoffs(paths)
    timeline_events = list_timeline_events(paths, include_technical=True)
    status_counts = Counter(str(session.status) for session in sessions)
    provider_counts = Counter(str(session.provider) for session in sessions)
    return {
        "sessions_total": len(sessions),
        "handoffs_total": len(handoffs),
        "timeline_events_total": len(timeline_events),
        "sessions_by_status": dict(sorted(status_counts.items())),
        "sessions_by_provider": dict(sorted(provider_counts.items())),
    }


def render_prometheus(metrics: dict[str, Any]) -> str:
    lines = [
        "# HELP loghop_sessions_total Total loghop sessions.",
        "# TYPE loghop_sessions_total counter",
        f"loghop_sessions_total {int(metrics['sessions_total'])}",
        "# HELP loghop_handoffs_total Total loghop handoffs.",
        "# TYPE loghop_handoffs_total counter",
        f"loghop_handoffs_total {int(metrics['handoffs_total'])}",
        "# HELP loghop_timeline_events_total Total timeline events.",
        "# TYPE loghop_timeline_events_total counter",
        f"loghop_timeline_events_total {int(metrics['timeline_events_total'])}",
    ]
    for status, count in dict(metrics.get("sessions_by_status", {})).items():
        lines.append(f'loghop_sessions_by_status_total{{status="{_label(status)}"}} {int(count)}')
    for provider, count in dict(metrics.get("sessions_by_provider", {})).items():
        lines.append(
            f'loghop_sessions_by_provider_total{{provider="{_label(provider)}"}} {int(count)}'
        )
    return "\n".join(lines) + "\n"


def _label(value: object) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')
