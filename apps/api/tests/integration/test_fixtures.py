"""Item 37: the fixtures themselves are golden files.

Specification 3.4.e asks for golden-file fixtures. A golden file that can
change without anyone noticing is not one, so the committed PDFs are hashed
here. A failure means either the fixtures were edited or PyMuPDF's output
changed -- both of which alter what the extractor is tested against, and both
of which should be a decision rather than a surprise.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

#: Regenerate with: python apps/api/tests/fixtures/build_fixtures.py
GOLDEN = {
    "eu_locale_statements.pdf": "4df1f5e764b1ac63f0ee34e3caf66d0f2c8075321eed9531f576469ff734ed2d",
    "image_only_scan.pdf": "da7aef992df10327bc1d8fcfd4299f7c2d2d93da3b3142465ce30081792caf06",
    "mixed_text_and_image.pdf": "489b0f73f79d218722e6000b307cd6864d274bb82e23731c8b8bc95069f9df71",
    "not_actually_a_pdf.pdf": "3b7b8a4b411ddf8db9bacc2f3aabf406f8e4c0c087829b336ca331c40adfdff1",
    "partly_scanned.pdf": "dc3a34921d20e18c31a644cb15314c88f5ddd8eae504c8c91b3baf3817f616ce",
    "text_native_statements.pdf": "01c5c71b8e358d52ea46d0012f240f20dae0097a9c1a69a3814a8818f28076c6",
    "three_statements.pdf": "d4a527796b7cf58f95f6a4cb9600ddc79b86c4f1ff9a6b1935313b372ae37ae7",
    "forecastable.pdf": "90001dccbf686aa7d8a1bdde4d57dc08b49a686f8724ea03a76c2dbb7bb55f95",
    "truncated.pdf": "a816c02f2bacf367015727e1e55b48c551c3d04d9c14003700dbb99277ef2e93",
}

#: AES-256 salts every write at random, so this one cannot be pinned. It is
#: excluded by name rather than by weakening the test for everything else.
NOT_REPRODUCIBLE = {"encrypted.pdf"}


@pytest.mark.parametrize("name, digest", sorted(GOLDEN.items()))
def test_fixture_is_unchanged(name, digest):
    data = (FIXTURES / name).read_bytes()
    assert hashlib.sha256(data).hexdigest() == digest, (
        f"{name} differs from the committed golden file. Rebuild it with "
        f"apps/api/tests/fixtures/build_fixtures.py and update GOLDEN "
        f"deliberately, rather than to make this pass."
    )


def test_every_fixture_is_accounted_for():
    on_disk = {p.name for p in FIXTURES.glob("*.pdf")}
    assert on_disk == set(GOLDEN) | NOT_REPRODUCIBLE


def test_the_encrypted_fixture_exists_even_though_it_is_not_pinned():
    assert (FIXTURES / "encrypted.pdf").exists()
