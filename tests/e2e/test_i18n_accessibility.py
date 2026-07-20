import re

from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import Page, expect


def test_arabic_is_rtl_but_json_is_ltr_and_persists(page: Page, live_server) -> None:
    page.goto(live_server.url)
    page.get_by_role("button", name="Language").click()
    page.get_by_role("combobox", name="Search languages").fill("العربية")
    page.get_by_role("option", name=re.compile("العربية")).click()

    expect(page.locator("html")).to_have_attribute("lang", "ar")
    expect(page.locator("html")).to_have_attribute("dir", "rtl")
    assert page.locator("#request-json").evaluate(
        "element => getComputedStyle(element).direction"
    ) == "ltr"
    assert page.locator(".technical-field input").all_inner_texts()
    assert page.locator(".technical-field input").evaluate_all(
        "controls => controls.every(control => getComputedStyle(control).direction === 'ltr')"
    )
    page.locator("#send-request").click()
    assert page.locator(".json-block").first.evaluate(
        "element => getComputedStyle(element).direction"
    ) == "ltr"
    page.reload()
    expect(page.locator("html")).to_have_attribute("dir", "rtl")


def test_portal_has_no_serious_accessibility_violations_or_mobile_overflow(
    page: Page, live_server
) -> None:
    page.set_viewport_size({"width": 320, "height": 800})
    page.goto(live_server.url)
    dimensions = page.evaluate(
        "() => ({scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth})"
    )
    assert dimensions["scroll"] <= dimensions["client"]
    results = Axe().run(page)
    serious = [
        violation
        for violation in results.response["violations"]
        if violation.get("impact") in {"serious", "critical"}
    ]
    assert not serious, results.generate_report()


def test_visible_setup_and_download_dialogs_are_accessible_without_mobile_overflow(
    page: Page, live_server
) -> None:
    page.set_viewport_size({"width": 320, "height": 800})
    page.goto(live_server.url)

    page.get_by_role("button", name="Voice Setup").click()
    _assert_accessible_without_horizontal_overflow(page)
    page.get_by_role("option", name=re.compile("locked voice", re.I)).click()
    expect(page.get_by_role("dialog", name="Confirm voice license")).to_be_visible()
    _assert_accessible_without_horizontal_overflow(page)
    page.get_by_role("dialog", name="Confirm voice license").locator(
        ".icon-button.dialog-close"
    ).click()
    page.locator("#voice-dialog [data-setup-cancel]").first.click()

    page.get_by_role("button", name="Network Setup").click()
    _assert_accessible_without_horizontal_overflow(page)
    page.locator("#network-dialog [data-setup-cancel]").first.click()

    page.get_by_role("button", name="General Setup").click()
    _assert_accessible_without_horizontal_overflow(page)


def _assert_accessible_without_horizontal_overflow(page: Page) -> None:
    dimensions = page.evaluate(
        "() => ({scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth})"
    )
    assert dimensions["scroll"] <= dimensions["client"]
    results = Axe().run(page)
    serious = [
        violation
        for violation in results.response["violations"]
        if violation.get("impact") in {"serious", "critical"}
    ]
    assert not serious, results.generate_report()


def test_locale_change_updates_cr001_controls_and_status_icons_are_hidden(
    page: Page, live_server
) -> None:
    page.goto(live_server.url)
    page.get_by_role("button", name="Language").click()
    page.get_by_role("combobox", name="Search languages").fill("Deutsch")
    page.get_by_role("option", name="Deutsch").click()

    voice_trigger = page.locator("[data-voice-dialog]")
    expect(voice_trigger).to_have_text("Stimme")
    expect(voice_trigger).to_have_attribute("aria-label", "Voice Setup")
    voice_trigger.click()
    page.locator("#voice-options").wait_for()
    assert page.locator("#voice-options .voice-status svg").evaluate_all(
        "icons => icons.every(icon => icon.getAttribute('aria-hidden') === 'true')"
    )


def test_non_english_voice_unknown_and_failure_fallbacks_are_localized(
    page: Page, live_server
) -> None:
    page.goto(live_server.url)
    page.get_by_role("button", name="Language").click()
    page.get_by_role("combobox", name="Search languages").fill("Deutsch")
    page.get_by_role("option", name="Deutsch").click()

    page.get_by_role("button", name="Voice Setup").click()
    page.get_by_role("option", name=re.compile("locked voice", re.I)).click()
    expect(page.get_by_role("dialog", name="Confirm voice license")).to_contain_text(
        "Unbekannt"
    )
    page.get_by_role("dialog", name="Confirm voice license").locator(
        ".icon-button.dialog-close"
    ).click()
    page.locator("#voice-dialog [data-setup-cancel]").first.click()

    page.route(
        "**/api/v1/getVoices",
        lambda route: route.fulfill(status=502, json={"reasonCode": 502}),
    )
    page.get_by_role("button", name="Voice Setup").click()
    expect(page.get_by_text("Stimmen konnten nicht geladen werden")).to_be_visible()
