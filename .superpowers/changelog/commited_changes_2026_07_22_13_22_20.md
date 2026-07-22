# Commitnuté změny

- Chybějící soubor z příkazu `play` se nově přeskočí a zpracování pokračuje další položkou.
- Přibyl stav úlohy `cancelled` a endpoint `POST /api/v1/stop`, který bezpečně zastaví aktivní zvuk, zruší frontu a probudí čekající klienty odpovědí 409.
- Audio přehrávač podporuje přerušení a po zastavení lze bez restartu přehrát další požadavek.
- Reset webového editoru nyní vyžaduje lokalizované potvrzení ve všech podporovaných jazycích.
- Výchozí obsah editoru byl nahrazen schváleným požadavkem s polem `value`.
- Tlačítko Benchmark, jeho data, endpoint, lokalizace a navázaná logika byly odstraněny.
- Byly doplněny jednotkové, integrační a E2E testy pro nové chování.
