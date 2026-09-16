"""Item 33 (persistence): record storage, in JSON, behind a protocol.

Specification 3.2.d requires PostgreSQL for a hosted deployment and decision
2.2.a is private hosted, so PostgreSQL is where this ends up. It is Phase 15/17
work and nothing here pretends otherwise. What Phase 3 needs is somewhere to
put a `SourceDocument`, its tables, its locations, its facts and its audit
trail, so that duplicate detection works across runs (10.3) and an extraction
can be read back.

The contract is `DocumentRepository`. Everything above it -- the pipeline, the
CLI -- depends on the protocol, not on JSON, so a PostgreSQL implementation is
a new class rather than a rewrite.

**Every number is written as a string** (4.2). A `Decimal` serialized through
`json` with `float` would lose exactly what `model/numeric.py` exists to
protect, so `_jsonable` refuses floats outright rather than converting them.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Protocol

from ..extraction.records import ExtractionResult


class SerializationError(TypeError):
    """A value reached the serializer in a form that would lose information."""


def _jsonable(value: object) -> object:
    """Convert to JSON-safe types. Decimals become strings; floats are refused."""
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        raise SerializationError(
            f"a float ({value!r}) reached the record serializer. Specification "
            f"4.2 requires monetary values cross boundaries as decimal strings, "
            f"and writing this would store {Decimal(value)}."
        )
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: _jsonable(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(v) for v in value]
    raise SerializationError(f"cannot serialize {type(value).__name__}: {value!r}")


class DocumentRepository(Protocol):
    """What the pipeline needs from storage. Implement this for PostgreSQL."""

    def id_for_hash(self, company_id: str, immutable_hash: str) -> str | None:
        """10.3. The existing document with this hash for this company, if any."""

    def save(self, result: ExtractionResult) -> Path:
        """Persist one extraction."""

    def load(self, document_id: str) -> dict:
        """Read one extraction back as plain data."""

    def document_ids(self) -> tuple[str, ...]:
        """Every stored document, oldest first."""


class JsonDocumentRepository:
    """A file-per-document repository. Single-user, which 2.2.b confirms."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root) / "records"
        self.root.mkdir(parents=True, exist_ok=True)

    @property
    def index_path(self) -> Path:
        return self.root / "index.json"

    def _index(self) -> dict[str, str]:
        if not self.index_path.exists():
            return {}
        return json.loads(self.index_path.read_text())

    @staticmethod
    def _key(company_id: str, immutable_hash: str) -> str:
        return f"{company_id}:{immutable_hash}"

    def id_for_hash(self, company_id: str, immutable_hash: str) -> str | None:
        return self._index().get(self._key(company_id, immutable_hash))

    def lookup_for(self, company_id: str):
        """A callable for `pipeline.ingest`'s `existing_id_for_hash`."""
        return lambda digest: self.id_for_hash(company_id, digest)

    def save(self, result: ExtractionResult) -> Path:
        document = result.document
        path = self.root / f"{document.id}.json"
        payload = {
            "document": _jsonable(document),
            "tables": _jsonable(result.tables),
            "locations": _jsonable(result.locations),
            "facts": _jsonable(result.facts),
            "audit": _jsonable(result.audit),
            "job_history": list(result.job_history),
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False))

        index = self._index()
        index[self._key(document.company_id, document.immutable_hash)] = document.id
        self.index_path.write_text(json.dumps(index, indent=2, sort_keys=True))
        return path

    def load(self, document_id: str) -> dict:
        return json.loads((self.root / f"{document_id}.json").read_text())

    def document_ids(self) -> tuple[str, ...]:
        return tuple(sorted(p.stem for p in self.root.glob("doc-*.json")))
