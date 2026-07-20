# Necommitnuté změny

- Do konfigurace `voice` byl přidán parametr `language`, který se vždy odvozuje z prefixu `speaker`.
- Načítání starších konfigurací automaticky doplní odvozený jazyk do `setup.json`.
- Zpracování `setSetup` před uložením znovu odvodí jazyk a `getSetup` jej vrací v odpovědi.
- Byly doplněny unit a integrační testy odvození, migrace a REST API.
