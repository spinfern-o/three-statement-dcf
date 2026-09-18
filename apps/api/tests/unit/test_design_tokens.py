"""Specification 6.4 and 6.6.b: the token values must pass contrast testing.

6.4 requires the exact colour values "pass contrast testing and be recorded in
packages/design-tokens". Recording them is easy and testing them is the part
that rots, so the test parses the recorded file rather than holding its own
copy of the palette. A value edited in `tokens.css` to something that looks
nicer and fails WCAG breaks the build.

The ratio is WCAG 2.2's: relative luminance from linearized sRGB, and
(L1 + 0.05) / (L2 + 0.05).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

TOKENS = Path(__file__).resolve().parents[4] / "packages" / "design-tokens" / "tokens.css"

#: 6.6.b. Normal text.
TEXT_MINIMUM = 4.5
#: WCAG 2.2 success criterion 1.4.11, non-text contrast for UI components.
COMPONENT_MINIMUM = 3.0


def _tokens() -> dict[str, str]:
    text = TOKENS.read_text()
    found = dict(re.findall(r"(--[a-z0-9-]+):\s*(#[0-9a-fA-F]{6})\s*;", text))
    assert found, f"no colour tokens parsed from {TOKENS}"
    return found


def _channel(value: int) -> float:
    c = value / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _luminance(colour: str) -> float:
    h = colour.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast(a: str, b: str) -> float:
    la, lb = _luminance(a), _luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def test_the_ratio_function_matches_the_known_extremes():
    """Black on white is 21:1 and a colour on itself is 1:1, by definition."""
    assert round(contrast("#000000", "#ffffff"), 2) == 21.0
    assert round(contrast("#123456", "#123456"), 2) == 1.0


#: Every foreground/background pair the application actually renders.
TEXT_PAIRS = [
    ("--color-text-primary", "--color-canvas"),
    ("--color-text-primary", "--color-surface"),
    ("--color-text-primary", "--color-surface-muted"),
    ("--color-text-primary", "--color-warning-surface"),
    ("--color-text-secondary", "--color-canvas"),
    ("--color-text-secondary", "--color-surface"),
    ("--color-accent-primary", "--color-surface"),
    ("--color-accent-financial", "--color-surface"),
    ("--color-warning", "--color-surface"),
    ("--color-warning", "--color-warning-surface"),
    ("--color-danger", "--color-surface"),
    ("--color-danger", "--color-danger-surface"),
    ("--color-success", "--color-success-surface"),
    ("--color-text-inverse", "--color-accent-primary"),
    ("--color-text-inverse", "--color-danger"),
    ("--color-text-inverse", "--color-accent-financial"),
]

COMPONENT_PAIRS = [
    ("--color-border-strong", "--color-canvas"),
    ("--color-border-strong", "--color-surface"),
    ("--color-focus", "--color-canvas"),
    ("--color-focus", "--color-surface"),
]


@pytest.mark.parametrize("foreground, background", TEXT_PAIRS)
def test_text_meets_wcag_aa(foreground, background):
    tokens = _tokens()
    ratio = contrast(tokens[foreground], tokens[background])
    assert ratio >= TEXT_MINIMUM, (
        f"{foreground} ({tokens[foreground]}) on {background} "
        f"({tokens[background]}) is {ratio:.2f}:1, below 6.6.b's {TEXT_MINIMUM}:1"
    )


@pytest.mark.parametrize("foreground, background", COMPONENT_PAIRS)
def test_interactive_boundaries_meet_non_text_contrast(foreground, background):
    tokens = _tokens()
    ratio = contrast(tokens[foreground], tokens[background])
    assert ratio >= COMPONENT_MINIMUM, (
        f"{foreground} on {background} is {ratio:.2f}:1, below WCAG 1.4.11's "
        f"{COMPONENT_MINIMUM}:1 for a form control's border"
    )


def test_every_token_section_6_4_names_is_defined():
    """6.4 lists the tokens by name. All of them, or the list is decoration."""
    required = [
        "--color-canvas",
        "--color-surface",
        "--color-surface-muted",
        "--color-text-primary",
        "--color-text-secondary",
        "--color-accent-primary",
        "--color-accent-financial",
        "--color-success",
        "--color-warning",
        "--color-danger",
        "--color-border",
        "--radius-card",
        "--radius-control",
        "--shadow-card",
        *[f"--space-{n}" for n in range(1, 13)],
    ]
    text = TOKENS.read_text()
    missing = [name for name in required if f"{name}:" not in text]
    assert not missing, f"6.4 names these and tokens.css does not define them: {missing}"


def test_reduced_motion_is_honoured():
    """6.6.g."""
    assert "prefers-reduced-motion" in TOKENS.read_text()
