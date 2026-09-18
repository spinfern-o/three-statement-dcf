"""Items 27, 28 and 38: hashing, write-once storage, and byte-for-byte custody."""

from __future__ import annotations

import os

import pytest

from apps.api.app.core.errors import IngestionRefusal
from apps.api.app.extraction.hashing import check_duplicate, sha256_hex
from apps.api.app.extraction.storage import (
    MAX_FILENAME_LENGTH,
    SourceStore,
    sanitize_filename,
)

PAYLOAD = b"%PDF-1.7\nhello\n%%EOF\n"


def test_the_hash_is_of_the_bytes_as_received():
    assert sha256_hex(b"abc") == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


def test_a_duplicate_is_refused_by_default():
    with pytest.raises(IngestionRefusal) as exc:
        check_duplicate(PAYLOAD, existing_id_for_hash=lambda h: "doc-1")
    assert exc.value.reason.code == "ING-010-03"
    assert "doc-1" in exc.value.detail


def test_a_linked_duplicate_needs_an_explicit_reason():
    with pytest.raises(IngestionRefusal):
        check_duplicate(
            PAYLOAD, existing_id_for_hash=lambda h: "doc-1", allow_linked_duplicate=True
        )
    result = check_duplicate(
        PAYLOAD,
        existing_id_for_hash=lambda h: "doc-1",
        allow_linked_duplicate=True,
        link_reason="the filer reissued this document under a new cover",
    )
    assert result.linked and result.existing_document_id == "doc-1"


@pytest.mark.parametrize(
    "name, expected",
    [
        ("../../etc/passwd", "passwd"),
        ("C:\\Users\\x\\rpt.pdf", "rpt.pdf"),
        ("weird\x00name.pdf", "weird_name.pdf"),
        ("FY2025 10-K.pdf", "FY2025 10-K.pdf"),
    ],
)
def test_filenames_are_sanitized(name, expected):
    assert sanitize_filename(name) == expected


def test_non_ascii_filenames_survive():
    """A filing named in another script is not less legitimate."""
    assert sanitize_filename("Jahresabschluss \u00fcber 2025.pdf") == "Jahresabschluss \u00fcber 2025.pdf"


def test_long_filenames_are_truncated_but_keep_their_suffix():
    name = sanitize_filename("a" * 400 + ".pdf")
    assert len(name) == MAX_FILENAME_LENGTH
    assert name.endswith(".pdf")


@pytest.mark.parametrize("name", ["  ..  ", ".....", "///"])
def test_filenames_with_nothing_safe_left_are_refused(name):
    with pytest.raises(IngestionRefusal) as exc:
        sanitize_filename(name)
    assert exc.value.reason.code == "ING-020-11"


def test_storage_is_content_addressed_and_verified(tmp_path):
    store = SourceStore(tmp_path)
    stored = store.store(PAYLOAD, original_filename="x.pdf")
    assert stored.immutable_hash in stored.path.name
    assert stored.path.read_bytes() == PAYLOAD
    assert store.verify(stored.immutable_hash)


def test_item_38_the_original_is_unchanged(tmp_path):
    """Item 38, measured: the stored bytes hash to what was uploaded."""
    store = SourceStore(tmp_path)
    before = sha256_hex(PAYLOAD)
    stored = store.store(PAYLOAD, original_filename="x.pdf")
    assert sha256_hex(stored.path.read_bytes()) == before
    assert store.read(before) == PAYLOAD


def test_restoring_identical_bytes_writes_nothing(tmp_path):
    store = SourceStore(tmp_path)
    first = store.store(PAYLOAD, original_filename="x.pdf")
    mtime = first.path.stat().st_mtime_ns
    second = store.store(PAYLOAD, original_filename="different-name.pdf")
    assert second.already_present
    assert second.path.stat().st_mtime_ns == mtime


def test_stored_files_are_read_only(tmp_path):
    store = SourceStore(tmp_path)
    stored = store.store(PAYLOAD, original_filename="x.pdf")
    assert oct(os.stat(stored.path).st_mode & 0o777) == "0o444"


def test_tampering_is_detected_even_though_root_can_write(tmp_path):
    """Mode 0444 is defence in depth. The hash is the guarantee."""
    store = SourceStore(tmp_path)
    stored = store.store(PAYLOAD, original_filename="x.pdf")
    os.chmod(stored.path, 0o644)
    stored.path.write_bytes(b"%PDF-1.7\ntampered\n%%EOF\n")
    assert not store.verify(stored.immutable_hash)
    with pytest.raises(IngestionRefusal) as exc:
        store.read(stored.immutable_hash)
    assert exc.value.reason.code == "ING-010-12"


def test_a_hash_collision_path_is_refused_not_overwritten(tmp_path):
    """Rule 1.12. The store never replaces bytes it already holds."""
    store = SourceStore(tmp_path)
    stored = store.store(PAYLOAD, original_filename="x.pdf")
    os.chmod(stored.path, 0o644)
    stored.path.write_bytes(b"different")
    with pytest.raises(IngestionRefusal) as exc:
        store.store(PAYLOAD, original_filename="x.pdf")
    assert exc.value.reason.code == "ING-010-12"


def test_path_for_refuses_anything_that_is_not_a_digest(tmp_path):
    store = SourceStore(tmp_path)
    with pytest.raises(ValueError):
        store.path_for("../../etc/passwd")
