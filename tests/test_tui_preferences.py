from pathlib import Path

import pytest


def test_tui_preferences_round_trip(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    from loghop.install._config import load_tui_preferences, save_tui_preferences

    assert load_tui_preferences() == {}

    save_tui_preferences(theme="loghopharborlight", language="es")

    assert load_tui_preferences() == {
        "theme": "loghopharborlight",
        "language": "es",
    }


def test_tui_preferences_ignore_empty_values(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    from loghop.install._config import load_tui_preferences, save_tui_preferences

    save_tui_preferences(theme="loghopclassiclight", language="en")
    save_tui_preferences(theme="", language=None)

    assert load_tui_preferences() == {"language": "en"}
