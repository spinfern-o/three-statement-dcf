"""A YAML loader that does not destroy numeric precision before we see it.

PyYAML resolves a numeric scalar to a Python float during parsing, so by the
time `yaml.safe_load` returns, `0.08` is already

    0.08000000000000000166533453693773481063544750213623046875

and no later conversion can recover the 0.08 that was written in the file.
Specification 4.2 requires monetary inputs to be handled as decimal strings
at the boundary, which is exactly this problem.

`load_exact` keeps every numeric scalar as the string the file contained, so
`model.numeric.D` can build an exact Decimal from the original digits.
Booleans, nulls, dates and strings are untouched, and the structure is
otherwise identical to `yaml.safe_load`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class ExactLoader(yaml.SafeLoader):
    """SafeLoader that hands back numeric scalars verbatim, as strings."""


def _keep_as_written(loader: yaml.SafeLoader, node: yaml.Node) -> str:
    return loader.construct_scalar(node)


# Only int and float are intercepted. bool, null, timestamp and str keep
# SafeLoader's behaviour, because none of them loses information.
ExactLoader.add_constructor("tag:yaml.org,2002:int", _keep_as_written)
ExactLoader.add_constructor("tag:yaml.org,2002:float", _keep_as_written)


def load_exact(source: str | Path) -> Any:
    """Parse YAML, preserving numeric scalars as their written text."""
    if isinstance(source, Path):
        with source.open("r", encoding="utf-8") as fh:
            return yaml.load(fh, Loader=ExactLoader)
    return yaml.load(source, Loader=ExactLoader)
