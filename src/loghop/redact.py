import re
from typing import Any

SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"-----BEGIN [A-Z ]+-----[\s\S]*?-----END [A-Z ]+-----"),
        "[redacted private key block]",
    ),
    (
        re.compile(
            r"(?i)\b(ANTHROPIC|OPENAI|GOOGLE|GITHUB|AWS|AZURE|STRIPE|SLACK|HUGGINGFACE"
            r"|COHERE|MISTRAL|RESEND|POSTMARK|TWILIO|SENDGRID|DATADOG|GRAFANA)"
            r"[_-]?(API[_-]?KEY|SECRET[_-]?KEY|ACCESS[_-]?KEY|SESSION[_-]?TOKEN|TOKEN)"
            r"\s*[=:]\s*\S+"
        ),
        r"\1_\2=[redacted]",
    ),
    (
        re.compile(r"(?i)\b([A-Z0-9_]*(?:SESSION_TOKEN|KEY_BASE))\s*[=:]\s*\S+"),
        r"\1=[redacted]",
    ),
    (
        re.compile(
            r"(?i)\b(api[_-]?key|secret|password|passwd|token|auth[_-]?token|access[_-]?token|refresh[_-]?token|private[_-]?key|credentials?)\s*([:=])\s*[\"']?\S+"
        ),
        r"\1\2[redacted]",
    ),
    (
        re.compile(
            r"""(?i)["']?(api[_-]?key|secret|password|token|credentials|auth[_-]?token)["']?\s*:\s*["'][^"']+["']"""
        ),
        r'"\1": "[redacted]"',
    ),
    (
        re.compile(
            r"(?i)\b(DATABASE_URL|MONGO_URI|REDIS_URL|CONNECTION_STRING|CONN_STR)\s*[=:]\s*\S+"
        ),
        r"\1=[redacted]",
    ),
    (
        re.compile(r"https?://[^/@\s:]+:[^/@\s]+@\S+"),
        "[redacted credential url]",
    ),
    # Anthropic-specific (catch with informative label before the generic sk- rule).
    (
        re.compile(r"\bsk-ant-(?:api|admin)\d{2}-[A-Za-z0-9_-]{32,}"),
        "[redacted anthropic api key]",
    ),
    # OpenAI project + service-account tokens (modern format).
    (
        re.compile(r"\bsk-(?:proj|svcacct)-[A-Za-z0-9_-]{20,}"),
        "[redacted openai api key]",
    ),
    # Google Cloud / Firebase / Maps API keys.
    (
        re.compile(r"\bAIza[0-9A-Za-z_-]{35}"),
        "[redacted google api key]",
    ),
    # Hugging Face access tokens.
    (
        re.compile(r"\bhf_[A-Za-z0-9]{34,}"),
        "[redacted huggingface token]",
    ),
    # npm tokens (publish + automation).
    (
        re.compile(r"\bnpm_[A-Za-z0-9]{9,}"),
        "[redacted npm token]",
    ),
    (
        re.compile(r"(?i)\b(sk-|pk_live_|sk_live_|tok_|xox[bposa]-)[\w-]+"),
        "[redacted api key]",
    ),
    (
        re.compile(r"AKIA[0-9A-Z]{16}"),
        "[redacted aws access key]",
    ),
    (
        re.compile(r"(?i)\baws_secret_access_key\s*[=:]\s*[\"']?[A-Za-z0-9/+=]{40}[\"']?"),
        "aws_secret_access_key=[redacted]",
    ),
    (
        re.compile(
            r"(?i)\b(service_account|client_email)\s*[=:]\s*[\"']?[^\s\"']+@[^\s\"']+\.iam\.gserviceaccount\.com[\"']?"
        ),
        r"\1=[redacted gcp service account]",
    ),
    (
        re.compile(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),
        "[redacted jwt]",
    ),
    # GitHub tokens — covers ghp_ (personal), gho_ (oauth), ghu_ (user-to-server),
    # ghs_ (server-to-server), ghr_ (refresh).
    (
        re.compile(r"\bgh[posru]_[A-Za-z0-9_]{36,}"),
        "[redacted github token]",
    ),
    (
        re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
        "[redacted github token]",
    ),
    (
        re.compile(r"glpat-[A-Za-z0-9\-]{20,}"),
        "[redacted gitlab token]",
    ),
    (
        re.compile(r"SG\.[A-Za-z0-9_-]{22}\.[A-Za-z0-9_-]{43}"),
        "[redacted sendgrid key]",
    ),
    (
        re.compile(r"xox[cbarsp]-[A-Za-z0-9-]+"),
        "[redacted slack token]",
    ),
    (
        re.compile(
            r"https://hooks\.slack\.com/services/[A-Za-z0-9_-]+/[A-Za-z0-9_-]+/[A-Za-z0-9_-]+"
        ),
        "[redacted slack webhook]",
    ),
    (
        re.compile(
            r"https?://(?:ptb\.|canary\.)?discord(?:app)?\.com/api/webhooks/\d+/[A-Za-z0-9_-]+"
        ),
        "[redacted discord webhook]",
    ),
    (
        re.compile(r"\b[A-Za-z0-9\-_]{24,26}\.[A-Za-z0-9\-_]{6}\.[A-Za-z0-9\-_]{27,38}\b"),
        "[redacted discord token]",
    ),
    (
        re.compile(r"(?i)\bBearer\s+[A-Za-z0-9_\-.+/]+=*"),
        "Bearer [redacted]",
    ),
    (
        re.compile(r"(?i)\bBasic\s+[A-Za-z0-9+/=]{4,}"),
        "Basic [redacted]",
    ),
    (
        re.compile(r"(?i)\bToken\s+[A-Za-z0-9_\-.+/]+=*"),
        "Token [redacted]",
    ),
)


_custom_patterns: list[tuple[re.Pattern[str], str]] | None = None


def get_redaction_patterns() -> list[tuple[re.Pattern[str], str]]:
    global _custom_patterns
    if _custom_patterns is not None:
        return _custom_patterns

    patterns: list[tuple[re.Pattern[str], str]] = []

    # 1. Load global config custom redaction patterns
    try:
        from loghop.install._config import global_config_path

        g_path = global_config_path()
        if g_path.exists():
            import tomllib

            with open(g_path, "rb") as f:
                data = tomllib.load(f)
            redactions = data.get("redaction", [])
            if isinstance(redactions, list):
                patterns.extend(
                    (re.compile(item["pattern"]), item["replacement"])
                    for item in redactions
                    if isinstance(item, dict) and "pattern" in item and "replacement" in item
                )
    except Exception:  # noqa: BLE001
        pass

    # 2. Load project config custom redaction patterns
    try:
        import tomllib
        from pathlib import Path

        from loghop.store import find_project_root

        root = find_project_root(Path.cwd())
        if root:
            p_path = root / ".loghop" / "config.toml"
            if p_path.exists():
                with open(p_path, "rb") as f:
                    data = tomllib.load(f)
                redactions = data.get("redaction", [])
                if isinstance(redactions, list):
                    patterns.extend(
                        (re.compile(item["pattern"]), item["replacement"])
                        for item in redactions
                        if isinstance(item, dict) and "pattern" in item and "replacement" in item
                    )
    except Exception:  # noqa: BLE001
        pass

    _custom_patterns = patterns
    return _custom_patterns


def _clear_redact_cache() -> None:
    global _custom_patterns
    _custom_patterns = None


def redact_text(text: str | None) -> str:
    if not text:
        return ""
    redacted = text
    for pattern, replacement in get_redaction_patterns():
        redacted = pattern.sub(replacement, redacted)
    for pattern, replacement in SECRET_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def redact_dict(data: Any) -> Any:
    if isinstance(data, str):
        return redact_text(data)
    if isinstance(data, dict):
        return {
            redact_text(str(k)) if isinstance(k, str) else k: redact_dict(v)
            for k, v in data.items()
        }
    if isinstance(data, list | tuple):
        return type(data)(redact_dict(item) for item in data)
    if isinstance(data, set | frozenset):
        return type(data)(redact_dict(item) for item in data)
    return data
