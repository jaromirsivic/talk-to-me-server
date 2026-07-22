import json
from pathlib import Path


def test_portal_has_semantic_shell_and_accessible_json_composer() -> None:
    html = Path("web/index.html").read_text(encoding="utf-8")

    assert "<header" in html and "<main" in html and "<footer" not in html
    assert 'aria-label="Request JSON"' in html
    assert 'id="chat-history"' in html
    assert 'type="module"' in html
    assert 'aria-live="polite"' in html
    assert "Conversation</h1>" not in html
    assert 'data-i18n-aria-label="chat.region"' in html
    assert 'id="benchmark-request"' not in html
    assert 'id="reset-confirm-dialog"' in html
    assert 'href="/styles.css?v=sprint-0003"' in html
    assert 'src="/js/app.js?v=sprint-0003"' in html


def test_first_message_notice_is_inserted_before_the_first_request() -> None:
    app = Path("web/js/app.js").read_text(encoding="utf-8")
    chat = Path("web/js/chat.js").read_text(encoding="utf-8")
    css = Path("web/styles.css").read_text(encoding="utf-8")

    notice_call = "appendFirstMessageNotice(history)"
    request_call = 'appendChatCard(history, "request"'
    assert notice_call in app
    assert app.index(notice_call) < app.index(request_call)
    assert 'history.querySelector(\'[data-kind="request"]\')' in app
    assert 'notice.dataset.i18n = "chat.firstMessageNotice"' in chat
    assert 'notice.setAttribute("role", "status")' in chat
    assert ".first-message-notice" in css
    assert "align-self: center" in css


def test_default_request_is_valid_and_benchmark_is_fully_removed() -> None:
    payload = json.loads(Path("master-data/request.json").read_text(encoding="utf-8"))
    app = Path("src/talk_to_me_server/app.py").read_text(encoding="utf-8")
    browser = Path("web/js/app.js").read_text(encoding="utf-8")

    assert payload["value"].startswith("If you here this voice")
    assert payload["importance"] == "high"
    assert payload["volumeMultiplier"] == 0.95
    assert payload["calculateStats"] is False
    assert payload["waitUntilPlaybackFinished"] is False
    assert "benchmark" not in app.casefold()
    assert "benchmark" not in browser.casefold()


def test_every_api_call_uses_post_and_json_is_pretty_printed() -> None:
    api = Path("web/js/api.js").read_text(encoding="utf-8")
    json_source = Path("web/js/json.js").read_text(encoding="utf-8")

    assert 'method: "POST"' in api
    assert "fetch(" in api
    assert "JSON.stringify(value, null, 2)" in json_source


def test_approved_blue_and_responsive_breakpoints_are_present() -> None:
    css = Path("web/styles.css").read_text(encoding="utf-8")

    assert "#2C6BED" in css
    assert "720px" in css
    assert "1100px" in css
    assert "prefers-reduced-motion" in css


def test_network_setup_uses_the_project_svg_icon() -> None:
    html = Path("web/index.html").read_text(encoding="utf-8")
    css = Path("web/styles.css").read_text(encoding="utf-8")
    icon = Path("web/assets/icons/network_setup.svg").read_text(encoding="utf-8")
    network_start = html.index('data-settings-dialog="network"')
    network_button = html[network_start:html.index("</button>", network_start)]

    assert 'class="network-setup-icon"' in html
    assert "⌁" not in network_button
    assert '/assets/icons/network_setup.svg' in css
    assert 'fill="#2C6BED"' in icon


def test_general_setup_and_composer_use_the_project_svg_icons() -> None:
    html = Path("web/index.html").read_text(encoding="utf-8")
    css = Path("web/styles.css").read_text(encoding="utf-8")
    settings = Path("web/assets/icons/settings.svg").read_text(encoding="utf-8")
    fullscreen = Path("web/assets/icons/fullscreen.svg").read_text(encoding="utf-8")
    general_start = html.index('data-settings-dialog="general"')
    general_button = html[general_start:html.index("</button>", general_start)]

    assert 'class="general-setup-icon"' in general_button
    assert "⚙" not in general_button
    assert 'id="composer-size-toggle"' in html
    assert 'class="fullscreen-icon"' in html
    assert '/assets/icons/settings.svg' in css
    assert '/assets/icons/fullscreen.svg' in css
    assert 'fill="#2C6BED"' in settings
    assert 'fill="#2C6BED"' in fullscreen


def test_composer_code_controls_use_project_icons_in_the_requested_order() -> None:
    html = Path("web/index.html").read_text(encoding="utf-8")
    css = Path("web/styles.css").read_text(encoding="utf-8")
    toolbar_start = html.index('class="composer-toolbar-actions"')
    toolbar_end = html.index("</div>", toolbar_start)
    toolbar = html[toolbar_start:toolbar_end]

    assert 'id="benchmark-request"' not in toolbar
    assert toolbar.index('id="reset-request"') < toolbar.index('id="copy-request"')
    assert toolbar.index('id="copy-request"') < toolbar.index('id="wrap-request"')
    assert toolbar.index('id="wrap-request"') < toolbar.index('id="line-numbers-request"')
    assert toolbar.index('id="line-numbers-request"') < toolbar.index(
        'id="composer-size-toggle"'
    )
    assert toolbar.count('data-i18n-tooltip="code.') == 3
    assert 'data-i18n-tooltip="composer.maximize"' in toolbar
    assert toolbar.count('aria-pressed="true"') == 1
    assert 'id="composer-size-toggle"' in toolbar
    assert ".composer-size-toggle[data-tooltip]::after" in css
    assert 'data-tooltip="Maximize request editor"' in toolbar

    editor_start = html.index('class="code-view composer-editor')
    editor_end = html.index('</textarea>', editor_start)
    editor = html[editor_start:editor_end]
    assert 'class="code-view composer-editor"' in editor
    assert 'class="line-number-gutter" aria-hidden="true" hidden' in editor
    assert 'class="is-wrapped"' in editor
    assert 'wrap="soft"' in editor

    for name in ("copy", "line_numbers", "wrap"):
        icon = Path(f"web/assets/icons/{name}.svg").read_text(encoding="utf-8")
        assert f'/assets/icons/{name}.svg' in css
        assert 'fill="#2C6BED"' in icon


def test_chat_cards_offer_the_same_icon_only_code_controls() -> None:
    html = Path("web/index.html").read_text(encoding="utf-8")
    template_start = html.index('id="chat-card-template"')
    template_end = html.index("</template>", template_start)
    template = html[template_start:template_end]

    assert 'class="card-code-controls"' in template
    assert template.count('data-code-action=') == 3
    assert template.count('data-i18n-tooltip="code.') == 3
    assert template.count('aria-pressed="true"') == 1
    assert 'class="code-view card-code-view"' in template
    assert 'class="line-number-gutter" aria-hidden="true" hidden' in template
    assert 'class="json-block is-wrapped"' in template
    assert '>Copy<' not in template


def test_voice_setup_uses_transactional_form_and_local_material_icons() -> None:
    html = Path("web/index.html").read_text(encoding="utf-8")
    voices = Path("web/js/voices.js").read_text(encoding="utf-8")

    assert 'form class="dialog-card" id="voice-form"' in html
    assert html.count('data-setup-cancel') >= 6
    assert 'data-save-status aria-live="polite"' in html
    assert 'class="material-icon"' in html
    assert "M9 9c1.66 0 2.99-1.34" in html
    assert "createSetupDialogController" in voices
    assert "createDraft: (setup) => structuredClone(setup.voice)" in voices
    assert "setup.voice = draft" in voices
    assert 'persist: persistSetup' in voices
    assert "M12 2C6.48 2 2 6.48" in voices
    assert "M5 20h14v-2H5v2z" in voices
    assert "data-severity" not in html
    assert "severity" not in voices


def test_installed_voice_uses_delete_confirmation_flow() -> None:
    html = Path("web/index.html").read_text(encoding="utf-8")
    voices = Path("web/js/voices.js").read_text(encoding="utf-8")

    assert 'id="delete-voice-dialog"' in html
    assert 'aria-labelledby="delete-voice-title"' in html
    assert 'id="delete-voice-message"' in html
    assert 'id="confirm-delete-voice"' in html
    assert 'postApi("deleteVoice"' in voices
    assert 'translate("voice.deleteMessage"' in voices
    assert 'translate("voice.deleted")' in voices
    assert 'className = "voice-delete-button"' in voices
    assert "voice.status !== \"ready\"" in voices
    assert "`${deleteLabel} (${installedSize})`" in voices
    assert 'className = "voice-option-row"' in voices
    assert 'requestVoiceDeletion(voice)' in voices


def test_installed_voice_row_uses_selection_confirmation_flow() -> None:
    html = Path("web/index.html").read_text(encoding="utf-8")
    voices = Path("web/js/voices.js").read_text(encoding="utf-8")

    assert 'id="select-voice-dialog"' in html
    assert 'id="select-voice-message"' in html
    assert 'id="confirm-select-voice"' in html
    assert 'translate("voice.selectMessage"' in voices
    assert "stageVoice(candidate.id)" in voices


def test_installed_voices_are_sorted_before_catalog_downloads() -> None:
    voices = Path("web/js/voices.js").read_text(encoding="utf-8")

    assert 'Number(right.status === "ready") - Number(left.status === "ready")' in voices


def test_voice_setup_has_summary_filter_and_local_only_collapsed_import() -> None:
    html = Path("web/index.html").read_text(encoding="utf-8")

    assert 'class="voice-summary"' in html
    assert 'id="current-voice-language"' in html
    assert html.index('class="voice-current-summary"') < html.index(
        'class="voice-volume-control"'
    )
    assert 'class="voice-search-row"' in html
    assert 'class="voice-filter"' in html
    assert '<details class="import-panel" id="import-panel">' in html
    assert 'id="custom-voice-license"' in html
    assert 'type="url"' not in html
    assert "Import from URLs" not in html
    assert 'type="submit">Save settings</button>' in html


def test_portal_toast_uses_top_layer_and_has_a_close_button() -> None:
    html = Path("web/index.html").read_text(encoding="utf-8")

    assert 'id="portal-toast"' in html
    assert 'popover="manual"' in html
    assert 'data-toast-message' in html
    assert 'data-toast-close' in html


def test_voice_download_dialog_has_an_accessible_progress_state() -> None:
    html = Path("web/index.html").read_text(encoding="utf-8")

    assert 'id="download-voice-progress"' in html
    assert '<progress' in html
    assert 'data-i18n-aria-label="voice.downloadProgress"' in html
    assert 'data-i18n="voice.downloading"' in html
    assert 'data-i18n="voice.downloadingHint"' in html


def test_composer_uses_a_translucent_blurred_surface() -> None:
    css = Path("web/styles.css").read_text(encoding="utf-8")

    assert "--panel-surface: color-mix(in srgb, var(--surface) 50%, transparent)" in css
    assert "background: var(--panel-surface)" in css
    assert "backdrop-filter: blur(16px)" in css
    assert "-webkit-backdrop-filter: blur(16px)" in css


def test_modal_and_composer_actions_share_voice_setup_sizing() -> None:
    css = Path("web/styles.css").read_text(encoding="utf-8")

    assert "--action-height: 42px" in css
    assert "--action-font-size: 13px" in css
    assert ".dialog-actions .quiet-button, .composer-toolbar-actions .quiet-button" in css
    assert "min-height: var(--action-height)" in css
    assert "font-size: var(--action-font-size)" in css
    assert ".composer-toolbar-actions .code-control, .composer-toolbar-actions .composer-size-toggle" in css
    assert "padding: 0; place-items: center" in css


def test_download_voice_has_one_heading_and_send_button_has_no_arrow() -> None:
    html = Path("web/index.html").read_text(encoding="utf-8")
    download_start = html.index('id="download-voice-dialog"')
    download_end = html.index("</dialog>", download_start)
    download_dialog = html[download_start:download_end]
    send_start = html.index('id="send-request"')
    send_end = html.index("</button>", send_start)
    send_button = html[send_start:send_end]

    assert 'data-i18n="voice.downloadRequired"' not in download_dialog
    assert download_dialog.count("<h2") == 1
    assert 'data-i18n="voice.download"' in download_dialog
    assert 'aria-hidden="true"' not in send_button
    assert "→" not in send_button


def test_composer_has_localized_stop_button_and_non_overlapping_queue_polling() -> None:
    html = Path("web/index.html").read_text(encoding="utf-8")
    app = Path("web/js/app.js").read_text(encoding="utf-8")
    css = Path("web/styles.css").read_text(encoding="utf-8")
    stop_start = html.index('id="stop-playback"')
    send_start = html.index('id="send-request"')

    assert stop_start < send_start
    assert 'id="stop-playback" type="button" disabled' in html
    assert 'data-i18n="composer.stop"' in html
    assert 'postApi("queueInfo", {mode: "min"})' in app
    assert 'postApi("stop", {})' in app
    assert "setTimeout(pollQueueInfo, QUEUE_POLL_INTERVAL_MS)" in app
    assert ".stop-button" in css
    assert "background: var(--danger)" in css


def test_voice_dynamic_fallbacks_are_localized() -> None:
    voices = Path("web/js/voices.js").read_text(encoding="utf-8")

    for key in (
        "voice.unknown",
        "voice.files",
        "voice.loadError",
        "voice.downloadError",
        "voice.importError",
        "voice.selectFilesError",
        "voice.identityRequired",
        "voice.rightsRequired",
    ):
        assert f'translate("{key}")' in voices

    for fallback in (
        "license unknown",
        "the voice files",
        "Unable to load voices",
        "Voice download failed",
        "Voice import failed",
        "Select one .onnx model and one .onnx.json config",
        "Custom voice name and license are required",
        "Confirm that you have the right to use this voice",
    ):
        assert fallback not in voices
