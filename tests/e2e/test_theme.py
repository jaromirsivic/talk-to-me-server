from playwright.sync_api import Page, expect


def test_theme_toggle_applies_and_persists_without_opening_modal(
    page: Page, live_server
) -> None:
    page.goto(live_server.url)
    toggle = page.get_by_role("button", name="Use dark theme")
    toggle.click()

    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    expect(page.get_by_role("button", name="Use light theme")).to_be_visible()
    expect(page.locator("dialog[open]")).to_have_count(0)
    page.reload()
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
