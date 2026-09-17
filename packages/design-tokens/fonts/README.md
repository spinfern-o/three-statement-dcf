# Vendored fonts

Specification item 122 and 6.2. Both families are unmodified releases under the
[SIL Open Font License 1.1](https://scripts.sil.org/OFL), whose text is beside
them as the licence requires.

| File | Family | Weight | Bytes | Licence |
|---|---|---|---|---|
| `source-serif-4-latin-400-normal.woff2` | Source Serif 4 | 400 | 20,088 | `OFL-SourceSerif4.txt` |
| `source-serif-4-latin-600-normal.woff2` | Source Serif 4 | 600 | 21,532 | `OFL-SourceSerif4.txt` |
| `inter-latin-400-normal.woff2` | Inter | 400 | 23,664 | `OFL-Inter.txt` |
| `inter-latin-500-normal.woff2` | Inter | 500 | 24,272 | `OFL-Inter.txt` |
| `inter-latin-600-normal.woff2` | Inter | 600 | 24,452 | `OFL-Inter.txt` |

Latin subsets, taken from the [Fontsource](https://fontsource.org) builds.
114 KB for all five faces.

## Why these two

6.2.a asks for "an open-source editorial serif for page titles and major
financial figures" and recommends Source Serif 4 or Libre Baskerville. 6.2.b
asks for an open-source sans for everything else and recommends Inter.

6.2.c is the requirement that makes the choice matter rather than taste:
**tabular numerals for all financial values.** Inter has them, and the CSS
turns them on with `font-variant-numeric: tabular-nums`. A fallback stack that
happens to lack them misaligns every column of figures on every statement
screen, which is the one thing a financial table cannot do.

## Why self-hosted

The review server binds to 127.0.0.1 and holds an unreleased filing. A page
that fetched its fonts from a CDN would tell that CDN when the model was being
looked at, and would lose its numeric alignment the moment the CDN was
unreachable. Section 20's independence requirement points the same way.

## Adding a script

Only the Latin subset is here. A filing in another script needs its subset
added deliberately -- Inter and Source Serif 4 both ship Cyrillic and Greek --
rather than 400 KB of coverage carried against the possibility.
