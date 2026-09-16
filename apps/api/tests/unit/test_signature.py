"""Item 26. Specification 10.1: type by signature, never by filename."""

from __future__ import annotations

import pytest

from apps.api.app.core.errors import IngestionRefusal
from apps.api.app.extraction.signature import detect_mime_type, validate_signature

MINIMAL = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


def test_a_complete_pdf_passes():
    result = validate_signature(MINIMAL, max_bytes=1_000_000)
    assert result.pdf_version == "1.7"
    assert result.byte_size == len(MINIMAL)
    assert result.eof_at_end


def test_the_filename_is_never_consulted(tmp_path):
    """A GIF named .pdf is a GIF. This is the whole point of 10.1."""
    gif = b"GIF89a\x01\x00\x01\x00\x00\xff\x00,\x00;"
    with pytest.raises(IngestionRefusal) as exc:
        validate_signature(gif, max_bytes=1_000_000)
    assert exc.value.reason.code == "ING-010-01"
    assert detect_mime_type(gif) == "application/octet-stream"


def test_a_header_at_a_nonzero_offset_is_refused_and_the_offset_is_named():
    with pytest.raises(IngestionRefusal) as exc:
        validate_signature(b"JUNK" + MINIMAL, max_bytes=1_000_000)
    assert "offset 4" in exc.value.detail


def test_truncation_is_refused_rather_than_partially_parsed():
    with pytest.raises(IngestionRefusal) as exc:
        validate_signature(MINIMAL[:20], max_bytes=1_000_000)
    assert exc.value.reason.code == "ING-010-02"


def test_an_empty_upload_is_refused():
    with pytest.raises(IngestionRefusal) as exc:
        validate_signature(b"", max_bytes=1_000_000)
    assert "empty" in exc.value.detail


def test_the_size_limit_is_enforced():
    with pytest.raises(IngestionRefusal) as exc:
        validate_signature(MINIMAL, max_bytes=8)
    assert exc.value.reason.code == "ING-020-08"


def test_a_bad_version_marker_is_refused():
    with pytest.raises(IngestionRefusal):
        validate_signature(b"%PDF-XX\n%%EOF\n", max_bytes=1000)


@pytest.mark.parametrize("version", [b"1.4", b"1.7", b"2.0"])
def test_supported_versions_are_recorded(version):
    data = b"%PDF-" + version + b"\n%%EOF\n"
    assert validate_signature(data, max_bytes=1000).pdf_version == version.decode()
