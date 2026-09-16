"""PDF ingestion and extraction -- specification Section 10, Phase 3.

Module map, against the Phase 3 items in specification Section 23:

    26  signature.py    PDF signature validation
    27  hashing.py      immutable hash and duplicate detection
    28  storage.py      safe, write-once storage
    29  jobs.py         extraction job states
    30  text_native.py  text-native extraction
    31  pages.py        page classification; image-only is REFUSED (2.3.c)
    32  geometry.py     page geometry and source locations
    33  records.py      raw table and fact records
    34  metadata.py     metadata detection, UNCONFIRMED
    35  parsing.py      unit, sign and locale parsing
    36  reasons.py      confidence and reason codes
    37  (tests)         apps/api/tests
    38  storage.py      the original PDF is never modified

One boundary is worth stating once, loudly, because it is the only place in
this repository where a binary float is permitted to exist:

    PAGE GEOMETRY ARRIVES AS FLOAT AND IS CONVERTED AT THE BOUNDARY.

PyMuPDF returns bounding boxes as Python floats. They are converted to Decimal
once, in `geometry.py`, and quantized to 0.001 PDF points. No financial value
is ever derived from them -- a fact's value comes from its `raw_value` string
through `parsing.py`, never from a coordinate. `geometry.py` says the same
thing at greater length.
"""
