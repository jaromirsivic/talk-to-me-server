import re
from pathlib import Path

from playwright.sync_api import Page, expect


def open_voice_setup(page: Page, live_server) -> None:
    page.goto(live_server.url)
    page.get_by_role("button", name="Voice Setup").click()
    expect(page.get_by_role("dialog", name="Voice Setup")).to_be_visible()


def test_fast_voice_click_waits_for_slow_setup_initialization(
    page: Page, live_server
) -> None:
    page.set_extra_http_headers({"X-Test-Setup-Delay": "0.5"})
    page.goto(live_server.url)
    page.get_by_role("button", name="Voice Setup").click()

    expect(page.get_by_role("dialog", name="Voice Setup")).to_be_visible()
    expect(page.get_by_text("Current voice: LJSpeech")).to_be_visible()


def test_voice_summary_places_current_voice_left_and_volume_right(
    page: Page, live_server
) -> None:
    open_voice_setup(page, live_server)

    current_voice = page.locator(".voice-current-summary").bounding_box()
    volume = page.locator(".voice-volume-control").bounding_box()

    assert current_voice is not None
    assert volume is not None
    assert current_voice["x"] < volume["x"]


def test_import_error_is_above_voice_dialog_and_can_be_closed(
    page: Page, live_server
) -> None:
    open_voice_setup(page, live_server)
    page.locator("#import-panel summary").click()
    page.get_by_role("button", name="Import local voice").click()

    toast = page.locator('.toast[data-kind="error"]')
    expect(toast).to_be_visible()
    expect(toast).to_contain_text("Custom voice name and license are required")
    assert toast.evaluate(
        """element => {
          const bounds = element.getBoundingClientRect();
          const topElement = document.elementFromPoint(
            bounds.left + bounds.width / 2,
            bounds.top + bounds.height / 2,
          );
          return element.contains(topElement);
        }"""
    )

    toast.get_by_role("button", name="Close").click()
    expect(toast).to_be_hidden()


def test_voice_cancel_discards_selection_and_volume(page: Page, live_server) -> None:
    open_voice_setup(page, live_server)
    page.get_by_role(
        "button", name=re.compile("amy.*download required", re.I)
    ).click()
    confirmation = page.get_by_role("dialog", name="Download voice")
    confirmation.get_by_role("button", name="Download and use").click()
    expect(confirmation).to_be_hidden()
    expect(page.get_by_text("Voice downloaded")).to_be_visible()
    page.get_by_label("Voice volume").fill("72")
    page.get_by_role("button", name="Cancel", exact=True).click()

    page.get_by_role("button", name="Voice Setup").click()
    expect(page.get_by_text("Current voice: LJSpeech")).to_be_visible()
    expect(page.get_by_text("Language: en-US")).to_be_visible()
    expect(page.get_by_label("Voice volume")).to_have_value("100")


def test_voice_close_and_escape_discard_draft(page: Page, live_server) -> None:
    open_voice_setup(page, live_server)
    volume = page.get_by_label("Voice volume")
    volume.fill("71")
    page.get_by_role("dialog", name="Voice Setup").get_by_role(
        "button", name="Close"
    ).click()
    page.get_by_role("button", name="Voice Setup").click()
    expect(volume).to_have_value("100")

    volume.fill("69")
    page.get_by_role("dialog", name="Voice Setup").press("Escape")
    page.get_by_role("button", name="Voice Setup").click()
    expect(volume).to_have_value("100")


def test_restricted_voice_confirms_then_activates_only_after_save(
    page: Page, live_server
) -> None:
    open_voice_setup(page, live_server)
    page.get_by_role(
        "button", name=re.compile("locked voice.*confirmation required", re.I)
    ).click()
    dialog = page.get_by_role("dialog", name="Confirm voice license")
    expect(dialog).to_contain_text("Locked Voice")
    expect(dialog).to_contain_text("Unknown")
    expect(dialog).to_contain_text("License not approved for redistribution")
    page.get_by_role("button", name="Download and use").click()
    expect(page.get_by_text("Current voice: Locked Voice")).to_be_visible()
    installed = page.get_by_role(
        "button", name=re.compile("locked voice.*installed", re.I)
    )
    status = installed.locator(".voice-status")
    expect(status).not_to_have_class(re.compile("requires-confirmation"))
    expect(status.locator("path")).to_have_attribute(
        "d",
        "M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z",
    )
    page.get_by_role("button", name="Save settings").click()
    page.reload()
    page.get_by_role("button", name="Voice Setup").click()
    expect(page.get_by_text("Current voice: Locked Voice")).to_be_visible()


def test_free_voice_download_stages_selection_until_save(page: Page, live_server) -> None:
    open_voice_setup(page, live_server)
    page.get_by_role(
        "button", name=re.compile("amy.*download required", re.I)
    ).click()
    expect(page.get_by_role("dialog", name="Download voice")).to_be_visible()
    page.get_by_role("button", name="Download and use").click()
    expect(page.get_by_text("Voice downloaded")).to_be_visible()
    expect(page.get_by_text("Current voice: Amy")).to_be_visible()
    page.get_by_role("button", name="Save settings").click()
    page.reload()
    page.get_by_role("button", name="Voice Setup").click()
    expect(page.get_by_text("Current voice: Amy")).to_be_visible()


def test_installed_voice_opens_delete_confirmation_and_can_be_deleted(
    page: Page, live_server
) -> None:
    open_voice_setup(page, live_server)
    installed = page.get_by_role("button", name=re.compile("ljspeech.*installed", re.I))

    installed.locator("xpath=..").get_by_role("button", name="Delete voice").click()

    confirmation = page.get_by_role("dialog", name="Delete Voice")
    expect(confirmation).to_be_visible()
    expect(confirmation).to_contain_text("Delete LJSpeech from this device?")
    confirmation.get_by_role("button", name="Delete voice").click()
    expect(confirmation).to_be_hidden()
    expect(page.get_by_text("Voice deleted")).to_be_visible()
    expect(
        page.get_by_role("button", name=re.compile("ljspeech.*download required", re.I))
    ).to_be_visible()


def test_delayed_download_installs_but_does_not_mutate_reopened_voice_draft(
    page: Page, live_server
) -> None:
    open_voice_setup(page, live_server)
    page.set_extra_http_headers({"X-Test-Voice-Delay": "0.4"})
    page.get_by_role("button", name=re.compile("amy.*download required", re.I)).click()
    confirmation = page.get_by_role("dialog", name="Download voice")
    confirmation.get_by_role("button", name="Download and use").click()
    progress = confirmation.locator("#download-voice-progress")
    expect(progress.get_by_text("Downloading voice…", exact=True)).to_be_visible()
    expect(
        progress.get_by_text("The download is in progress. This may take a few minutes.")
    ).to_be_visible()
    expect(
        progress.get_by_role("progressbar", name="Voice download progress")
    ).to_be_visible()
    expect(confirmation.get_by_role("button", name="Downloading voice…")).to_be_disabled()
    confirmation.get_by_role("button", name="Close").click()
    page.get_by_role("dialog", name="Voice Setup").get_by_role(
        "button", name="Cancel", exact=True
    ).click()

    page.set_extra_http_headers({})
    page.get_by_role("button", name="Voice Setup").click()
    page.get_by_label("Voice volume").fill("73")
    page.wait_for_timeout(600)

    expect(page.get_by_text("Current voice: LJSpeech")).to_be_visible()
    expect(page.get_by_label("Voice volume")).to_have_value("73")
    expect(page.get_by_role("button", name=re.compile("amy.*installed", re.I))).to_be_visible()


def test_delayed_import_installs_but_does_not_mutate_reopened_voice_draft(
    page: Page, live_server, tmp_path: Path
) -> None:
    model = tmp_path / "delayed.onnx"
    config = tmp_path / "delayed.onnx.json"
    model.write_bytes(b"model")
    config.write_text('{"audio":{"sample_rate":22050}}', encoding="utf-8")
    open_voice_setup(page, live_server)
    page.set_extra_http_headers({"X-Test-Voice-Delay": "0.4"})
    page.locator("#import-panel summary").click()
    page.get_by_label("Custom voice name").fill("Delayed Voice")
    page.get_by_label("Piper model file").set_input_files(model)
    page.get_by_label("Piper config file").set_input_files(config)
    page.get_by_label("I confirm I have the right to use this voice").check()
    page.get_by_role("button", name="Import local voice").click()
    page.get_by_role("dialog", name="Voice Setup").get_by_role(
        "button", name="Cancel", exact=True
    ).click()

    page.set_extra_http_headers({})
    page.get_by_role("button", name="Voice Setup").click()
    page.get_by_label("Voice volume").fill("77")
    page.wait_for_timeout(600)

    expect(page.get_by_text("Current voice: LJSpeech")).to_be_visible()
    expect(page.get_by_label("Voice volume")).to_have_value("77")
    expect(
        page.get_by_role("button", name=re.compile("delayed voice.*installed", re.I))
    ).to_be_visible()


def test_all_and_downloaded_filters_compose_with_search(page: Page, live_server) -> None:
    open_voice_setup(page, live_server)
    search = page.get_by_role("searchbox", name="Search voices")
    voices = page.get_by_role("list", name="Available voices")
    expect(voices.locator(".voice-option")).to_have_count(4)

    page.get_by_role("button", name="Already downloaded").click()
    expect(voices.locator(".voice-option")).to_have_count(1)
    expect(voices.get_by_role("button", name=re.compile("ljspeech", re.I))).to_be_visible()
    search.fill("amy")
    expect(page.get_by_text("No voices found")).to_be_visible()

    page.get_by_role("button", name="All voices").click()
    expect(voices.get_by_role("button", name=re.compile("amy", re.I))).to_be_visible()


def test_invalid_voice_is_unavailable_and_has_no_download_icon(
    page: Page, live_server
) -> None:
    open_voice_setup(page, live_server)
    invalid = page.get_by_role(
        "button",
        name=re.compile("broken voice.*unavailable.*missing voice metadata", re.I),
    )

    expect(invalid).to_be_disabled()
    expect(invalid.locator(".material-icon")).to_have_count(0)
    expect(page.get_by_role("dialog", name="Download voice")).not_to_be_visible()


def test_voice_search_arrows_focus_the_first_visible_voice(page: Page, live_server) -> None:
    open_voice_setup(page, live_server)
    search = page.get_by_role("searchbox", name="Search voices")
    search.press("ArrowDown")
    expect(
        page.get_by_role("button", name=re.compile("ljspeech.*installed", re.I))
    ).to_be_focused()


def test_installed_voice_delete_cancel_restores_focus(
    page: Page, live_server
) -> None:
    open_voice_setup(page, live_server)
    installed = page.get_by_role("button", name=re.compile("ljspeech.*installed", re.I))
    delete_button = installed.locator("xpath=..").get_by_role(
        "button", name="Delete voice"
    )
    delete_button.focus()
    delete_button.press("Enter")
    confirmation = page.get_by_role("dialog", name="Delete Voice")
    expect(confirmation).to_be_visible()
    confirmation.get_by_role("button", name="Cancel").click()

    expect(delete_button).to_be_focused()


def test_installed_voice_row_stages_selection_until_save(page: Page, live_server) -> None:
    open_voice_setup(page, live_server)
    page.get_by_role("button", name=re.compile("amy.*download required", re.I)).click()
    page.get_by_role("button", name="Download and use").click()
    page.get_by_role("button", name="Save settings").click()

    page.get_by_role("button", name="Voice Setup").click()
    page.get_by_role("button", name=re.compile("ljspeech.*installed", re.I)).click()
    confirmation = page.get_by_role("dialog", name="Select Voice")
    expect(confirmation).to_contain_text("Use LJSpeech as the active voice?")
    confirmation.get_by_role("button", name="Use voice").click()
    expect(page.get_by_text("Current voice: LJSpeech")).to_be_visible()
    page.get_by_role("button", name="Save settings").click()

    page.reload()
    page.get_by_role("button", name="Voice Setup").click()
    expect(page.get_by_text("Current voice: LJSpeech")).to_be_visible()


def test_completed_download_restores_focus_to_rebuilt_voice_option(
    page: Page, live_server
) -> None:
    open_voice_setup(page, live_server)
    page.get_by_role("button", name=re.compile("amy.*download required", re.I)).click()
    page.get_by_role("dialog", name="Download voice").get_by_role(
        "button", name="Download and use"
    ).click()

    installed = page.get_by_role("button", name=re.compile("amy.*installed", re.I))
    expect(installed).to_be_focused()
    expect(installed.locator(".voice-status-details")).to_have_count(0)
    expect(
        installed.locator("xpath=..").get_by_role(
            "button", name="Delete voice (63 MB)"
        )
    ).to_be_visible()
    expect(installed).to_have_attribute("title", str(Path("downloaded.onnx").resolve()))


def test_import_starts_collapsed_with_cc0_and_has_no_url_controls(
    page: Page, live_server
) -> None:
    open_voice_setup(page, live_server)
    panel = page.locator("#import-panel")
    expect(panel).not_to_have_attribute("open", "")
    panel.locator("summary").click()
    expect(page.get_by_label("Voice license")).to_have_value("CC0-1.0")
    expect(page.get_by_label("Model URL")).to_have_count(0)
    expect(page.get_by_label("Config URL")).to_have_count(0)
    expect(page.get_by_role("button", name="Import from URLs")).to_have_count(0)


def test_local_import_stages_custom_voice_and_shows_custom_badge_only(
    page: Page, live_server, tmp_path: Path
) -> None:
    model = tmp_path / "voice.onnx"
    config = tmp_path / "voice.onnx.json"
    model.write_bytes(b"model")
    config.write_text('{"audio":{"sample_rate":22050}}', encoding="utf-8")
    open_voice_setup(page, live_server)

    expect(page.locator(".source-badge")).to_have_count(0)
    page.locator("#import-panel summary").click()
    page.get_by_label("Custom voice name").fill("My Voice")
    page.get_by_label("Piper model file").set_input_files(model)
    page.get_by_label("Piper config file").set_input_files(config)
    page.get_by_label("I confirm I have the right to use this voice").check()
    page.get_by_role("button", name="Import local voice").click()

    expect(page.get_by_text("Voice imported")).to_be_visible()
    expect(page.get_by_text("Current voice: My Voice")).to_be_visible()
    custom = page.get_by_role("button", name=re.compile("my voice.*installed", re.I))
    expect(custom.get_by_text("Custom", exact=True)).to_be_visible()
    page.get_by_role("button", name="Cancel", exact=True).click()
    page.get_by_role("button", name="Voice Setup").click()
    expect(page.get_by_text("Current voice: LJSpeech")).to_be_visible()


def test_save_persists_voice_and_volume_together(page: Page, live_server) -> None:
    open_voice_setup(page, live_server)
    page.get_by_label("Voice volume").fill("72")
    page.get_by_role("button", name="Save settings").click()

    page.reload()
    page.get_by_role("button", name="Voice Setup").click()
    expect(page.get_by_text("Current voice: LJSpeech")).to_be_visible()
    expect(page.get_by_label("Voice volume")).to_have_value("72")
