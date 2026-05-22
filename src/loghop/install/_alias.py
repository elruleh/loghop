from pathlib import Path

from loghop.install._config import _backup
from loghop.install._types import InstallReport
from loghop.store._io import atomic_write_text

START_MARKER = "# >>> loghop aliases >>>"
END_MARKER = "# <<< loghop aliases <<<"
ALIAS_BLOCK = f"""{START_MARKER}
alias claude='loghop wrap claude'
alias codex='loghop wrap codex'
{END_MARKER}"""


def install_aliases(
    *,
    uninstall: bool = False,
    dry_run: bool = False,
) -> list[InstallReport]:
    """Install or uninstall shell aliases in local shell profile files."""
    profiles = [
        Path.home() / ".bashrc",
        Path.home() / ".zshrc",
        Path.home() / ".config" / "fish" / "config.fish",
    ]

    return [_process_profile(path, uninstall=uninstall, dry_run=dry_run) for path in profiles]


def _process_profile(path: Path, uninstall: bool, dry_run: bool) -> InstallReport:
    if not path.exists():
        return InstallReport(
            path, "skipped" if not uninstall else "unchanged", "profile does not exist"
        )

    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        return InstallReport(path, "error", f"could not read file: {exc}")

    has_block = START_MARKER in content and END_MARKER in content

    if uninstall:
        if not has_block:
            return InstallReport(path, "unchanged")
        if dry_run:
            return InstallReport(path, "would-remove")

        lines = content.splitlines(keepends=True)
        new_lines = []
        in_block = False
        for line in lines:
            if START_MARKER in line:
                in_block = True
                continue
            if END_MARKER in line:
                in_block = False
                continue
            if not in_block:
                new_lines.append(line)

        new_content = "".join(new_lines)
        if content.endswith("\n") and not new_content.endswith("\n"):
            new_content += "\n"

        _backup(path)

        try:
            atomic_write_text(path, new_content)
        except OSError as exc:
            return InstallReport(path, "error", f"could not write file: {exc}")
        return InstallReport(path, "removed")

    else:
        if has_block:
            try:
                start_idx = content.index(START_MARKER)
                end_idx = content.index(END_MARKER) + len(END_MARKER)
                current_block = content[start_idx:end_idx].strip()
                if current_block == ALIAS_BLOCK.strip():
                    return InstallReport(path, "unchanged")
            except ValueError:
                pass

        if dry_run:
            return InstallReport(path, "would-update" if has_block else "would-create")

        if has_block:
            lines = content.splitlines(keepends=True)
            new_lines = []
            in_block = False
            for line in lines:
                if START_MARKER in line:
                    in_block = True
                    new_lines.append(ALIAS_BLOCK + "\n")
                    continue
                if END_MARKER in line:
                    in_block = False
                    continue
                if not in_block:
                    new_lines.append(line)
            new_content = "".join(new_lines)
        else:
            if content and not content.endswith("\n"):
                new_content = content + "\n\n" + ALIAS_BLOCK + "\n"
            else:
                new_content = content + "\n" + ALIAS_BLOCK + "\n"

        _backup(path)

        try:
            atomic_write_text(path, new_content)
        except OSError as exc:
            return InstallReport(path, "error", f"could not write file: {exc}")

        return InstallReport(path, "updated" if has_block else "created")
