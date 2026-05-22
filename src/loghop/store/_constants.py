from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

VERSION = 1
FILE_MODE = 0o600
DIR_MODE = 0o700
DEFAULT_TIMEOUT = 300
DEFAULT_MEMORY_FILE = "loghop.md"
_MAX_SESSIONS_SOFT_LIMIT = 1000


class SessionStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    TIMED_OUT = "timed_out"
    LAUNCH_FAILED = "launch_failed"


SKIP_FOR_RESUME: frozenset[str] = frozenset(
    str(s)
    for s in (
        SessionStatus.RUNNING,
        SessionStatus.FAILED,
        SessionStatus.LAUNCH_FAILED,
        SessionStatus.TIMED_OUT,
        SessionStatus.INTERRUPTED,
    )
)
DEFAULT_IGNORE = """# loghop handoff exclusions
.loghop/
*.png
*.jpg
*.jpeg
*.gif
*.pdf
*.zip
*.tar
*.gz
*.p12
*.pfx
*.pem
*.key
*.env
.env
.env.*
.npmrc
.pypirc
.netrc
.kube/
kubeconfig
id_rsa
id_ed25519
node_modules/
dist/
build/
"""


def utc_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class ProjectPaths:
    root: Path
    dot: Path
    config: Path
    handoffs: Path
    sessions: Path
    topics: Path
    timeline: Path
    ignore: Path
    memory: Path


def project_paths(root: Path) -> ProjectPaths:
    dot = root / ".loghop"
    return ProjectPaths(
        root=root,
        dot=dot,
        config=dot / "config.toml",
        handoffs=dot / "handoffs",
        sessions=dot / "sessions",
        topics=dot / "topics",
        timeline=dot / "timeline.jsonl",
        ignore=dot / ".loghopignore",
        memory=root / DEFAULT_MEMORY_FILE,
    )
