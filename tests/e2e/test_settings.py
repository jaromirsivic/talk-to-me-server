from playwright.sync_api import Page, expect


def test_restart_field_is_reported_without_server_restart(page: Page, live_server) -> None:
    page.goto(live_server.url)
    page.get_by_role("button", name="General Setup").click()
    workers = page.get_by_label("Synthesis workers")
    expect(workers).to_have_value("4")
    workers.fill("6")
    page.get_by_role("button", name="Save settings").click()

    expect(page.get_by_text("Restart required: general.workers")).to_be_visible()
    assert live_server.process_id == live_server.original_process_id


def test_network_dialog_exposes_lan_warning_and_complete_controls(
    page: Page, live_server
) -> None:
    page.goto(live_server.url)
    page.get_by_role("button", name="Network Setup").click()
    dialog = page.get_by_role("dialog", name="Network Setup")

    expect(dialog.get_by_text("Remote management exposes setup controls to your LAN.")).to_be_visible()
    expect(dialog.get_by_label("IPv4 address")).to_have_value("127.0.0.1")
    expect(dialog.get_by_label("IPv6 address")).to_have_value("::1")
    expect(dialog.get_by_label("Port")).to_have_value("44448")


def test_network_cancel_discards_draft_and_warning_follows_checkbox(page: Page, live_server) -> None:
    page.goto(live_server.url)
    page.get_by_role("button", name="Network Setup").click()
    dialog = page.get_by_role("dialog", name="Network Setup")
    remote = dialog.get_by_label("Enable remote management")
    warning = dialog.get_by_text("Remote management exposes setup controls to your LAN.")
    expect(remote).to_be_checked()
    expect(warning).to_be_visible()
    remote.uncheck()
    expect(warning).to_be_hidden()
    dialog.get_by_role("button", name="Cancel").click()
    page.get_by_role("button", name="Network Setup").click()
    expect(dialog.get_by_label("Enable remote management")).to_be_checked()


def test_general_escape_discards_but_save_persists(page: Page, live_server) -> None:
    page.goto(live_server.url)
    page.get_by_role("button", name="General Setup").click()
    page.get_by_label("Synthesis workers").fill("6")
    page.keyboard.press("Escape")
    page.get_by_role("button", name="General Setup").click()
    expect(page.get_by_label("Synthesis workers")).to_have_value("4")
    page.get_by_label("Synthesis workers").fill("6")
    page.get_by_role("button", name="Save settings").click()
    page.get_by_role("button", name="General Setup").click()
    expect(page.get_by_label("Synthesis workers")).to_have_value("6")


def test_stale_setup_success_does_not_close_or_clear_reopened_draft(
    page: Page, live_server
) -> None:
    page.goto(live_server.url)
    page.set_extra_http_headers({"X-Test-Setup-Delay": "0.4"})
    page.get_by_role("button", name="General Setup").click()
    dialog = page.get_by_role("dialog", name="General Setup")
    workers = dialog.get_by_label("Synthesis workers")
    workers.fill("6")
    dialog.get_by_role("button", name="Save settings").click()
    expect(dialog.locator("[data-save-status]")).to_have_text("Saving…")
    dialog.get_by_role("button", name="Close").click()

    page.set_extra_http_headers({})
    page.get_by_role("button", name="General Setup").click()
    workers.fill("7")
    page.wait_for_timeout(600)

    expect(dialog).to_be_visible()
    expect(workers).to_have_value("7")
    expect(dialog.locator("[data-save-status]")).to_be_empty()
    dialog.get_by_role("button", name="Save settings").click()
    expect(dialog).not_to_be_visible()
    page.reload()
    page.get_by_role("button", name="General Setup").click()
    expect(page.get_by_label("Synthesis workers")).to_have_value("7")


def test_stale_setup_failure_does_not_inject_error_and_reopened_draft_can_retry(
    page: Page, live_server
) -> None:
    page.goto(live_server.url)
    page.set_extra_http_headers(
        {"X-Test-Setup-Delay": "0.4", "X-Test-Setup-Fail": "true"}
    )
    page.get_by_role("button", name="General Setup").click()
    dialog = page.get_by_role("dialog", name="General Setup")
    workers = dialog.get_by_label("Synthesis workers")
    workers.fill("6")
    dialog.get_by_role("button", name="Save settings").click()
    expect(dialog.locator("[data-save-status]")).to_have_text("Saving…")
    dialog.press("Escape")

    page.set_extra_http_headers({})
    page.get_by_role("button", name="General Setup").click()
    workers.fill("7")
    page.wait_for_timeout(600)

    expect(dialog).to_be_visible()
    expect(workers).to_have_value("7")
    expect(dialog.locator("[data-save-status]")).to_be_empty()
    expect(page.get_by_text("Delayed setup failure")).not_to_be_visible()
    dialog.get_by_role("button", name="Save settings").click()
    expect(dialog).not_to_be_visible()
