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


def test_toasts_stack_with_independent_countdowns_and_close_controls(
    page: Page, live_server
) -> None:
    page.goto(live_server.url)
    toggle = page.locator("#theme-toggle")
    toggle.click()
    expect(toggle).to_be_enabled()
    expect(toggle).to_have_attribute("aria-label", "Use light theme")
    expect(page.locator('.toast[data-kind="success"]')).to_have_css(
        "background-color", "rgb(20, 51, 34)"
    )
    toggle.click()

    toasts = page.locator('.toast[data-kind="success"]')
    expect(toasts).to_have_count(2)
    expect(toasts.nth(0)).to_contain_text("Theme applied immediately (9)")
    expect(toasts.nth(1)).to_contain_text("Theme applied immediately (9)")
    expect(toasts.nth(0)).to_have_css("background-color", "rgb(220, 252, 231)")

    toasts.nth(0).get_by_role("button", name="Close").click()
    expect(toasts).to_have_count(1)
    expect(toasts.first).to_contain_text("(8)", timeout=2_000)
    expect(toasts).to_have_count(0, timeout=9_500)
