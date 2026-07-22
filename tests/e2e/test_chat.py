import json
import re
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.parametrize("viewport", [{"width": 1440, "height": 900}, {"width": 390, "height": 844}])
def test_chat_shows_indented_request_and_response(
    page: Page, live_server, viewport, tmp_path: Path
) -> None:
    page.set_viewport_size(viewport)
    page.goto(live_server.url)
    editor = page.get_by_label("Request JSON")
    expect(editor).to_have_value(re.compile("If you here this voice"))
    editor.fill(json.dumps({"values": ["Hello"], "importance": "high", "calculateStats": True}))
    page.get_by_role("button", name="Send request").click()
    expect(page.locator('[data-kind="response"]')).to_have_count(1)

    request = page.locator('[data-kind="request"] code').text_content()
    response = page.locator('[data-kind="response"] code').text_content()
    assert request == '{\n  "values": [\n    "Hello"\n  ],\n  "importance": "high",\n  "calculateStats": true\n}'
    assert response.startswith('{\n  "version": 1,\n  "reasonCode": 200,')
    page.screenshot(path=tmp_path / f"chat-{viewport['width']}.png", full_page=True)


def test_first_message_notice_follows_first_request_and_precedes_response(
    page: Page, live_server
) -> None:
    page.goto(live_server.url)
    page.get_by_role("button", name="Send request").click()

    notice = page.locator(".first-message-notice")
    request = page.locator('[data-kind="request"]')
    expect(notice).to_have_count(1)
    expect(request).to_have_count(1)
    expect(notice).to_contain_text("neural network")
    assert request.evaluate(
        "node => Boolean(node.compareDocumentPosition(document.querySelector('.first-message-notice')) & Node.DOCUMENT_POSITION_FOLLOWING)"
    )

    expect(page.locator('[data-kind="response"]')).to_have_count(1)
    response = page.locator('[data-kind="response"]').first
    assert notice.evaluate(
        "node => Boolean(node.compareDocumentPosition(document.querySelector('[data-kind=response]')) & Node.DOCUMENT_POSITION_FOLLOWING)"
    )
    assert response.is_visible()
    page.get_by_role("button", name="Send request").click()
    expect(page.locator('[data-kind="response"]')).to_have_count(2)
    expect(notice).to_have_count(1)


def test_editor_starts_from_master_request_and_reports_json_location(
    page: Page, live_server
) -> None:
    page.goto(live_server.url)
    editor = page.get_by_label("Request JSON")
    expect(editor).to_have_value(re.compile("importance"))
    initial = json.loads(editor.input_value())
    assert initial["importance"] == "high"
    editor.fill('{"values": [}')
    page.get_by_role("button", name="Send request").click()

    dialog = page.get_by_role("dialog", name="Invalid JSON")
    expect(dialog).to_contain_text("line 1")
    expect(dialog).to_contain_text("column")
    expect(page.locator(".chat-card")).to_have_count(0)


def test_reset_requires_confirmation_and_restores_default_request(
    page: Page, live_server
) -> None:
    page.goto(live_server.url)
    editor = page.get_by_label("Request JSON")
    editor.fill('{"values":["custom"]}')
    page.get_by_role("button", name="Reset").click()

    dialog = page.get_by_role("dialog", name="Reset")
    expect(dialog).to_contain_text("Do you really want to reset the text in the panel?")
    expect(page.locator("#cancel-reset")).to_be_focused()
    dialog.get_by_role("button", name="Cancel").click()
    expect(editor).to_have_value('{"values":["custom"]}')

    page.get_by_role("button", name="Reset").click()
    dialog.get_by_role("button", name="Reset text").click()
    payload = json.loads(editor.input_value())
    assert payload["value"].startswith("If you here this voice")
    assert payload["importance"] == "high"
    assert payload["volumeMultiplier"] == 0.95
    assert payload["calculateStats"] is False
    expect(page.locator(".chat-card")).to_have_count(0)


def test_stop_button_follows_queue_polling_and_stays_disabled_for_one_second(
    page: Page, live_server
) -> None:
    queue_state = {"active": False}
    stop_requests = []

    def route_queue_info(route) -> None:
        active = queue_state["active"]
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "version": 1,
                    "reasonCode": 200,
                    "reasonText": "OK",
                    "hasActiveJobs": active,
                    "activeJobCount": 1 if active else 0,
                }
            ),
        )

    def route_stop(route) -> None:
        stop_requests.append(True)
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "version": 1,
                    "reasonCode": 200,
                    "reasonText": "Playback stopped",
                    "cancelledJobs": 1,
                }
            ),
        )

    page.route("**/api/v1/queueInfo", route_queue_info)
    page.route("**/api/v1/stop", route_stop)
    page.goto(live_server.url)
    stop = page.get_by_role("button", name="Stop")
    expect(stop).to_be_disabled()

    queue_state["active"] = True
    expect(stop).to_be_enabled(timeout=2_500)
    stop.click()
    expect(stop).to_be_disabled()
    assert len(stop_requests) == 1

    page.wait_for_timeout(700)
    expect(stop).to_be_disabled()
    expect(stop).to_be_enabled(timeout=1_500)
    assert len(stop_requests) == 1


def test_composer_copy_writes_the_exact_editor_json_to_clipboard(
    page: Page, live_server
) -> None:
    page.context.grant_permissions(["clipboard-read", "clipboard-write"], origin=live_server.url)
    page.goto(live_server.url)
    editor = page.get_by_label("Request JSON")
    payload = '{\n  "values": ["Copy me"]\n}'
    editor.fill(payload)

    page.locator("#copy-request").click()

    copied = page.evaluate("navigator.clipboard.readText()").replace("\r\n", "\n")
    assert copied == payload


def test_composer_word_wrap_and_line_numbers_align_wrapped_logical_lines(
    page: Page, live_server
) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(live_server.url)
    editor = page.get_by_label("Request JSON")
    editor.fill(f'{{"long":"{"x" * 240}"}}\n{{"short":true}}')

    wrap = page.locator("#wrap-request")
    line_numbers = page.locator("#line-numbers-request")

    expect(wrap).to_have_attribute("aria-pressed", "true")
    expect(line_numbers).to_have_attribute("aria-pressed", "false")
    line_numbers.click()
    expect(line_numbers).to_have_attribute("aria-pressed", "true")
    expect(editor).to_have_css("white-space", "pre-wrap")
    numbers = page.locator("#composer .line-number")
    expect(numbers).to_have_count(2)
    first_height = numbers.nth(0).evaluate(
        "element => Number.parseFloat(element.style.height)"
    )
    second_height = numbers.nth(1).evaluate(
        "element => Number.parseFloat(element.style.height)"
    )
    assert first_height > second_height


def test_composer_code_controls_stay_in_one_mobile_toolbar_row(
    page: Page, live_server
) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(live_server.url)

    actions = page.locator(".composer-toolbar-actions").bounding_box()
    editor = page.locator(".composer-editor").bounding_box()
    assert actions is not None
    assert editor is not None
    assert actions["height"] <= 44
    assert editor["height"] >= 70


def test_request_and_response_cards_have_independent_code_controls(
    page: Page, live_server
) -> None:
    page.context.grant_permissions(["clipboard-read", "clipboard-write"], origin=live_server.url)
    page.goto(live_server.url)
    page.get_by_role("button", name="Send request").click()
    expect(page.locator('[data-kind="response"]')).to_have_count(1)

    request = page.locator('[data-kind="request"]')
    response = page.locator('[data-kind="response"]')
    expect(request.locator("[data-code-action]")).to_have_count(3)
    expect(response.locator("[data-code-action]")).to_have_count(3)

    expect(request.get_by_role("button", name="Word wrap")).to_have_attribute(
        "aria-pressed", "true"
    )
    expect(request.get_by_role("button", name="Line numbers")).to_have_attribute(
        "aria-pressed", "false"
    )
    expect(request.locator(".json-block")).to_have_css("white-space", "pre-wrap")
    request.get_by_role("button", name="Line numbers").click()
    expect(request.locator(".line-number")).to_have_count(
        request.locator("code").text_content().count("\n") + 1
    )

    request.get_by_role("button", name="Word wrap").click()
    request.get_by_role("button", name="Line numbers").click()
    expect(request.get_by_role("button", name="Word wrap")).to_have_attribute(
        "aria-pressed", "false"
    )
    expect(response.get_by_role("button", name="Word wrap")).to_have_attribute(
        "aria-pressed", "true"
    )
    expect(response.get_by_role("button", name="Line numbers")).to_have_attribute(
        "aria-pressed", "false"
    )

    request.get_by_role("button", name="Copy JSON").click()
    copied = page.evaluate("navigator.clipboard.readText()").replace("\r\n", "\n")
    assert copied == request.locator("code").text_content()


def test_composer_can_be_resized_from_its_top_edge(page: Page, live_server) -> None:
    page.goto(live_server.url)
    composer = page.locator("#composer")
    handle = page.get_by_role("separator", name="Resize request editor")
    initial = composer.bounding_box()
    handle_box = handle.bounding_box()

    assert initial is not None
    assert handle_box is not None
    page.mouse.move(handle_box["x"] + handle_box["width"] / 2, handle_box["y"] + 2)
    page.mouse.down()
    page.mouse.move(handle_box["x"] + handle_box["width"] / 2, handle_box["y"] - 100)
    page.mouse.up()

    resized = composer.bounding_box()
    assert resized is not None
    assert resized["height"] >= initial["height"] + 80
    expect(page.get_by_label("Request JSON")).to_have_css("resize", "none")


def test_composer_maximizes_below_header_and_restores(page: Page, live_server) -> None:
    page.goto(live_server.url)
    composer = page.locator("#composer")
    header = page.locator(".app-header")
    toggle = page.locator("#composer-size-toggle")
    expect(toggle).to_have_attribute("aria-label", "Maximize request editor")
    expect(toggle).to_have_attribute("data-tooltip", "Maximize request editor")
    toggle.click()

    expect(composer).to_have_class(re.compile("is-maximized"))
    expect(toggle).to_have_attribute("aria-pressed", "true")
    expect(toggle).to_have_attribute("data-tooltip", "Restore request editor")
    composer_box = composer.bounding_box()
    header_box = header.bounding_box()
    viewport = page.viewport_size
    assert composer_box is not None
    assert header_box is not None
    assert viewport is not None
    assert abs(composer_box["y"] - (header_box["y"] + header_box["height"])) <= 1
    assert abs(composer_box["width"] - viewport["width"]) <= 1
    assert abs(composer_box["y"] + composer_box["height"] - viewport["height"]) <= 1

    page.get_by_role("button", name="Restore request editor").click()
    expect(composer).not_to_have_class(re.compile("is-maximized"))
    expect(toggle).to_have_attribute("aria-pressed", "false")


def test_send_request_restores_composer_and_keeps_latest_response_visible(
    page: Page, live_server
) -> None:
    page.goto(live_server.url)
    composer = page.locator("#composer")
    page.get_by_role("button", name="Maximize request editor").click()
    page.get_by_role("button", name="Send request").click()

    expect(composer).not_to_have_class(re.compile("is-maximized"))
    expect(page.locator('[data-kind="response"]')).to_have_count(1)


def test_page_can_scroll_latest_response_above_composer(page: Page, live_server) -> None:
    page.goto(live_server.url)
    for index in range(6):
        page.get_by_label("Request JSON").fill(
            json.dumps({"values": [f"Message {index}"], "importance": "high"})
        )
        page.get_by_role("button", name="Send request").click()
        expect(page.locator('[data-kind="response"]')).to_have_count(index + 1)

    page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
    latest = page.locator('[data-kind="response"]').last.bounding_box()
    composer_box = page.locator("#composer").bounding_box()
    assert latest is not None
    assert composer_box is not None
    assert latest["y"] + latest["height"] <= composer_box["y"] - 12


def test_chat_cards_show_local_date_and_time_with_seconds(page: Page, live_server) -> None:
    page.goto(live_server.url)
    page.get_by_role("button", name="Send request").click()

    expect(page.locator('[data-kind="request"] time')).to_have_attribute("datetime", re.compile("T"))
    expect(page.locator('[data-kind="response"] time')).to_have_attribute("datetime", re.compile("T"))
    assert all(
        re.search(r"\d{1,2}:\d{2}:\d{2}", text)
        for text in page.locator(".card-time").all_text_contents()
    )
