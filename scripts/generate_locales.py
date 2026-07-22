"""Generate the complete, reviewable portal locale catalog."""

from __future__ import annotations

import json
from pathlib import Path


BASE = {
    "languageName": "English",
    "nav.voice": "Voice",
    "nav.network": "Network",
    "nav.general": "General",
    "nav.language": "Language",
    "theme.dark": "Use dark theme",
    "theme.light": "Use light theme",
    "chat.eyebrow": "TEXT TO SPEECH",
    "chat.region": "Text to speech conversation",
    "chat.private": "Runs on this device",
    "chat.readyTitle": "Ready when you are",
    "chat.readyBody": "Edit the JSON request below. Requests and responses stay visible only until this page is reloaded.",
    "composer.request": "REQUEST JSON",
    "composer.reset": "Reset",
    "composer.maximize": "Maximize request editor",
    "composer.restore": "Restore request editor",
    "composer.status": "JSON is validated before sending",
    "composer.send": "Send request",
    "composer.sending": "Sending request…",
    "composer.received": "Response received",
    "composer.transportError": "Transport error",
    "code.copy": "Copy JSON",
    "code.copied": "JSON copied",
    "code.wordWrap": "Word wrap",
    "code.lineNumbers": "Line numbers",
    "dialog.invalidJson": "Invalid JSON",
    "dialog.invalidJsonMessage": "The request is not valid JSON at line {line}, column {column}.",
    "dialog.close": "Close",
    "dialog.cancel": "Cancel",
    "dialog.save": "Save settings",
    "dialog.return": "Return to editor",
    "dialog.resetMessage": "Do you really want to reset the text in the panel?",
    "dialog.confirmReset": "Reset text",
    "language.search": "Search languages",
    "language.noResults": "No languages found",
    "chat.request": "request",
    "chat.response": "response",
    "chat.copy": "Copy",
    "chat.copied": "Copied",
    "settings.saving": "Saving…",
    "settings.saved": "Settings saved",
    "settings.applied": "Settings applied immediately",
    "theme.applied": "Theme applied immediately",
    "voice.title": "Voice Setup",
    "voice.current": "Current voice: {name}",
    "voice.language": "Language: {language}",
    "voice.volume": "Volume",
    "voice.volumeControl": "Voice volume",
    "voice.search": "Search voices",
    "voice.searchPlaceholder": "Name, language, or quality",
    "voice.filter": "Filter",
    "voice.filter.all": "All voices",
    "voice.filter.downloaded": "Already downloaded",
    "voice.noResults": "No voices found",
    "voice.unknown": "Unknown",
    "voice.unavailable": "unavailable",
    "voice.installed": "installed",
    "voice.downloadRequired": "download required",
    "voice.confirmationRequired": "license confirmation required",
    "voice.custom": "Custom",
    "voice.import": "Import a custom voice",
    "voice.customName": "Custom voice name",
    "voice.license": "Voice license",
    "voice.modelFile": "Piper model file",
    "voice.configFile": "Piper config file",
    "voice.confirmRights": "I confirm I have the right to use this voice",
    "voice.importLocal": "Import local voice",
    "voice.confirmLicense": "Confirm voice license",
    "voice.freeDownloadMessage": "{name} is not installed. Download {size} and use this voice?",
    "voice.restrictedDownloadMessage": "{name} uses license {license}. {notice} Continue with the download?",
    "voice.downloadAndUse": "Download and use",
    "voice.download": "Download voice",
    "voice.downloading": "Downloading voice…",
    "voice.downloadingHint": "The download is in progress. This may take a few minutes.",
    "voice.downloadProgress": "Voice download progress",
    "voice.files": "the voice files",
    "voice.loadError": "Unable to load voices",
    "voice.downloadError": "Voice download failed",
    "voice.importError": "Voice import failed",
    "voice.selectFilesError": "Select one .onnx model and one .onnx.json config",
    "voice.identityRequired": "Custom voice name and license are required",
    "voice.rightsRequired": "Confirm that you have the right to use this voice",
    "voice.downloaded": "Voice downloaded",
    "voice.imported": "Voice imported",
    "voice.saved": "Voice settings saved",
    "network.title": "Network Setup",
    "network.remoteManagement": "Enable remote management",
    "network.remoteWarning": "Remote management exposes setup controls to your LAN.",
    "general.title": "General Setup",
}

LOCALE_OVERRIDES = {
    "cs": {
        "composer.maximize": "Maximalizovat editor požadavku",
        "composer.restore": "Obnovit normální velikost editoru",
        "code.copy": "Kopírovat JSON",
        "code.copied": "JSON zkopírován",
        "code.wordWrap": "Zalamování řádků",
        "code.lineNumbers": "Čísla řádků",
        "voice.downloading": "Stahování hlasu…",
        "voice.downloadingHint": "Stahování probíhá. Může trvat několik minut.",
        "voice.downloadProgress": "Průběh stahování hlasu",
    },
    "de": {
        "voice.unknown": "Unbekannt",
        "voice.files": "die Sprachdateien",
        "voice.loadError": "Stimmen konnten nicht geladen werden",
        "voice.downloadError": "Stimme konnte nicht heruntergeladen werden",
        "voice.importError": "Stimme konnte nicht importiert werden",
        "voice.selectFilesError": "Wählen Sie ein .onnx-Modell und eine .onnx.json-Konfiguration aus",
        "voice.identityRequired": "Name und Lizenz der benutzerdefinierten Stimme sind erforderlich",
        "voice.rightsRequired": "Bestätigen Sie, dass Sie diese Stimme verwenden dürfen",
    },
}

# Native name plus the most visible shell vocabulary. Less common status prose uses the
# English fallback until a language owner supplies a reviewed wording.
LOCALES = {
    "bg": ("Български", "Глас", "Мрежа", "Общи", "Език", "Разговор", "Готови сме", "Изпрати заявка", "Търсене на езици", "Затвори", "Отказ", "Запази настройките"),
    "cs": ("Čeština", "Hlas", "Síť", "Obecné", "Jazyk", "Konverzace", "Můžeme začít", "Odeslat požadavek", "Hledat jazyky", "Zavřít", "Zrušit", "Uložit nastavení"),
    "da": ("Dansk", "Stemme", "Netværk", "Generelt", "Sprog", "Samtale", "Klar, når du er", "Send anmodning", "Søg efter sprog", "Luk", "Annuller", "Gem indstillinger"),
    "de": ("Deutsch", "Stimme", "Netzwerk", "Allgemein", "Sprache", "Unterhaltung", "Bereit, wenn Sie es sind", "Anfrage senden", "Sprachen suchen", "Schließen", "Abbrechen", "Einstellungen speichern"),
    "el": ("Ελληνικά", "Φωνή", "Δίκτυο", "Γενικά", "Γλώσσα", "Συνομιλία", "Έτοιμοι όταν είστε", "Αποστολή αιτήματος", "Αναζήτηση γλωσσών", "Κλείσιμο", "Ακύρωση", "Αποθήκευση ρυθμίσεων"),
    "en": ("English", "Voice", "Network", "General", "Language", "Conversation", "Ready when you are", "Send request", "Search languages", "Close", "Cancel", "Save settings"),
    "es": ("Español", "Voz", "Red", "General", "Idioma", "Conversación", "Listo cuando quieras", "Enviar solicitud", "Buscar idiomas", "Cerrar", "Cancelar", "Guardar ajustes"),
    "et": ("Eesti", "Hääl", "Võrk", "Üldine", "Keel", "Vestlus", "Valmis, kui sina oled", "Saada päring", "Otsi keeli", "Sulge", "Loobu", "Salvesta seaded"),
    "fi": ("Suomi", "Ääni", "Verkko", "Yleiset", "Kieli", "Keskustelu", "Valmiina, kun olet", "Lähetä pyyntö", "Hae kieliä", "Sulje", "Peruuta", "Tallenna asetukset"),
    "fr": ("Français", "Voix", "Réseau", "Général", "Langue", "Conversation", "Prêt quand vous l'êtes", "Envoyer la requête", "Rechercher des langues", "Fermer", "Annuler", "Enregistrer les paramètres"),
    "ga": ("Gaeilge", "Guth", "Líonra", "Ginearálta", "Teanga", "Comhrá", "Réidh nuair atá tú", "Seol iarratas", "Cuardaigh teangacha", "Dún", "Cealaigh", "Sábháil socruithe"),
    "hr": ("Hrvatski", "Glas", "Mreža", "Općenito", "Jezik", "Razgovor", "Spremni kad i vi", "Pošalji zahtjev", "Pretraži jezike", "Zatvori", "Odustani", "Spremi postavke"),
    "hu": ("Magyar", "Hang", "Hálózat", "Általános", "Nyelv", "Beszélgetés", "Készen állunk", "Kérés küldése", "Nyelvek keresése", "Bezárás", "Mégse", "Beállítások mentése"),
    "it": ("Italiano", "Voce", "Rete", "Generale", "Lingua", "Conversazione", "Pronto quando vuoi", "Invia richiesta", "Cerca lingue", "Chiudi", "Annulla", "Salva impostazioni"),
    "lt": ("Lietuvių", "Balsas", "Tinklas", "Bendra", "Kalba", "Pokalbis", "Pasiruošę, kai būsite", "Siųsti užklausą", "Ieškoti kalbų", "Uždaryti", "Atšaukti", "Išsaugoti nustatymus"),
    "lv": ("Latviešu", "Balss", "Tīkls", "Vispārīgi", "Valoda", "Saruna", "Gatavi, kad esat", "Sūtīt pieprasījumu", "Meklēt valodas", "Aizvērt", "Atcelt", "Saglabāt iestatījumus"),
    "mt": ("Malti", "Vuċi", "Netwerk", "Ġenerali", "Lingwa", "Konversazzjoni", "Lesti meta tkun int", "Ibgħat talba", "Fittex lingwi", "Agħlaq", "Ikkanċella", "Issejvja s-settings"),
    "nl": ("Nederlands", "Stem", "Netwerk", "Algemeen", "Taal", "Gesprek", "Klaar wanneer u dat bent", "Verzoek verzenden", "Talen zoeken", "Sluiten", "Annuleren", "Instellingen opslaan"),
    "pl": ("Polski", "Głos", "Sieć", "Ogólne", "Język", "Rozmowa", "Gotowe, gdy Ty jesteś", "Wyślij żądanie", "Szukaj języków", "Zamknij", "Anuluj", "Zapisz ustawienia"),
    "pt": ("Português", "Voz", "Rede", "Geral", "Idioma", "Conversa", "Pronto quando estiver", "Enviar pedido", "Pesquisar idiomas", "Fechar", "Cancelar", "Guardar definições"),
    "ro": ("Română", "Voce", "Rețea", "General", "Limbă", "Conversație", "Gata când sunteți", "Trimite cererea", "Caută limbi", "Închide", "Anulează", "Salvează setările"),
    "sk": ("Slovenčina", "Hlas", "Sieť", "Všeobecné", "Jazyk", "Konverzácia", "Môžeme začať", "Odoslať požiadavku", "Hľadať jazyky", "Zavrieť", "Zrušiť", "Uložiť nastavenia"),
    "sl": ("Slovenščina", "Glas", "Omrežje", "Splošno", "Jezik", "Pogovor", "Pripravljeni, ko ste vi", "Pošlji zahtevo", "Išči jezike", "Zapri", "Prekliči", "Shrani nastavitve"),
    "sv": ("Svenska", "Röst", "Nätverk", "Allmänt", "Språk", "Konversation", "Redo när du är", "Skicka begäran", "Sök språk", "Stäng", "Avbryt", "Spara inställningar"),
    "ru": ("Русский", "Голос", "Сеть", "Общие", "Язык", "Диалог", "Готовы, когда вы готовы", "Отправить запрос", "Поиск языков", "Закрыть", "Отмена", "Сохранить настройки"),
    "zh-Hans": ("简体中文", "语音", "网络", "常规", "语言", "对话", "准备就绪", "发送请求", "搜索语言", "关闭", "取消", "保存设置"),
    "ja": ("日本語", "音声", "ネットワーク", "一般", "言語", "会話", "準備できました", "リクエストを送信", "言語を検索", "閉じる", "キャンセル", "設定を保存"),
    "ar": ("العربية", "الصوت", "الشبكة", "عام", "اللغة", "المحادثة", "جاهز عندما تكون جاهزًا", "إرسال الطلب", "البحث عن اللغات", "إغلاق", "إلغاء", "حفظ الإعدادات"),
    "uk": ("Українська", "Голос", "Мережа", "Загальні", "Мова", "Розмова", "Готові, коли ви готові", "Надіслати запит", "Пошук мов", "Закрити", "Скасувати", "Зберегти налаштування"),
    "no": ("Norsk", "Stemme", "Nettverk", "Generelt", "Språk", "Samtale", "Klar når du er", "Send forespørsel", "Søk etter språk", "Lukk", "Avbryt", "Lagre innstillinger"),
}


def main() -> None:
    output = Path(__file__).resolve().parents[1] / "master-data" / "i18n"
    output.mkdir(parents=True, exist_ok=True)
    keys = (
        "languageName", "nav.voice", "nav.network", "nav.general", "nav.language",
        "chat.readyTitle", "composer.send", "language.search",
        "dialog.close", "dialog.cancel", "dialog.save",
    )
    for code, values in LOCALES.items():
        translated_values = values[:5] + values[6:]
        translated = BASE | dict(zip(keys, translated_values, strict=True))
        translated.update(LOCALE_OVERRIDES.get(code, {}))
        existing_path = output / f"{code}.json"
        if existing_path.is_file():
            existing = json.loads(existing_path.read_text(encoding="utf-8"))
            for key in ("dialog.resetMessage", "dialog.confirmReset"):
                if key in existing:
                    translated[key] = existing[key]
        existing_path.write_text(
            json.dumps(translated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
