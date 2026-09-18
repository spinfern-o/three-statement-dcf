#!/usr/bin/env python3
"""Ingest a PDF filing and report what was extracted -- Phase 3 of the build spec.

    python3 ingest_pdf.py FILING.pdf
    python3 ingest_pdf.py FILING.pdf --store ./var/sources --company acme
    python3 ingest_pdf.py FILING.pdf --confirm-metadata     # show 10.13's effect
    python3 ingest_pdf.py FILING.pdf --facts 20 --json out.json

This is the ingestion half of the system. It does not build a model: the
calculation engine begins at STEP 4 with figures a human has verified, and
`run_model.py` is its entry point. Between them sit source review -- built,
and served by `review_server.py` -- and mapping, which is Phase 5 and is not.

Exit status
    0  extracted
    1  refused by a rule -- the message names which one
    2  a usage or environment problem
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from apps.api.app.core.config import IngestionConfig
from apps.api.app.extraction import report
from apps.api.app.extraction.pipeline import ingest
from apps.api.app.extraction.records import confirm_metadata
from apps.api.app.extraction.storage import SourceStore
from apps.api.app.persistence.json_store import JsonDocumentRepository
from apps.api.app.security.logging import security_event
from apps.api.app.security.scanning import quarantine, scan

DEFAULT_STORE = Path("var/sources")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("pdf", type=Path, help="the filing to ingest")
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE,
                        help=f"immutable source store (default {DEFAULT_STORE})")
    parser.add_argument("--company", default="default",
                        help="company identifier; duplicate detection is scoped to it (10.3)")
    parser.add_argument("--facts", type=int, default=None,
                        help="show only the first N facts")
    parser.add_argument("--confirm-metadata", action="store_true",
                        help="accept every detected metadata field and re-run what depends "
                             "on it (10.13, 10.35). Demonstration only -- a real "
                             "confirmation is a reviewer decision per field")
    parser.add_argument("--linked-duplicate", metavar="REASON", default=None,
                        help="record an explicit linked duplicate of an existing upload (10.3)")
    parser.add_argument("--no-save", action="store_true", help="do not write records to disk")
    args = parser.parse_args(argv)

    if not args.pdf.exists():
        print(f"no such file: {args.pdf}", file=sys.stderr)
        return 2

    config = IngestionConfig(storage_root=str(args.store))
    store = SourceStore(args.store)
    repository = JsonDocumentRepository(args.store)

    # 20.9: scan before anything parses the bytes, and quarantine rather than
    # delete a file that fails, so the refusal stays auditable. With no scanner
    # configured this reports NOT SCANNED and proceeds -- it never reports
    # clean for a file nothing looked at.
    scan_result = scan(args.pdf)
    if not scan_result.may_process:
        scan_result = quarantine(args.pdf, args.store, scan_result)
        print(f"\n{report.rule('=')}")
        print("UPLOAD REFUSED BY THE SCANNER (20.9)")
        print(report.rule('='))
        print(f"  {scan_result.describe()}")
        print(f"  quarantined at: {scan_result.quarantined_at}")
        security_event(
            "upload.refused", actor=args.company, outcome="refused",
            detail=scan_result.describe(), document_id=args.pdf.name,
        )
        return 2
    if not scan_result.outcome.is_known:
        print(f"\n  NOTE: {scan_result.describe()}\n")

    outcome = ingest(
        args.pdf.read_bytes(),
        original_filename=args.pdf.name,
        company_id=args.company,
        config=config,
        store=store,
        existing_id_for_hash=repository.lookup_for(args.company),
        allow_linked_duplicate=args.linked_duplicate is not None,
        link_reason=args.linked_duplicate,
    )

    print(report.job_block(tuple(t.describe() for t in outcome.job.history)))

    if not outcome.accepted:
        refusal = outcome.refusal
        print(f"\n{report.rule('=')}")
        print("UPLOAD REFUSED")
        print(report.rule('='))
        print(f"\n  {refusal.reason.code}  (specification {refusal.reason.rule})")
        print(f"  {refusal.reason.summary}\n")
        print(f"  {refusal.detail}\n")
        print("  Nothing was extracted. The refusal is the specified outcome, not a failure.")
        return 1

    result = outcome.result
    if args.confirm_metadata:
        detected = {
            name: None
            for name, field in result.document.metadata.fields.items()
            if field.value is not None
        }
        before = len(result.facts_needing_review)
        result = confirm_metadata(
            result, detected, actor="owner",
            reason="--confirm-metadata: every detected value accepted as printed",
        )
        after = len(result.facts_needing_review)
        print(f"\n  [--confirm-metadata] {len(detected)} field(s) confirmed; "
              f"facts needing review {before} -> {after} (10.35)")

    print(report.document_block(result))
    print(report.pages_block(result.document.pages))
    print(report.metadata_block(result.document.metadata))
    print(report.tables_block(result))
    print(report.facts_block(result, limit=args.facts))
    print(report.confidence_block(result))
    print(report.review_block(result))
    print(report.audit_block(result))

    if not args.no_save:
        path = repository.save(result)
        print(f"\nRecords written to {path}")

    print(
        f"\n{report.rule()}\n"
        f"{len(result.facts)} fact(s) extracted, "
        f"{len(result.facts_needing_review)} awaiting review.\n"
        f"Review them in a browser:  python3 review_server.py --store {args.store}\n"
        f"No fact is VERIFIED: that needs a reviewer action (Phase 4, built) AND an\n"
        f"approved mapping (Phase 5, not built).\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
