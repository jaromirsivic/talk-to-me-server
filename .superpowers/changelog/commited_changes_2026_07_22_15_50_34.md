# Necommitované změny

- Stahování oficiálních hlasů a import vlastních hlasů nově ukládají do `voice.json` pouze relativní názvy `model.onnx` a `model.onnx.json`.
- Katalog hlasů vyhodnocuje relativní cesty vůči adresáři konkrétního manifestu.
- U starého manifestu s neplatnou absolutní cestou katalog automaticky použije odpovídající lokální soubor vedle `voice.json`.
- Existující manifesty hlasů `ljspeech` a `jirka` byly v lokálních aplikačních datech převedeny na relativní cesty.
- Doplněny regresní testy a ověřena segmentace původního požadavku hlasem `ljspeech`.
