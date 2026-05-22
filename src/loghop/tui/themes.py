from textual.theme import Theme

from loghop import env

"""Token system (4 tiers + branded surfaces).

- text / text-soft / text-muted / text-quiet  (typography hierarchy)
- brand / brand-soft / brand-strong           (action color)
- border-quiet / border-strong                (chrome)
- surface / surface-hover / panel             (containers)
- success / warning / error                   (status)
Both theme dicts MUST share the same keys (validated by test_theme_parity).
"""

# =============================================================================

# =============================================================================
# LOGHOP CLASSIC DARK
# Neutral near-black base. Chrome and action affordances stay grayscale; only
# semantic states keep subtle color.
# =============================================================================
CLASSIC_DARK = Theme(
    name="loghopclassicdark",
    primary="#d4d4d4",  # Neutral action color
    secondary="#737373",  # Neutral secondary elements
    warning="#c2b280",  # Desaturated warning
    error="#c28f8f",  # Desaturated error
    success="#9ab8a0",  # Desaturated success
    accent="#e5e5e5",  # Neutral cursor / hover
    foreground="#e5e5e5",  # Main text
    background="#0f0f0f",  # Near-black
    surface="#171717",  # Panels, cards
    panel="#212121",  # Headers, dividers
    dark=True,
    luminosity_spread=0.12,
    text_alpha=0.95,
    variables={
        "input-selection-background": "#d4d4d4 24%",
        "input-cursor-foreground": "#0f0f0f",
        "input-cursor-background": "#e5e5e5",
        "button-color-foreground": "#0f0f0f",
        "button-focus-text-style": "reverse",
        "block-cursor-background": "#d4d4d4",
        "block-cursor-foreground": "#0f0f0f",
        "block-cursor-text-style": "bold",
        "footer-key-foreground": "#d4d4d4",
    },
)

_CSS_VARS_CLASSIC_DARK = {
    # Surfaces
    "$background": "#0f0f0f",
    "$surface": "#171717",
    "$surface-hover": "#212121",
    "$panel": "#212121",
    "$surface-darken-1": "#0a0a0a",
    "$surface-darken-2": "#050505",
    "$surface-lighten-1": "#2b2b2b",
    "$surface-lighten-2": "#3a3a3a",
    # Text tiers (contrast bumped to AA-comfortable)
    "$text": "#e5e5e5",
    "$text-soft": "#c7c7c7",
    "$text-muted": "#a3a3a3",
    "$text-quiet": "#808080",
    # Brand
    "$brand": "#d4d4d4",
    "$brand-soft": "#525252",
    "$brand-strong": "#f5f5f5",
    # Borders
    "$border-quiet": "#2b2b2b",
    "$border-strong": "#d4d4d4",
    # Status
    "$warning": "#c2b280",
    "$error": "#c28f8f",
    "$success": "#9ab8a0",
    # Legacy aliases — kept for compatibility, point at the new tokens
    "$accent": "#e5e5e5",
    "$accent-lighten-1": "#f5f5f5",
    "$primary": "#d4d4d4",
    "$primary-muted": "#525252",
    "$primary-lighten-1": "#f5f5f5",
    "$primary-darken-1": "#a3a3a3",
}
# =============================================================================
# LOGHOP CLASSIC LIGHT
# Neutral white base. Chrome and action affordances stay grayscale; only
# semantic states keep subtle color.
# =============================================================================
CLASSIC_LIGHT = Theme(
    name="loghopclassiclight",
    primary="#404040",  # Neutral action color
    secondary="#737373",  # Neutral secondary elements
    warning="#6f551f",  # Desaturated warning, AA on light surfaces
    error="#8f5f5f",  # Desaturated error
    success="#3a6b42",  # Desaturated success, AA on light surfaces
    accent="#262626",  # Neutral cursor / hover
    foreground="#171717",  # Main text
    background="#fafafa",  # White base
    surface="#f2f2f2",  # Panels, cards
    panel="#e5e5e5",  # Headers, borders, dividers
    dark=False,
    luminosity_spread=0.12,
    text_alpha=0.95,
    variables={
        "input-selection-background": "#404040 16%",
        "input-cursor-foreground": "#fafafa",
        "input-cursor-background": "#404040",
        "button-color-foreground": "#fafafa",
        "button-focus-text-style": "reverse",
        "block-cursor-background": "#404040",
        "block-cursor-foreground": "#fafafa",
        "block-cursor-text-style": "bold",
        "footer-key-foreground": "#404040",
    },
)

_CSS_VARS_CLASSIC_LIGHT = {
    # Surfaces
    "$background": "#fafafa",
    "$surface": "#f2f2f2",
    "$surface-hover": "#e5e5e5",
    "$panel": "#e5e5e5",
    "$surface-darken-1": "#d4d4d4",
    "$surface-darken-2": "#bdbdbd",
    "$surface-lighten-1": "#ffffff",
    "$surface-lighten-2": "#ffffff",
    # Text tiers (light side: muted/quiet bumped for AA/AAA contrast on white)
    "$text": "#171717",
    "$text-soft": "#404040",
    "$text-muted": "#4a4a4a",
    "$text-quiet": "#616161",
    # Brand
    "$brand": "#404040",
    "$brand-soft": "#d4d4d4",
    "$brand-strong": "#171717",
    # Borders
    "$border-quiet": "#d4d4d4",
    "$border-strong": "#404040",
    # Status
    "$warning": "#6f551f",
    "$error": "#8f5f5f",
    "$success": "#3a6b42",
    # Legacy aliases
    "$accent": "#262626",
    "$accent-lighten-1": "#404040",
    "$primary": "#404040",
    "$primary-muted": "#d4d4d4",
    "$primary-lighten-1": "#525252",
    "$primary-darken-1": "#171717",
}
# =============================================================================
# LOGHOP HARBOR DARK
# Deep teal/blue base. This complements Classic's grayscale restraint with a
# calm chromatic shell while preserving high-contrast semantic status colors.
# =============================================================================
HARBOR_DARK = Theme(
    name="loghopharbordark",
    primary="#63d4c8",
    secondary="#8fb1aa",
    warning="#e7bf73",
    error="#ef9a91",
    success="#8fd6a2",
    accent="#9ad7ff",
    foreground="#e7f2ef",
    background="#06171d",
    surface="#0b2229",
    panel="#0f2a33",
    dark=True,
    luminosity_spread=0.14,
    text_alpha=0.96,
    variables={
        "input-selection-background": "#63d4c8 24%",
        "input-cursor-foreground": "#06171d",
        "input-cursor-background": "#b7fff3",
        "button-color-foreground": "#06171d",
        "button-focus-text-style": "reverse",
        "block-cursor-background": "#63d4c8",
        "block-cursor-foreground": "#06171d",
        "block-cursor-text-style": "bold",
        "footer-key-foreground": "#63d4c8",
    },
)

_CSS_VARS_HARBOR_DARK = {
    # Surfaces
    "$background": "#06171d",
    "$surface": "#0b2229",
    "$surface-hover": "#12313a",
    "$panel": "#0f2a33",
    "$surface-darken-1": "#041116",
    "$surface-darken-2": "#020a0d",
    "$surface-lighten-1": "#183b45",
    "$surface-lighten-2": "#24515d",
    # Text tiers
    "$text": "#e7f2ef",
    "$text-soft": "#bfd7d1",
    "$text-muted": "#8fb1aa",
    "$text-quiet": "#6f938b",
    # Brand
    "$brand": "#63d4c8",
    "$brand-soft": "#1f5a59",
    "$brand-strong": "#b7fff3",
    # Borders
    "$border-quiet": "#1c3e47",
    "$border-strong": "#63d4c8",
    # Status
    "$warning": "#e7bf73",
    "$error": "#ef9a91",
    "$success": "#8fd6a2",
    # Legacy aliases
    "$accent": "#9ad7ff",
    "$accent-lighten-1": "#c6ecff",
    "$primary": "#63d4c8",
    "$primary-muted": "#1f5a59",
    "$primary-lighten-1": "#96e7dd",
    "$primary-darken-1": "#2f938e",
}
# =============================================================================
# LOGHOP HARBOR LIGHT
# Sea-mist light companion for Harbor Dark. Warm status colors stay readable on
# pale surfaces and the teal brand remains the primary affordance.
# =============================================================================
HARBOR_LIGHT = Theme(
    name="loghopharborlight",
    primary="#00615f",
    secondary="#405f62",
    warning="#7a5200",
    error="#933631",
    success="#315f2f",
    accent="#003f3e",
    foreground="#102b2f",
    background="#f4faf8",
    surface="#eaf4f0",
    panel="#d3e6df",
    dark=False,
    luminosity_spread=0.14,
    text_alpha=0.96,
    variables={
        "input-selection-background": "#00615f 18%",
        "input-cursor-foreground": "#f4faf8",
        "input-cursor-background": "#00615f",
        "button-color-foreground": "#f4faf8",
        "button-focus-text-style": "reverse",
        "block-cursor-background": "#00615f",
        "block-cursor-foreground": "#f4faf8",
        "block-cursor-text-style": "bold",
        "footer-key-foreground": "#00615f",
    },
)

_CSS_VARS_HARBOR_LIGHT = {
    # Surfaces
    "$background": "#f4faf8",
    "$surface": "#eaf4f0",
    "$surface-hover": "#dcece7",
    "$panel": "#d3e6df",
    "$surface-darken-1": "#c1d8d0",
    "$surface-darken-2": "#a9c6bd",
    "$surface-lighten-1": "#fbfefd",
    "$surface-lighten-2": "#ffffff",
    # Text tiers (light side: muted/quiet bumped for AA/AAA contrast on sea-mist)
    "$text": "#102b2f",
    "$text-soft": "#24464a",
    "$text-muted": "#3b585b",
    "$text-quiet": "#4a6366",
    # Brand
    "$brand": "#00615f",
    "$brand-soft": "#b9ded7",
    "$brand-strong": "#003f3e",
    # Borders
    "$border-quiet": "#b7d2cb",
    "$border-strong": "#00615f",
    # Status
    "$warning": "#7a5200",
    "$error": "#933631",
    "$success": "#315f2f",
    # Legacy aliases
    "$accent": "#003f3e",
    "$accent-lighten-1": "#00615f",
    "$primary": "#00615f",
    "$primary-muted": "#b9ded7",
    "$primary-lighten-1": "#008c85",
    "$primary-darken-1": "#003f3e",
}
THEME_REGISTRY = {
    CLASSIC_DARK.name: (CLASSIC_DARK, _CSS_VARS_CLASSIC_DARK),
    CLASSIC_LIGHT.name: (CLASSIC_LIGHT, _CSS_VARS_CLASSIC_LIGHT),
    HARBOR_DARK.name: (HARBOR_DARK, _CSS_VARS_HARBOR_DARK),
    HARBOR_LIGHT.name: (HARBOR_LIGHT, _CSS_VARS_HARBOR_LIGHT),
}

THEME_CSS_VARS = {name: css_vars for name, (_, css_vars) in THEME_REGISTRY.items()}

_THEME_KEY_BY_NAME = {
    "dark": CLASSIC_DARK.name,
    "light": CLASSIC_LIGHT.name,
    "classic-dark": CLASSIC_DARK.name,
    "classic-light": CLASSIC_LIGHT.name,
    "harbor-dark": HARBOR_DARK.name,
    "harbor-light": HARBOR_LIGHT.name,
    CLASSIC_DARK.name: CLASSIC_DARK.name,
    CLASSIC_LIGHT.name: CLASSIC_LIGHT.name,
    HARBOR_DARK.name: HARBOR_DARK.name,
    HARBOR_LIGHT.name: HARBOR_LIGHT.name,
}

_CSS_VARS_BY_THEME_KEY = {
    CLASSIC_DARK.name: _CSS_VARS_CLASSIC_DARK,
    CLASSIC_LIGHT.name: _CSS_VARS_CLASSIC_LIGHT,
    HARBOR_DARK.name: _CSS_VARS_HARBOR_DARK,
    HARBOR_LIGHT.name: _CSS_VARS_HARBOR_LIGHT,
}

_LIGHT_THEME_KEYS = {CLASSIC_LIGHT.name, HARBOR_LIGHT.name}

_PAIRED_THEME_KEY = {
    CLASSIC_DARK.name: CLASSIC_LIGHT.name,
    CLASSIC_LIGHT.name: CLASSIC_DARK.name,
    HARBOR_DARK.name: HARBOR_LIGHT.name,
    HARBOR_LIGHT.name: HARBOR_DARK.name,
}

_ROLE_TOKENS = {
    "success": "$success",
    "warning": "$warning",
    "error": "$error",
    "neutral": "$text-muted",
}

_NO_COLOR_MAP: dict[str, str] = {
    "success": "#a3a3a3",
    "warning": "#a3a3a3",
    "error": "#d4d4d4",
    "neutral": "#a3a3a3",
}


def theme_key(theme: str | None) -> str:
    """Normalize a Textual theme name or shorthand to a registered theme key."""
    normalized = (theme or "").lower()
    if normalized in _THEME_KEY_BY_NAME:
        return _THEME_KEY_BY_NAME[normalized]
    return CLASSIC_LIGHT.name if "light" in normalized else CLASSIC_DARK.name


def theme_is_light(theme: str | None) -> bool:
    return theme_key(theme) in _LIGHT_THEME_KEYS


def paired_theme(theme: str | None) -> str:
    return _PAIRED_THEME_KEY.get(theme_key(theme), CLASSIC_DARK.name)


def css_vars_for(theme: str | None) -> dict[str, str]:
    """Return TCSS variables for a theme, applying no-color overrides when requested."""
    tokens = dict(_CSS_VARS_BY_THEME_KEY[theme_key(theme)])
    if not env.no_color():
        return tokens
    tokens.update(
        {
            "$brand": tokens["$text"],
            "$brand-soft": tokens["$border-quiet"],
            "$brand-strong": tokens["$text"],
            "$warning": tokens["$text-muted"],
            "$success": tokens["$text-muted"],
            "$error": tokens["$text"],
            "$accent": tokens["$text"],
            "$accent-lighten-1": tokens["$text"],
            "$primary": tokens["$text"],
            "$primary-muted": tokens["$text-muted"],
            "$primary-lighten-1": tokens["$text"],
            "$primary-darken-1": tokens["$text-soft"],
        }
    )
    return tokens


def semantic_color(role: str, *, theme: str | None = None) -> str:
    """Resolve semantic roles to the active theme token color.

    Rich markup needs literal colors, while TCSS can use tokens directly. This
    keeps Python-rendered badges aligned with the same token dictionaries used
    by ``loghop.tcss`` instead of duplicating a second palette.

    When ``NO_COLOR`` (or ``LOGHOP_NO_COLOR``) is set, semantic status colors
    collapse to their nearest gray equivalent so the UI remains usable without
    any color tint.
    """
    if env.no_color():
        return _NO_COLOR_MAP.get((role or "").lower(), "#a3a3a3")
    tokens = _CSS_VARS_BY_THEME_KEY[theme_key(theme)]
    token = _ROLE_TOKENS.get((role or "").lower(), _ROLE_TOKENS["neutral"])
    return tokens[token]
