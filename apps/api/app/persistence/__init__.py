"""Record storage.

Specification 3.2.d requires PostgreSQL for a hosted deployment, and decision
2.2.a is private hosted. PostgreSQL is Phase 15/17 work and is NOT wired here.
Phase 3 needs somewhere to put records so the pipeline can be run and tested
end to end, so this package defines the repository interface and one JSON-file
implementation of it. Swapping in PostgreSQL means implementing the same
protocol, not rewriting the extraction code.
"""
