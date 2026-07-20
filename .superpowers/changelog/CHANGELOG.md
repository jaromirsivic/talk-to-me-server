# Changelog

## Průběžné streamované přehrávání TTS

- Přehrávání jobu začíná ihned po dokončení první hodnoty bez čekání na syntézu všech dalších hodnot.
- Hodnoty se přehrávají ve vstupním pořadí v jednom kontinuálním `OutputStream`.
- Při čekání na následující hodnotu callback generuje pouze aktuálně potřebné ticho.
- Dokončení používá `CallbackStop` a čeká na drain posledního hardwarového bufferu.
- Stavový model podporuje souběžnou syntézu a přehrávání a zachovává FIFO mezi joby.
- Byly doplněny testy časného startu, návaznosti hodnot, čekacího ticha a korektního dokončení streamu.

## Ovládací tokeny, segmentace textu a rozšíření rozhraní TTS

- JSON editor i chatové karty mají ve výchozím stavu zapnuté zalamování řádků a vypnuté číslování řádků, tlačítko maximalizace má lokalizovanou nápovědu.
- Rozšířené statistiky uvádějí u každé položky `values` stabilní `workerIndex` a `totalWorkers`.
- Samostatné tokeny gongů přehrávají dodané WAV soubory a tokeny pauz generují ticho, přičemž `{{PAUSE}}` trvá 1 000 ms a parametrizovaná pauza je omezena na 0 až 15 000 ms.
- Endpoint `textToSpeech` přijímá právě jedno z polí `value` nebo `values`. Jednotný text se v hlavním procesu rozdělí podle hranic vět eSpeak a oddělí gongové a pauzové tokeny bez změny worker IPC.
- Před první zprávou se zobrazuje lokalizované upozornění na možné delší načítání neuronové sítě.
- `startserver.bat` vypisuje PID, port, naslouchací adresy a URL portálu a ponechá okno viditelné nejméně pět sekund.
- Byly doplněny WAV prostředky, dokumentace a jednotkové, integrační, smoke a E2E testy.

## Instalační a řídicí skripty pro podporované platformy

- Windows používá instalátory `install.bat` a `install.ps1` a řídicí skripty `start-server.bat` a `stop-server.bat`.
- Linux a macOS sdílejí skripty `install.sh`, `start-server.sh` a `stop-server.sh` pro x86_64 a ARM64.
- Unixový instalátor používá projektový `uv` 0.11.29 a před rozbalením kontroluje SHA-256 staženého archivu.
- Unixové řídicí skripty bezpečně sledují PID, ověřují vlastnictví procesu, kontrolují port a zapisují provozní výstup do logů.
- Dokumentace a smoke testy byly aktualizovány pro nové názvy a podporované platformy.
- Shellové skripty mají v Gitu vynucené LF konce řádků.

## Jazyk hlasu v konfiguraci

- Do konfigurace `voice` byl přidán parametr `language`, který se automaticky odvozuje z prefixu `speaker`.
- Načtení starší konfigurace odvozený jazyk doplní a zpracování `setSetup` jej před uložením znovu korektně nastaví.
- `getSetup` vrací odvozený jazyk v odpovědi a výchozí `setup.json` obsahuje odpovídající hodnotu.
- Byly doplněny jednotkové a integrační testy odvození, migrace a REST API.

## Výběr a mazání nainstalovaných hlasů

- Kliknutí na řádek nainstalovaného hlasu otevře potvrzení jeho výběru a potvrzená změna se odešle přes `setSetup` až po uložení nastavení.
- Mazání se spouští samostatným červeně obtaženým tlačítkem ve formátu `Smazat (velikost)`.
- Nainstalované hlasy se řadí před hlasy dostupné ke stažení, takže tlačítka pro smazání jsou viditelná ihned po otevření dialogu.
- Dialog výběru hlasu a nové ovládací prvky jsou přeložené do všech podporovaných jazyků a respektují pravidla přístupnosti.
- Byly doplněny kontraktní, lokalizační, E2E a mobilní testy.
