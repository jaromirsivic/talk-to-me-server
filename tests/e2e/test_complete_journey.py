import json
import re

from playwright.sync_api import Page, expect


def test_complete_operator_journey(page: Page, live_server) -> None:
    page.goto(live_server.url)

    page.get_by_role("button", name="Use dark theme").click()
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")

    page.get_by_role("button", name="Voice Setup").click()
    page.get_by_role("searchbox", name="Search voices").fill("Amy")
    page.get_by_role(
        "button", name=re.compile("amy.*download required", re.I)
    ).click()
    page.get_by_role("button", name="Download and use").click()
    expect(page.get_by_text("Voice downloaded")).to_be_visible()
    page.locator("#voice-dialog .dialog-close").click()

    request = {
        "values": ["Release journey"],
        "importance": "high",
        "calculateStats": True,
        "waitUntilPlaybackFinished": True,
    }
    page.get_by_label("Request JSON").fill(json.dumps(request))
    page.get_by_role("button", name="Send request").click()
    expect(page.locator('[data-kind="response"]')).to_have_count(1)
    assert page.locator('[data-kind="request"] code').text_content().startswith(
        '{\n  "values": [\n'
    )
    assert '"state": "finished"' in page.locator(
        '[data-kind="response"] code'
    ).text_content()

    page.get_by_role("button", name="General Setup").click()
    page.get_by_label("Garbage collector timeout").fill("7200")
    page.get_by_role("button", name="Save settings").click()
    expect(page.get_by_text("Restart required: general.directories")).to_be_visible()
    expect(page.get_by_role("dialog", name="General Setup")).not_to_be_visible()

    page.get_by_role("button", name="Language").click()
    page.get_by_role("combobox", name="Search languages").fill("Norsk")
    page.get_by_role("option", name=re.compile("Norsk")).click()
    expect(page.locator("html")).to_have_attribute("lang", "no")
    expect(page.locator('[data-i18n-aria-label="chat.region"]')).to_be_visible()
    expect(page.get_by_role("heading", name="Samtale")).to_have_count(0)

    page.reload()
    expect(page.locator("html")).to_have_attribute("lang", "no")
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
