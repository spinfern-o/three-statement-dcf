#!/usr/bin/env python3
"""Run the source-review application -- specification Phase 4.

    python3 review_server.py                       # ./var/sources, port 8000
    python3 review_server.py --store var/sources --port 8080

Ingest a filing first; this reads what the extractor produced and has no
upload form of its own yet:

    python3 ingest_pdf.py FILING.pdf --store var/sources

**It binds to localhost and has no authentication.** Decision 2.2.c requires
authentication for the hosted deployment, and it is not built -- see the note
in docs/decision-ledger.md. Until it is, this is a local review tool over
confidential filings, and putting it on a network interface would be putting
those filings on a network with no credential in front of them.
"""

from __future__ import annotations

import argparse
from pathlib import Path

DEFAULT_STORE = Path("var/sources")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE,
                        help=f"the immutable source store to review (default {DEFAULT_STORE})")
    parser.add_argument("--host", default="127.0.0.1",
                        help="bind address. Leave it on localhost until 2.2.c's "
                             "authentication exists")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)

    import uvicorn

    from apps.api.app.api.main import create_app

    if args.host not in ("127.0.0.1", "localhost", "::1"):
        print(
            f"\nWARNING: binding to {args.host}. This application has no "
            f"authentication (decision 2.2.c is unimplemented) and serves "
            f"confidential filings.\n"
        )

    app = create_app(args.store)
    print(f"Reviewing {args.store.resolve()}  ->  http://{args.host}:{args.port}/")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
