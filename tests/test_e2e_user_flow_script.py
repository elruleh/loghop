from __future__ import annotations

import subprocess
from pathlib import Path


def test_e2e_user_flow_script_help() -> None:
    script = Path(__file__).resolve().parents[1] / "scripts" / "e2e_user_flow.py"

    assert script.exists()
    proc = subprocess.run(
        ["python3", str(script), "--help"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0
    assert "--run-root" in proc.stdout
    assert "--real-providers" in proc.stdout
    assert "--skip-pytest" in proc.stdout
