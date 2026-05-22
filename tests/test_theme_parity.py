"""Guard the visual system: dark and light theme dicts must define the same
tokens, and every $variable referenced from loghop.tcss must resolve in both.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from loghop.tui.themes import (
    _CSS_VARS_CLASSIC_DARK,
    _CSS_VARS_CLASSIC_LIGHT,
    _CSS_VARS_HARBOR_DARK,
    _CSS_VARS_HARBOR_LIGHT,
    CLASSIC_DARK,
    CLASSIC_LIGHT,
    HARBOR_DARK,
    HARBOR_LIGHT,
    THEME_CSS_VARS,
    theme_is_light,
    theme_key,
)
from loghop.tui.widgets import badge


def _is_grayscale(hex_color: str) -> bool:
    value = hex_color.removeprefix("#")
    if len(value) != 6:
        return False
    return value[0:2] == value[2:4] == value[4:6]


def _relative_luminance(hex_color: str) -> float:
    value = hex_color.removeprefix("#")
    channels = []
    for offset in (0, 2, 4):
        raw = int(value[offset : offset + 2], 16) / 255
        channels.append(raw / 12.92 if raw <= 0.03928 else ((raw + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def _contrast_ratio(foreground: str, background: str) -> float:
    fg = _relative_luminance(foreground)
    bg = _relative_luminance(background)
    lighter, darker = max(fg, bg), min(fg, bg)
    return (lighter + 0.05) / (darker + 0.05)


def test_no_color_css_vars_are_monochrome(monkeypatch: pytest.MonkeyPatch) -> None:
    from loghop.tui.themes import css_vars_for

    monkeypatch.setenv("NO_COLOR", "1")

    vars_ = css_vars_for(CLASSIC_DARK.name)

    assert vars_["$brand"] == vars_["$text"]
    assert vars_["$brand-strong"] == vars_["$text"]
    assert vars_["$warning"] == vars_["$text-muted"]
    assert vars_["$success"] == vars_["$text-muted"]
    assert vars_["$error"] == vars_["$text"]


def test_status_colors_pass_text_contrast_on_surfaces() -> None:
    for theme_name, vars_ in THEME_CSS_VARS.items():
        for token in ("$warning", "$error", "$success"):
            assert _contrast_ratio(vars_[token], vars_["$surface"]) >= 4.5, (
                theme_name,
                token,
                vars_[token],
                vars_["$surface"],
            )


def test_theme_dicts_have_identical_keys() -> None:
    baseline_name, baseline = next(iter(THEME_CSS_VARS.items()))
    baseline_keys = set(baseline)
    for name, css_vars in THEME_CSS_VARS.items():
        diff = baseline_keys ^ set(css_vars)
        assert not diff, f"{name} diverges from {baseline_name}: {sorted(diff)}"


def test_loghop_tokens_present_in_both_themes() -> None:
    """Tokens we own (everything except Textual built-ins) must be in both."""
    css_path = Path(__file__).resolve().parent.parent / "src/loghop/tui/styles/loghop.tcss"
    css = css_path.read_text(encoding="utf-8")
    used = {f"${name}" for name in re.findall(r"\$([a-zA-Z][a-zA-Z0-9-]*)", css)}

    # Tokens we explicitly own (defined in our dicts) must be in both.
    owned: set[str] = set()
    for css_vars in THEME_CSS_VARS.values():
        owned.update(css_vars)
    used_owned = used & owned

    for name, css_vars in THEME_CSS_VARS.items():
        missing = used_owned - set(css_vars)
        assert not missing, f"{name} missing: {sorted(missing)}"


def test_badge_colors_resolve_from_theme_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("LOGHOP_NO_COLOR", raising=False)

    assert badge.role_color("success", theme="dark") == _CSS_VARS_CLASSIC_DARK["$success"]
    assert (
        badge.role_color("warning", theme=CLASSIC_DARK.name) == _CSS_VARS_CLASSIC_DARK["$warning"]
    )
    assert badge.role_color("error", theme="light") == _CSS_VARS_CLASSIC_LIGHT["$error"]
    assert badge.color_for("failed", theme=CLASSIC_LIGHT.name) == _CSS_VARS_CLASSIC_LIGHT["$error"]
    assert badge.color_for("unknown", theme="light") == _CSS_VARS_CLASSIC_LIGHT["$text-muted"]
    assert badge.role_color("success", theme=HARBOR_DARK.name) == _CSS_VARS_HARBOR_DARK["$success"]
    assert (
        badge.role_color("warning", theme=HARBOR_LIGHT.name) == _CSS_VARS_HARBOR_LIGHT["$warning"]
    )
    assert (
        badge.color_for("unknown", theme=HARBOR_DARK.name) == _CSS_VARS_HARBOR_DARK["$text-muted"]
    )


def test_theme_name_resolution_supports_multiple_families() -> None:
    assert theme_key("dark") == CLASSIC_DARK.name
    assert theme_key("light") == CLASSIC_LIGHT.name
    assert theme_key("harbor-dark") == HARBOR_DARK.name
    assert theme_key(HARBOR_LIGHT.name) == HARBOR_LIGHT.name
    assert theme_is_light(CLASSIC_LIGHT.name)
    assert theme_is_light(HARBOR_LIGHT.name)
    assert not theme_is_light(HARBOR_DARK.name)


def test_text_tokens_keep_readable_contrast() -> None:
    minimums = {
        "$text": 7.0,
        "$text-soft": 4.5,
        "$text-muted": 4.5,
        "$text-quiet": 4.5,
    }
    for name, css_vars in THEME_CSS_VARS.items():
        background = css_vars["$background"]
        failures = {
            token: _contrast_ratio(css_vars[token], background)
            for token, minimum in minimums.items()
            if _contrast_ratio(css_vars[token], background) < minimum
        }
        assert not failures, f"{name} low contrast: {failures}"


def test_chrome_and_brand_tokens_are_neutral_grayscale() -> None:
    neutral_tokens = {
        "$background",
        "$surface",
        "$surface-hover",
        "$panel",
        "$surface-darken-1",
        "$surface-darken-2",
        "$surface-lighten-1",
        "$surface-lighten-2",
        "$text",
        "$text-soft",
        "$text-muted",
        "$text-quiet",
        "$brand",
        "$brand-soft",
        "$brand-strong",
        "$border-quiet",
        "$border-strong",
        "$accent",
        "$accent-lighten-1",
        "$primary",
        "$primary-muted",
        "$primary-lighten-1",
        "$primary-darken-1",
    }
    for theme in (_CSS_VARS_CLASSIC_DARK, _CSS_VARS_CLASSIC_LIGHT):
        non_neutral = {
            token: theme[token] for token in neutral_tokens if not _is_grayscale(theme[token])
        }
        assert not non_neutral
