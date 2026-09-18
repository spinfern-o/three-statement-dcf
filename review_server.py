#!/usr/bin/env python3
"""Run the source-review application -- specification Phase 4.

    python3 review_server.py                       # ./var/sources, port 8000
    python3 review_server.py --store var/sources --port 8080

Ingest a filing first; this reads what the extractor produced and has no
upload form of its own yet:

    python3 ingest_pdf.py FILING.pdf --store var/sources

Authentication is decision 2.2.c and is built (Phase 15, item 145). Set the
credential before binding anywhere but localhost:

    python3 -m apps.api.app.security.credentials        # prints the hash
    python3 -m apps.api.app.security.credentials --key  # prints a signing key

Without REVIEW_PASSWORD_HASH this server runs in local-review mode, says so on
every page, and **refuses** to bind to anything but loopback. That is not a
warning any more: a confidential filing on a network interface with nothing in
front of it is the thing 20.1 and 2.2.c exist to prevent, and a warning is a
thing people scroll past.
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
                        help="bind address. Anything but loopback requires "
                             "REVIEW_PASSWORD_HASH to be set (2.2.c)")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)

    import uvicorn

    from apps.api.app.api.main import create_app
    from apps.api.app.security.credentials import Credential, CredentialError
    from apps.api.app.security.logging import configure as configure_security_log

    loopback = args.host in ("127.0.0.1", "localhost", "::1")
    try:
        credential = Credential.load()
    except CredentialError as exc:
        print(f"\nRefused: {exc}\n")
        return 2

    if credential is None and not loopback:
        print(
            f"\nRefused: binding to {args.host} with no credential configured.\n"
            f"This server holds a filing that has not been released (20.1), and "
            f"decision 2.2.c requires a credential in front of it.\n\n"
            f"    python3 -m apps.api.app.security.credentials\n"
            f"    python3 -m apps.api.app.security.credentials --key\n\n"
            f"then set REVIEW_PASSWORD_HASH and REVIEW_SECRET_KEY, or bind to "
            f"127.0.0.1.\n"
        )
        return 2

    configure_security_log()
    if credential is None:
        print(
            "\nLocal review mode: no credential configured, serving to "
            "loopback only. Every page says so.\n"
        )

    app = create_app(args.store)
    print(f"Reviewing {args.store.resolve()}  ->  http://{args.host}:{args.port}/")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
