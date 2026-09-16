"""Application code for the website described in docs/website-build-spec.md.

Specification Section 5 asks for `apps/api/app/...`. This repository has no
packaging configuration -- `model/` and `run_model.py` are imported from the
repository root -- so `apps` and `apps/api` are real packages rather than bare
directories, and the import path is `apps.api.app.extraction.<module>`.
"""
