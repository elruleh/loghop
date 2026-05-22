import argparse

from loghop.providers import SUPPORTED_PROVIDER_NAMES, detect_all
from loghop.terminal import Terminal


def handle_providers_list(_args: argparse.Namespace, term: Terminal) -> int:
    providers = detect_all()
    rows: list[tuple[str, str, str]] = []
    for name in SUPPORTED_PROVIDER_NAMES:
        detection = providers[name]
        state = "available" if detection.installed else "missing"
        path = detection.path or "not installed"
        rows.append((name, state, str(path)))
    term.table(rows, headers=("provider", "state", "path"), title="providers")
    term.capture_result(
        {
            "providers": {
                name: {"path": detection.path, "installed": detection.installed}
                for name, detection in providers.items()
            },
        }
    )
    return 0
