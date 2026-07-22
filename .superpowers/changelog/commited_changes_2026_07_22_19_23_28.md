# Necommitnuté změny

- Response karty v chatu nyní používají decentní zelené pozadí pro `reasonCode: 200` a červené pozadí sdílené s upozorněním po prvním requestu pro ostatní hodnoty. Doplněny byly kontrastní varianty tmavého motivu.
- Přidána best-effort globální zkratka `Ctrl+Shift+X` pro Windows, macOS a Linux. Zkratka thread-safe volá stejnou serializovanou operaci Stop jako REST endpoint a její selhání neovlivní běh serveru.
- Doplněna závislost `pynput`, provozní dokumentace, cache-busting statických assetů a automatické testy pro styly, životní cyklus listeneru, opakování zkratky a zachování chování Stop.
- Ověření: Ruff bez nálezů, 243 jednotkových, integračních a smoke testů prošlo, 2 hardwarové testy byly přeskočeny a 49 end-to-end testů prošlo.
