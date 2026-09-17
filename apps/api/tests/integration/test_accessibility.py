"""Item 49 and specification 22.7: keyboard and screen-reader workflows.

22.7 asks for six things: a keyboard-only full workflow, screen-reader labels,
focus order, colour contrast, zoom to 200%, and reduced motion. Contrast is
tested against the token file in `unit/test_design_tokens.py`; the other five
need a real browser, and this module drives one.

**No axe.** An automated rule engine would need fetching, and decisions 2.3.d
and 2.3.e close outbound network access. What runs instead is narrower and, for
these six requirements, stronger: Playwright's ARIA locators resolve an
element the way assistive technology does, so `get_by_role("button",
name="Accept")` failing means the button has no accessible name -- which is the
finding axe would have reported, arrived at through the same accessibility
tree.

The whole module skips cleanly when the browser is unavailable, so CI without
one stays green rather than red for the wrong reason.
"""

from __future__ import annotations

import socket
import threading
from pathlib import Path

import pytest

from apps.api.tests.conftest import STATEMENTS

#: Some environments ship a Chromium at a fixed path and forbid downloading
#: another. Where that exists it is used; otherwise Playwright resolves the
#: browser it manages itself. Only when neither works does the suite skip.
BUNDLED_CHROMIUM = Path("/opt/pw-browsers/chromium")

pytest.importorskip("playwright.sync_api", reason="playwright is not installed")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def served(tmp_path_factory):
    """Ingest a filing, then serve the review application on a real port."""
    import uvicorn

    from apps.api.app.api.main import create_app
    from apps.api.app.core.config import IngestionConfig
    from apps.api.app.extraction.pipeline import ingest
    from apps.api.app.extraction.storage import SourceStore
    from apps.api.app.persistence.json_store import JsonDocumentRepository

    root = tmp_path_factory.mktemp("served")
    config = IngestionConfig(storage_root=str(root))
    store = SourceStore(root)
    repository = JsonDocumentRepository(root)
    outcome = ingest(
        Path(STATEMENTS).read_bytes(),
        original_filename=Path(STATEMENTS).name,
        company_id="co-1",
        config=config,
        store=store,
    )
    assert outcome.accepted
    repository.save(outcome.result)

    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(create_app(root), host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(200):
        if server.started:
            break
        threading.Event().wait(0.05)
    assert server.started, "the review server did not start"

    yield {
        "base": f"http://127.0.0.1:{port}",
        "document_id": outcome.result.document.id,
        "repository": repository,
    }

    server.should_exit = True
    thread.join(timeout=10)


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright

    # --no-sandbox because CI containers run as root.
    options = {"args": ["--no-sandbox"]}
    if BUNDLED_CHROMIUM.exists():
        # A bundled build may not match this Playwright's expected revision, so
        # name it rather than letting the resolver go looking for another.
        options["executable_path"] = str(BUNDLED_CHROMIUM)

    with sync_playwright() as pw:
        try:
            instance = pw.chromium.launch(**options)
        except PlaywrightError as exc:  # pragma: no cover - environment dependent
            pytest.skip(f"no usable Chromium: {exc}")
        yield instance
        instance.close()


@pytest.fixture
def page(browser, served):
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()
    page.goto(f"{served['base']}/documents/{served['document_id']}/pages/2")
    yield page
    context.close()


def _navigating(page):
    """Wait for the navigation a submission causes.

    `wait_for_load_state("networkidle")` is the wrong tool here: it can resolve
    against the page you are still on, before the new one starts loading, and
    the test then asserts against stale content.
    """
    return page.expect_navigation()


# --- 22.7.a: a keyboard-only full workflow ---------------------------------

def test_the_skip_link_is_the_first_thing_tab_reaches(page):
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.className") == "skip-link"
    assert page.evaluate("document.activeElement.textContent").strip() == "Skip to main content"


def test_the_skip_link_moves_past_the_header(page):
    page.keyboard.press("Tab")
    page.keyboard.press("Enter")
    page.wait_for_function("() => window.location.hash === '#main'")
    assert page.evaluate("window.location.hash") == "#main"


def test_a_reviewer_can_confirm_metadata_with_the_keyboard_alone(page, served):
    """The real 22.7.a test: no mouse, from load to a recorded decision."""
    reason = page.get_by_label("Reason", exact=False).first
    reason.focus()
    page.keyboard.type("checked the cover page")
    with _navigating(page):
        page.keyboard.press("Enter")  # implicit submission, as a keyboard user expects

    assert "All required fields confirmed" in page.content()
    result = served["repository"].load_result(served["document_id"])
    assert result.document.metadata.all_required_confirmed


def test_a_reviewer_can_accept_a_fact_with_the_keyboard_alone(page, served):
    page.get_by_label("Reason", exact=False).first.focus()
    page.keyboard.type("checked the cover page")
    with _navigating(page):
        page.keyboard.press("Enter")

    # Now the first fact's form. Tab from its reason field to the Accept button.
    form = page.locator("tbody[id^='fact-'] form.decide").first
    form.locator("input[name='reason']").focus()
    page.keyboard.type("matches the printed page")
    page.keyboard.press("Tab")  # to the corrected-value field
    page.keyboard.press("Tab")  # to Accept
    focused = page.evaluate("document.activeElement.value")
    assert focused == "accept", f"expected the Accept button, got {focused!r}"
    with _navigating(page):
        page.keyboard.press("Enter")

    assert "Recorded: accept" in page.content()
    result = served["repository"].load_result(served["document_id"])
    assert any(f.decision is not None for f in result.facts)


def test_a_refusal_is_announced_not_silent(page, served):
    """A keyboard user must not have to hunt for why nothing happened."""
    page.get_by_label("Reason", exact=False).first.focus()
    page.keyboard.type("confirming")
    with _navigating(page):
        page.keyboard.press("Enter")

    dash_form = page.locator("tbody", has_text="Restructuring charges").locator("form.decide").first
    dash_form.locator("input[name='reason']").fill("it is zero")
    with _navigating(page):
        dash_form.get_by_role("button", name="Accept").click()

    alert = page.get_by_role("alert")
    assert alert.count() >= 1
    assert "no value to accept" in alert.first.inner_text()


# --- 22.7.b: screen-reader labels ------------------------------------------

def test_every_interactive_control_has_an_accessible_name(page):
    """The accessibility tree is what a screen reader reads. Empty names fail."""
    unnamed = page.evaluate(
        """() => {
          const named = el => (
            el.getAttribute('aria-label') ||
            (el.labels && el.labels.length && el.labels[0].textContent.trim()) ||
            el.textContent.trim() ||
            el.getAttribute('title') ||
            el.getAttribute('alt')
          );
          return [...document.querySelectorAll('button, a[href], input:not([type=hidden]), select, textarea')]
            .filter(el => !named(el))
            .map(el => el.outerHTML.slice(0, 120));
        }"""
    )
    assert not unnamed, f"controls with no accessible name: {unnamed}"


def test_the_action_buttons_resolve_by_role_and_name(page):
    for name in ("Accept", "Correct", "Reject"):
        assert page.get_by_role("button", name=name).count() > 0, name


def test_the_landmarks_resolve(page):
    assert page.get_by_role("banner").count() == 1
    assert page.get_by_role("main").count() == 1
    assert page.get_by_role("contentinfo").count() == 1
    assert page.get_by_role("navigation").count() >= 1


def test_the_page_image_is_described(page):
    """22.7.b. The image is evidence; a blank alt would hide that it exists."""
    alt = page.locator(".page-frame img").get_attribute("alt")
    assert alt and "Page 2" in alt


def test_the_progress_meter_reads_as_text(page):
    labels = page.evaluate(
        "() => [...document.querySelectorAll('[role=img]')].map(e => e.getAttribute('aria-label'))"
    )
    assert any(label and "percent" in label for label in labels), labels


# --- 22.7.c: focus order ----------------------------------------------------

def test_no_positive_tabindex_overrides_the_document_order(page):
    """A positive tabindex is how focus order stops matching reading order."""
    offenders = page.evaluate(
        "() => [...document.querySelectorAll('[tabindex]')]"
        ".filter(e => parseInt(e.getAttribute('tabindex'), 10) > 0).length"
    )
    assert offenders == 0


def test_focus_moves_down_the_page_not_around_it(page):
    """Tab order follows visual order WITHIN the main region.

    Scoped to `<main>` deliberately. Since the persistent left navigation
    (6.3.a), the document order is navigation then content, and the last
    navigation link sits visually above the first content control -- so a
    document-wide version of this test reads that as a backwards jump. It is
    not: nav-before-content is the correct reading order across landmarks, and
    is the reason a skip link exists at all. The next test asserts that
    ordering directly, so the property is still covered.
    """
    positions = page.evaluate(
        """() => {
          const focusable = [...document.querySelectorAll(
            'main a[href], main button, main input:not([type=hidden]),'
            + ' main select, main textarea'
          )].filter(el => el.offsetParent !== null);
          return focusable.map(el => Math.round(el.getBoundingClientRect().top));
        }"""
    )
    assert positions, "nothing focusable in the main region"
    backwards = [
        (a, b) for a, b in zip(positions, positions[1:]) if b < a - 60
    ]
    assert not backwards, f"focus jumps back up the page at: {backwards[:3]}"


def test_the_navigation_comes_before_the_content_and_the_skip_link_before_both(page):
    """The ordering the test above no longer asserts, asserted here.

    A reviewer tabbing into the page meets the skip link first, so the
    navigation can be skipped in one keystroke; that is the whole arrangement
    a persistent left navigation depends on.
    """
    order = page.evaluate(
        """() => {
          const nodes = [...document.querySelectorAll('.skip-link, nav.shell-nav, main')];
          return nodes.map(n => n.tagName + '.' + (n.className || ''));
        }"""
    )
    assert order == ["A.skip-link", "NAV.shell-nav", "MAIN.layout"], order


def test_focus_is_always_visible(page):
    """6.5.d. An outline removed and not replaced is an invisible caret."""
    page.get_by_role("button", name="Accept").first.focus()
    outline = page.evaluate(
        "() => { const s = getComputedStyle(document.activeElement); "
        "return [s.outlineStyle, s.outlineWidth]; }"
    )
    assert outline[0] != "none", "the focused control has no outline"
    assert outline[1] not in ("0px", ""), "the focused control's outline has no width"


# --- 22.7.e: zoom to 200% ---------------------------------------------------

def test_the_layout_does_not_scroll_sideways_at_200_percent(browser, served):
    """Halving the viewport is equivalent to doubling the zoom."""
    context = browser.new_context(viewport={"width": 720, "height": 900})
    page = context.new_page()
    page.goto(f"{served['base']}/documents/{served['document_id']}/pages/2")
    overflow = page.evaluate(
        "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    assert overflow <= 2, f"{overflow}px of horizontal scroll at 200% zoom"
    context.close()


# --- 22.7.f: reduced motion -------------------------------------------------

def test_reduced_motion_is_honoured(browser, served):
    context = browser.new_context(reduced_motion="reduce")
    page = context.new_page()
    page.goto(f"{served['base']}/documents/{served['document_id']}/pages/2")
    # 0.01ms comes back as "1e-05s", so parse rather than string-compare.
    durations = page.evaluate(
        """() => [...document.querySelectorAll('*')]
             .map(e => parseFloat(getComputedStyle(e).transitionDuration) || 0)
             .filter(d => d > 0.0001)"""
    )
    assert not durations, f"transitions still running under reduced motion: {durations[:3]}"
    context.close()


# --- 7.6: the supporting schedules screen ----------------------------------

@pytest.fixture(scope="module")
def served_forecast(tmp_path_factory, forecastable):
    """The forecastable filing, served with an approved base scenario.

    The forecast screen needs a scenario that passes the 14.1 gate, and
    `served_schedules` deliberately does not have one. Testing 200% zoom
    against a "nothing to forecast yet" page proves nothing.
    """
    import uvicorn

    from apps.api.app.api.main import create_app
    from apps.api.app.assumptions.store import ScenarioStore
    from apps.api.app.extraction.storage import SourceStore
    from apps.api.app.persistence.json_store import JsonDocumentRepository
    from apps.api.tests.conftest import FORECASTABLE, approved_scenario

    root = tmp_path_factory.mktemp("served-forecast")
    JsonDocumentRepository(root).save(forecastable)
    # The record alone is not enough: the source room renders a page image
    # from the stored PDF, so the bytes have to be in this root's store too.
    SourceStore(root).store(
        Path(FORECASTABLE).read_bytes(),
        original_filename=Path(FORECASTABLE).name,
    )

    ScenarioStore(root).save(forecastable.document.id, approved_scenario("owner"))

    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(create_app(root), host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(200):
        if server.started:
            break
        threading.Event().wait(0.05)
    assert server.started, "the review server did not start"

    yield {
        "base": f"http://127.0.0.1:{port}",
        "document_id": forecastable.document.id,
    }

    server.should_exit = True
    thread.join(timeout=10)


@pytest.mark.parametrize(
    "screen,empty_state",
    [("forecast", "Nothing to forecast yet"), ("valuation", "Nothing to value yet")],
)
def test_the_forecast_screen_does_not_scroll_sideways_at_200_percent(
    browser, served_forecast, screen, empty_state
):
    """6.6.d / WCAG 1.4.10. Seven period columns is the widest table here, and
    the sensitivity grid is the widest on the valuation screen."""
    served = served_forecast
    context = browser.new_context(viewport={"width": 640, "height": 900})
    page = context.new_page()
    try:
        page.goto(f"{served['base']}/documents/{served['document_id']}/{screen}")
        assert empty_state not in page.content(), (
            "this test is only meaningful against a populated screen"
        )
        overflow = page.evaluate(
            "document.documentElement.scrollWidth - document.documentElement.clientWidth"
        )
        assert overflow <= 0, f"the page scrolls {overflow}px sideways"
    finally:
        context.close()


@pytest.fixture(scope="module")
def served_schedules(tmp_path_factory, three_statements):
    """Serve the FULLY REVIEWED three-statement filing.

    `served` holds a filing at the start of review, where the schedules screen
    correctly shows its empty state. Testing 200% zoom against an empty state
    proves nothing: the tables that overflow are the wide numeric ones, and
    they only exist once the mappings are approved.
    """
    import uvicorn

    from apps.api.app.api.main import create_app
    from apps.api.app.persistence.json_store import JsonDocumentRepository

    root = tmp_path_factory.mktemp("served-schedules")
    JsonDocumentRepository(root).save(three_statements)

    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(create_app(root), host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(200):
        if server.started:
            break
        threading.Event().wait(0.05)
    assert server.started, "the review server did not start"

    yield {
        "base": f"http://127.0.0.1:{port}",
        "document_id": three_statements.document.id,
    }

    server.should_exit = True
    thread.join(timeout=10)


@pytest.mark.parametrize("screen", ["schedules", "formulas", "assumptions"])
def test_the_schedules_screen_is_reachable_and_structured(browser, served_schedules, screen):
    """6.6: landmarks, a single h1, and every table with a caption.

    The screen carries no controls -- it is read, not operated -- so the test
    is about whether a screen reader can navigate it. Nine schedules of
    numbers are exactly the content where jumping by heading and by table is
    the difference between usable and not.
    """
    served = served_schedules
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()
    try:
        page.goto(f"{served['base']}/documents/{served['document_id']}/{screen}")
        assert "Nothing to show yet" not in page.content(), (
            "this test is only meaningful against a populated screen"
        )
        assert page.locator("table").count() >= 2

        assert page.get_by_role("main").count() == 1
        assert page.get_by_role("heading", level=1).count() == 1

        # Every data table is captioned and its levels do not skip.
        levels = page.eval_on_selector_all(
            "h1, h2, h3", "nodes => nodes.map(n => Number(n.tagName[1]))"
        )
        for previous, current in zip(levels, levels[1:]):
            assert current <= previous + 1, f"heading level jumps {previous} -> {current}"
        for index in range(page.locator("table").count()):
            table = page.locator("table").nth(index)
            assert table.locator("caption").count() == 1, f"table {index} has no caption"
    finally:
        context.close()


@pytest.mark.parametrize("screen", ["schedules", "formulas", "assumptions"])
def test_the_schedules_screen_does_not_scroll_sideways_at_200_percent(
    browser, served_schedules, screen
):
    """6.6.d / WCAG 1.4.10. Wide numeric tables are where this breaks first."""
    served = served_schedules
    context = browser.new_context(viewport={"width": 640, "height": 900})
    page = context.new_page()
    try:
        page.goto(f"{served['base']}/documents/{served['document_id']}/{screen}")
        assert "Nothing to show yet" not in page.content()
        overflow = page.evaluate(
            "document.documentElement.scrollWidth - document.documentElement.clientWidth"
        )
        assert overflow <= 0, f"the page scrolls {overflow}px sideways"
    finally:
        context.close()


# --- items 129, 130: the responsive layouts, in a real browser -------------

#: 6.3's three layouts, at the widths their media queries switch on.
VIEWPORTS = (
    ("desktop", 1440, 900),
    ("tablet", 1000, 800),
    ("mobile", 390, 844),
)

#: Every screen the application has. A layout test that covers one screen
#: covers the one that happened to be easy.
SCREENS = ("", "/mapping", "/statements", "/schedules", "/formulas",
           "/assumptions", "/forecast", "/valuation")


@pytest.mark.parametrize("name,width,height", VIEWPORTS, ids=lambda v: str(v))
@pytest.mark.parametrize("screen", SCREENS)
def test_no_screen_scrolls_sideways_at_any_supported_width(
    browser, served_forecast, name, width, height, screen
):
    """6.6.d / WCAG 1.4.10, across 6.3's three layouts.

    The page must not scroll sideways. A wide data table may, inside its own
    focusable region -- 1.4.10 exempts two-dimensional data and `.table-scroll`
    is where that exemption is taken.
    """
    served = served_forecast
    context = browser.new_context(viewport={"width": width, "height": height})
    page = context.new_page()
    try:
        page.goto(
            f"{served['base']}/documents/{served['document_id']}{screen}",
            wait_until="load",
        )
        overflow = page.evaluate(
            "document.documentElement.scrollWidth - document.documentElement.clientWidth"
        )
        assert overflow <= 0, f"{name} {screen or '/source'} scrolls {overflow}px sideways"
    finally:
        context.close()


def test_the_navigation_becomes_a_rail_on_tablet(browser, served_forecast):
    """6.3.b. The labels become screen-reader-only rather than being removed,
    so every link keeps its accessible name through the layout change."""
    served = served_forecast
    context = browser.new_context(viewport={"width": 1000, "height": 800})
    page = context.new_page()
    try:
        page.goto(f"{served['base']}/documents/{served['document_id']}/statements")
        link = page.get_by_role("link", name="Schedules")
        assert link.count() >= 1, "the accessible name survives the collapse"
        # The rail is narrow, and the label is clipped rather than display:none.
        width = page.evaluate(
            "document.querySelector('.shell-nav').getBoundingClientRect().width"
        )
        assert width < 100, f"the sidebar is {width}px wide on tablet"
    finally:
        context.close()


def test_the_navigation_moves_below_the_content_on_mobile(browser, served_forecast):
    """6.3.c: a bottom bar. The main content must come first in the flow."""
    served = served_forecast
    context = browser.new_context(viewport={"width": 390, "height": 844})
    page = context.new_page()
    try:
        page.goto(f"{served['base']}/documents/{served['document_id']}/statements")
        positions = page.evaluate(
            "[document.querySelector('.shell-main').getBoundingClientRect().top,"
            " document.querySelector('.shell-nav').getBoundingClientRect().top]"
        )
        assert positions[0] < positions[1], "the content must precede the navigation"
    finally:
        context.close()


def test_the_portfolio_grid_collapses_to_one_column_on_mobile(browser, served_forecast):
    """6.3.c: single-column cards."""
    served = served_forecast
    context = browser.new_context(viewport={"width": 390, "height": 844})
    page = context.new_page()
    try:
        page.goto(f"{served['base']}/")
        columns = page.evaluate(
            "getComputedStyle(document.querySelector('.grid-12'))"
            ".gridTemplateColumns.split(' ').length"
        )
        assert columns == 1, f"the dashboard is {columns} columns wide on mobile"
    finally:
        context.close()


def test_the_statement_headers_stay_put_while_the_periods_scroll(
    browser, served_forecast
):
    """6.3.e / item 127. The property a frozen header actually has: it does
    not move when the region under it is scrolled."""
    served = served_forecast
    context = browser.new_context(viewport={"width": 900, "height": 700})
    page = context.new_page()
    try:
        page.goto(f"{served['base']}/documents/{served['document_id']}/forecast")
        region = page.locator(".table-scroll.is-frozen").first
        header = region.locator("thead th").first
        before = header.bounding_box()["y"]
        region.evaluate("node => node.scrollTop = 200")
        after = header.bounding_box()["y"]
        assert abs(after - before) < 2, (
            f"the header moved {after - before}px when the table was scrolled"
        )
    finally:
        context.close()


def test_the_vendored_fonts_actually_load(browser, served_forecast):
    """Item 122. `tokens.css` named these families for two phases while
    neither was present, so every screen fell through to the system stack --
    which is exactly the failure a test that only reads CSS would miss."""
    served = served_forecast
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()
    try:
        page.goto(f"{served['base']}/documents/{served['document_id']}/statements")
        page.wait_for_function("document.fonts.status === 'loaded'", timeout=5000)
        loaded = page.evaluate(
            "Array.from(document.fonts).map(f => f.family + ' ' + f.status)"
        )
        assert any("Inter" in item and "loaded" in item for item in loaded), loaded
        assert any("Source Serif 4" in item for item in loaded), loaded
    finally:
        context.close()


def test_financial_figures_use_tabular_numerals(browser, served_forecast):
    """6.2.c. The reason the font choice is not a matter of taste: a column of
    figures in proportional numerals does not line up."""
    served = served_forecast
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()
    try:
        page.goto(f"{served['base']}/documents/{served['document_id']}/statements")
        setting = page.evaluate(
            "getComputedStyle(document.querySelector('td.num')).fontVariantNumeric"
        )
        assert "tabular-nums" in setting, setting
    finally:
        context.close()
