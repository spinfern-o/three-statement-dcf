#!/usr/bin/env python3
"""Item 37: build the extraction fixtures.

Specification 3.4.e asks for "golden-file fixtures for known PDFs and expected
normalized outputs". The PDFs are generated rather than downloaded, for three
reasons: a real filing is copyrighted, a real filing cannot be trimmed to
exercise one edge case at a time, and a generated file can be rebuilt byte for
byte to prove the extractor -- not the fixture -- changed.

The generated files ARE committed. `test_fixtures_are_unchanged` re-hashes them
so a PyMuPDF upgrade that changes the output is visible as a failing test
rather than as a silent difference in what the extractor was tested against.

Every figure below is fictional. See tests/fixtures/ for the same statement in
the calculation engine's own fixtures.

Run:  python apps/api/tests/fixtures/build_fixtures.py
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pymupdf

HERE = Path(__file__).resolve().parent

#: Fixed so the bytes are reproducible. PyMuPDF otherwise stamps the current
#: time into /CreationDate and every rebuild produces a different file.
METADATA = {
    "title": "Example Industries plc - Annual Report 2025",
    "author": "",
    "subject": "",
    "keywords": "",
    "creator": "",
    "producer": "",
    "creationDate": "D:20260101000000Z",
    "modDate": "D:20260101000000Z",
}

#: The base-14 Helvetica MuPDF ships with is Latin-1 only, and silently
#: substitutes a middle dot for every character outside it -- including the em
#: dash, which is the single most important glyph in these fixtures (10.17).
#: DejaVu covers what a filing prints. The fixtures are COMMITTED, so CI never
#: needs this font; only rebuilding does.
FONT_FILES = {
    "regular": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "bold": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
}
FONT = "DJ"
BOLD = "DJB"
LEFT = 56
PAGE_W, PAGE_H = 595, 842  # A4 in points


_MEASURE = {
    FONT: pymupdf.Font(fontfile=FONT_FILES["regular"]),
    BOLD: pymupdf.Font(fontfile=FONT_FILES["bold"]),
}


def _prepare(page) -> None:
    """Embed both faces on the page before any text is drawn."""
    page.insert_font(fontname=FONT, fontfile=FONT_FILES["regular"])
    page.insert_font(fontname=BOLD, fontfile=FONT_FILES["bold"])


def _text(page, x, y, value, *, size=9, font=FONT) -> None:
    page.insert_text((x, y), value, fontname=font, fontsize=size)


def _row(page, y, label, columns, *, size=9, font=FONT) -> None:
    """One statement row: a left-hand label and right-aligned figures."""
    _text(page, LEFT, y, label, size=size, font=font)
    for x, value in columns:
        width = _MEASURE[font].text_length(value, size)
        _text(page, x - width, y, value, size=size, font=font)


def _rule(page, y, x0=LEFT, x1=PAGE_W - 40) -> None:
    page.draw_line(pymupdf.Point(x0, y), pymupdf.Point(x1, y), width=0.5)


def _table_frame(page, top, bottom, columns) -> None:
    """Ruling lines. `find_tables()` reads these directly rather than inferring."""
    _rule(page, top)
    _rule(page, bottom)
    page.draw_line(pymupdf.Point(LEFT - 6, top), pymupdf.Point(LEFT - 6, bottom), width=0.5)
    for x in columns:
        page.draw_line(pymupdf.Point(x + 8, top), pymupdf.Point(x + 8, bottom), width=0.5)


COL_A, COL_B = 400, 500


def _finish(doc, path: Path) -> None:
    """Subset the embedded fonts and write deterministically.

    DejaVu unsubsetted is roughly 700 KB per file, which would put five
    megabytes of font data into the repository to test a dozen numbers.
    Subsetting keeps only the glyphs actually drawn.
    """
    doc.subset_fonts(verbose=False)
    doc.set_metadata(METADATA)
    doc.save(path, garbage=4, deflate=True, no_new_id=True)
    doc.close()


def build_statements(path: Path) -> None:
    """A three-page text-native filing with the edge cases the parser must face."""
    doc = pymupdf.open()

    # --- page 1: cover, carrying every field 10.10 asks to detect -----------
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    _prepare(page)
    _text(page, LEFT, 120, "EXAMPLE INDUSTRIES PLC", size=18, font=BOLD)
    _text(page, LEFT, 150, "Annual Report and Consolidated Financial Statements", size=12)
    _text(page, LEFT, 180, "For the fiscal year ended December 31, 2025", size=11)
    _text(page, LEFT, 220, "(All amounts in thousands of U.S. dollars, except share data)", size=9)
    _text(page, LEFT, 250, "Prepared in accordance with U.S. GAAP", size=9)
    _text(page, LEFT, 280, "Report of Independent Registered Public Accounting Firm", size=9)
    _text(page, LEFT, 310, "These financial statements have been audited.", size=9)
    _text(page, LEFT, 700, "Example Industries plc - Annual Report 2025 - Page 1", size=7)

    # --- page 2: income statement -------------------------------------------
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    _prepare(page)
    _text(page, LEFT, 80, "CONSOLIDATED STATEMENTS OF OPERATIONS", size=11, font=BOLD)
    _text(page, LEFT, 96, "(in thousands of U.S. dollars)", size=8)
    top = 112
    _table_frame(page, top, 320, [COL_A, COL_B])
    _row(page, 126, "", [(COL_A, "2025"), (COL_B, "2024")], font=BOLD)
    _rule(page, 132)
    rows = [
        ("Revenue", "1,250,000", "1,100,000"),
        ("Cost of goods sold", "(750,000)", "(660,000)"),
        ("Gross profit", "500,000", "440,000"),
        ("Selling, general and administrative", "(300,000)", "(270,000)"),
        ("Research and development", "(45,500)", "(40,250)"),
        ("Restructuring charges", "—", "(12,000)¹"),
        ("Operating income", "154,500", "117,750"),
        ("Interest expense", "(18,000)", "(20,000)"),
        ("Income before income taxes", "136,500", "97,750"),
        ("Income tax expense", "(34,125)", "(24,438)"),
        ("Net income", "102,375", "73,312"),
    ]
    y = 148
    for label, a, b in rows:
        _row(page, y, label, [(COL_A, a), (COL_B, b)])
        y += 15
    _text(page, LEFT, 340, "(1) Restructuring charges ceased in 2025; see Note 7.", size=7)
    _text(page, LEFT, 700, "Example Industries plc - Annual Report 2025 - Page 2", size=7)

    # --- page 3: balance sheet ----------------------------------------------
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    _prepare(page)
    _text(page, LEFT, 80, "CONSOLIDATED BALANCE SHEETS", size=11, font=BOLD)
    _text(page, LEFT, 96, "(in thousands of U.S. dollars)", size=8)
    top = 112
    _table_frame(page, top, 355, [COL_A, COL_B])
    _row(page, 126, "", [(COL_A, "2025"), (COL_B, "2024")], font=BOLD)
    _rule(page, 132)
    rows = [
        ("Cash and cash equivalents", "185,000", "142,000"),
        ("Accounts receivable, net", "205,000", "180,500"),
        ("Inventories", "160,000", "155,000"),
        ("Total current assets", "550,000", "477,500"),
        ("Property, plant and equipment, net", "620,000", "588,000"),
        ("Goodwill", "N/A", "–"),
        ("Total assets", "1,170,000", "1,065,500"),
        ("Accounts payable", "130,000", "121,000"),
        ("Long-term debt", "400,000", "425,000"),
        ("Total liabilities", "530,000", "546,000"),
        ("Common stock", "50,000", "50,000"),
        ("Retained earnings", "590,000", "469,500"),
        ("Total equity", "640,000", "519,500"),
        ("Total liabilities and equity", "1,170,000", "1,065,500"),
    ]
    y = 148
    for label, a, b in rows:
        _row(page, y, label, [(COL_A, a), (COL_B, b)])
        y += 15
    _text(page, LEFT, 700, "Example Industries plc - Annual Report 2025 - Page 3", size=7)

    _finish(doc, path)


def build_eu_locale(path: Path) -> None:
    """The same figures printed `1.234.567,89`. Ambiguous until locale is confirmed."""
    doc = pymupdf.open()
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    _prepare(page)
    _text(page, LEFT, 80, "KONZERN-GEWINN- UND VERLUSTRECHNUNG", size=11, font=BOLD)
    _text(page, LEFT, 96, "(in Tausend Euro)", size=8)
    _table_frame(page, 112, 200, [COL_A, COL_B])
    _row(page, 126, "", [(COL_A, "2025"), (COL_B, "2024")], font=BOLD)
    _rule(page, 132)
    rows = [
        ("Umsatzerloese", "1.250.000", "1.100.000"),
        ("Materialaufwand", "(750.000)", "(660.000)"),
        ("Rohergebnis", "500.000", "440.000"),
        ("Steuerquote", "25,5%", "25,0%"),
    ]
    y = 148
    for label, a, b in rows:
        _row(page, y, label, [(COL_A, a), (COL_B, b)])
        y += 15
    _finish(doc, path)


def build_image_only(path: Path) -> None:
    """A scanned page: one raster image, no text layer. Decision 2.3.c refuses it."""
    source = pymupdf.open()
    page = source.new_page(width=PAGE_W, height=PAGE_H)
    _prepare(page)
    _text(page, LEFT, 120, "SCANNED STATEMENT OF OPERATIONS", size=14, font=BOLD)
    _text(page, LEFT, 160, "Revenue                         1,250,000", size=10)
    pixmap = page.get_pixmap(dpi=72)
    source.close()

    doc = pymupdf.open()
    out = doc.new_page(width=PAGE_W, height=PAGE_H)
    out.insert_image(pymupdf.Rect(0, 0, PAGE_W, PAGE_H), pixmap=pixmap)
    _finish(doc, path)


def build_mixed(path: Path) -> None:
    """Text and an image region on one page. Extracted, with the gap recorded."""
    source = pymupdf.open()
    tmp = source.new_page(width=300, height=120)
    _prepare(tmp)
    _text(tmp, 10, 40, "CHART: revenue by segment", size=10)
    pixmap = tmp.get_pixmap(dpi=72)
    source.close()

    doc = pymupdf.open()
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    _prepare(page)
    _text(page, LEFT, 80, "SEGMENT INFORMATION", size=11, font=BOLD)
    _table_frame(page, 100, 160, [COL_A, COL_B])
    _row(page, 114, "", [(COL_A, "2025"), (COL_B, "2024")], font=BOLD)
    _rule(page, 120)
    _row(page, 136, "Industrial", [(COL_A, "800,000"), (COL_B, "700,000")])
    _row(page, 151, "Consumer", [(COL_A, "450,000"), (COL_B, "400,000")])
    page.insert_image(pymupdf.Rect(LEFT, 200, LEFT + 300, 320), pixmap=pixmap)
    _finish(doc, path)


def build_partly_scanned(path: Path) -> None:
    """Page 1 text-native, page 2 a scan. Refused, naming page 2 (ING-010-08).

    The realistic shape of the problem: a filing that is mostly text with one
    inserted scanned page. Extracting it and quietly omitting page 2 would look
    like a filing whose page 2 was blank.
    """
    source = pymupdf.open()
    scan = source.new_page(width=PAGE_W, height=PAGE_H)
    _prepare(scan)
    _text(scan, LEFT, 120, "SIGNED CERTIFICATION", size=14, font=BOLD)
    _text(scan, LEFT, 160, "Total liabilities                    530,000", size=10)
    pixmap = scan.get_pixmap(dpi=72)
    source.close()

    doc = pymupdf.open()
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    _prepare(page)
    _text(page, LEFT, 80, "CONSOLIDATED STATEMENTS OF OPERATIONS", size=11, font=BOLD)
    _text(page, LEFT, 96, "(in thousands of U.S. dollars)", size=8)
    _table_frame(page, 112, 180, [COL_A, COL_B])
    _row(page, 126, "", [(COL_A, "2025"), (COL_B, "2024")], font=BOLD)
    _rule(page, 132)
    _row(page, 148, "Revenue", [(COL_A, "1,250,000"), (COL_B, "1,100,000")])
    _row(page, 163, "Net income", [(COL_A, "102,375"), (COL_B, "73,312")])

    scanned = doc.new_page(width=PAGE_W, height=PAGE_H)
    scanned.insert_image(pymupdf.Rect(0, 0, PAGE_W, PAGE_H), pixmap=pixmap)
    _finish(doc, path)


def build_encrypted(path: Path) -> None:
    """Password-protected. Refused: the bytes cannot be read (ING-010-04)."""
    doc = pymupdf.open()
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    # Base-14 Helvetica, not DejaVu: this page holds one ASCII word, and
    # subsetting does not run on an encrypted document, so embedding a font
    # here costs most of a megabyte for nothing.
    _text(page, LEFT, 120, "CONFIDENTIAL", size=14, font="hebo")
    doc.set_metadata(METADATA)
    doc.save(
        path,
        encryption=pymupdf.PDF_ENCRYPT_AES_256,
        owner_pw="owner-secret",
        user_pw="user-secret",
        no_new_id=True,
    )
    doc.close()


def build_non_pdf(path: Path) -> None:
    """A `.pdf` that is not one. 10.1 refuses it by signature, not extension."""
    path.write_bytes(b"GIF89a\x01\x00\x01\x00\x00\xff\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x00;")


def build_truncated(path: Path, source: Path) -> None:
    """A complete PDF with its tail removed. Refused as incomplete (ING-010-02)."""
    data = source.read_bytes()
    path.write_bytes(data[: int(len(data) * 0.6)])


BUILDERS = {
    "text_native_statements.pdf": build_statements,
    "eu_locale_statements.pdf": build_eu_locale,
    "image_only_scan.pdf": build_image_only,
    "partly_scanned.pdf": build_partly_scanned,
    "mixed_text_and_image.pdf": build_mixed,
    "encrypted.pdf": build_encrypted,
    "not_actually_a_pdf.pdf": build_non_pdf,
}


def build_all(directory: Path = HERE) -> dict[str, str]:
    """Write every fixture and return {filename: sha256}."""
    for name, builder in BUILDERS.items():
        builder(directory / name)
    build_truncated(directory / "truncated.pdf", directory / "text_native_statements.pdf")

    digests = {}
    for name in sorted([*BUILDERS, "truncated.pdf"]):
        digests[name] = hashlib.sha256((directory / name).read_bytes()).hexdigest()
    return digests


#: AES-256 encryption salts each write at random, so `encrypted.pdf` hashes
#: differently every rebuild. It is committed like the rest, but excluded from
#: the golden-hash test rather than the test being weakened to accommodate it.
NOT_REPRODUCIBLE = frozenset({"encrypted.pdf"})


if __name__ == "__main__":
    for name, digest in build_all().items():
        print(f"{digest}  {name}")
    print(f"\npymupdf {pymupdf.__doc__.strip()}", file=sys.stderr)
