import json
import re
from pathlib import Path


EXPECTED = {
    "bg", "cs", "da", "de", "el", "en", "es", "et", "fi", "fr", "ga", "hr",
    "hu", "it", "lt", "lv", "mt", "nl", "pl", "pt", "ro", "sk", "sl", "sv",
    "ru", "zh-Hans", "ja", "ar", "uk", "no",
}
PLACEHOLDER = re.compile(r"\{[A-Za-z]+\}")


def test_all_locale_files_have_exactly_the_english_keys() -> None:
    paths = {path.stem: path for path in Path("master-data/i18n").glob("*.json")}
    assert set(paths) == EXPECTED
    baseline = json.loads(paths["en"].read_text(encoding="utf-8"))
    required = {
        "composer.benchmark", "composer.maximize", "composer.restore",
        "code.copy", "code.copied", "code.wordWrap", "code.lineNumbers",
        "chat.region", "chat.firstMessageNotice", "voice.title", "voice.current",
        "voice.language", "voice.volume", "voice.search", "voice.filter.all",
        "voice.filter.downloaded", "voice.filter", "voice.noResults",
        "voice.unknown", "voice.unavailable", "voice.volumeControl",
        "voice.download", "voice.confirmLicense",
        "voice.import", "voice.license", "voice.downloadAndUse",
        "voice.files", "voice.downloading", "voice.downloadingHint",
        "voice.downloadProgress", "voice.loadError", "voice.downloadError",
        "voice.importError", "voice.selectFilesError",
        "voice.identityRequired", "voice.rightsRequired",
        "network.title", "network.remoteManagement", "network.remoteWarning",
        "general.title", "dialog.cancel", "dialog.save",
    }
    assert required <= baseline.keys()
    for locale, path in paths.items():
        translated = json.loads(path.read_text(encoding="utf-8"))
        assert list(translated) == list(baseline), locale
        assert all(isinstance(value, str) and value.strip() for value in translated.values())


def test_locale_controller_uses_browser_local_storage_and_text_content() -> None:
    source = Path("web/js/i18n.js").read_text(encoding="utf-8")

    assert "localStorage" in source
    assert ".textContent" in source
    assert "innerHTML" not in source


def test_translations_preserve_placeholders_and_are_not_english_fallbacks() -> None:
    root = Path("master-data/i18n")
    baseline = json.loads((root / "en.json").read_text(encoding="utf-8"))

    for path in root.glob("*.json"):
        if path.stem == "en":
            continue
        translated = json.loads(path.read_text(encoding="utf-8"))
        unchanged = []
        for key, english_value in baseline.items():
            translated_value = translated[key]
            assert sorted(PLACEHOLDER.findall(translated_value)) == sorted(
                PLACEHOLDER.findall(english_value)
            ), f"{path.stem}: {key}"
            assert "VAR_" not in translated_value, f"{path.stem}: {key}"
            if key != "languageName" and translated_value == english_value:
                unchanged.append(key)
        assert len(unchanged) <= 10, f"{path.stem}: {unchanged}"
