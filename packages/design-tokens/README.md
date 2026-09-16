# Design tokens

Specification Section 6.4. One file, [`tokens.css`](tokens.css), holding every
colour, radius, shadow, spacing step and font stack the application uses.

**The contrast requirement is tested, not asserted.**
[`apps/api/tests/unit/test_design_tokens.py`](../../apps/api/tests/unit/test_design_tokens.py)
parses this file, computes the WCAG 2.2 relative-luminance ratio for every
foreground/background pair the application actually renders, and fails if any
text pair falls below 6.6.b's 4.5:1 or any interactive border below WCAG
1.4.11's 3:1. Editing a value to something that looks nicer and fails breaks
the build, which is the point.

Current ratios, computed by that test:

| Pair | Ratio | Needs |
|---|---|---|
| `text-primary` on `canvas` | 14.76 | 4.5 |
| `text-primary` on `surface` | 15.65 | 4.5 |
| `text-secondary` on `canvas` | 5.76 | 4.5 |
| `accent-primary` on `surface` | 5.35 | 4.5 |
| `accent-financial` on `surface` | 8.80 | 4.5 |
| `warning` on `warning-surface` | 5.35 | 4.5 |
| `danger` on `danger-surface` | 5.58 | 4.5 |
| `success` on `success-surface` | 4.66 | 4.5 |
| `text-inverse` on `accent-primary` | 5.35 | 4.5 |
| `border-strong` on `canvas` | 5.08 | 3.0 |

## Two places the literal reading of 6.1 had to bend

**Amber is not a text colour.** 6.1.g asks for "amber for unresolved or
review-required states", and `#f5a623` on white is 2.1:1. So amber is the
*surface* of an unresolved badge and the text on it is a dark amber that
passes. The state still reads amber; the words are still legible.

**Borders come in two weights.** A rule between cards has no contrast
minimum. The border of a form control has one — WCAG 1.4.11, 3:1 — and
`--color-border` does not meet it against the canvas. `--color-border-strong`
does. They are not interchangeable, and the test checks the strong one.

## Fonts

6.2 recommends Source Serif 4 and Inter. Neither is bundled: decisions 2.3.d
and 2.3.e close outbound network access, and a webfont from a CDN is an
outbound request on every page load. The stacks name the recommended faces
first and fall back to the system, so installing them locally is all it takes
to get the intended typography.

6.2.c (tabular numerals) is applied in the application stylesheet via
`font-variant-numeric: tabular-nums` on every numeric cell, not here — it is a
property, not a token.
