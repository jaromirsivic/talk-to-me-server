# Budoucí vylepšení

## Záložní segmentace textu

### Dotaz

Když pošlu do textToSpeech request, který vypadá takto:

```json
{
  "value": "If you here this voice then talk to me server works. You can play positive gong {{play('pos_fsdfds.wav')}} or neutral gong {{play('neutral_gong.wav')}} or negative gong {{play('negative_gong.wav')}}. And make a pause {{pause(2000)}}",
  "importance": "high",
  "volumeMultiplier": 0.95,
  "calculateStats": false,
  "waitUntilPlaybackFinished": false
}
```

tak se mi vrátí response:

```json
{
  "version": 1,
  "reasonCode": 503,
  "reasonText": "Text segmentation is unavailable"
}
```

Hlas, který používám je ljspeech. Když používám hlas jirka, tak se to neděje.

Jaký je důvod? Proč se tohle děje?

Příčinou není neexistující zvuk `pos_fsdfds.wav`. Chyba nastane dříve, při segmentaci pole `value`.

Metadata hlasu ljspeech obsahují neplatné absolutní cesty:

```text
D:\git\talktome\.worktrees\talktome-server\data\voices\official\en_US-ljspeech-medium\...
```

Tyto soubory už neexistují. Skutečný hlas se nachází zde:

```text
C:\git\talk-to-me-server\data\voices\official\en_US-ljspeech-medium\...
```

Průběh chyby je tento:

1. `textToSpeech` přijme pole `value`.
2. Server chce text rozdělit na věty podle konfigurace aktuálního hlasu.
3. Katalog nesprávně označí ljspeech jako nainstalovaný pouze podle existence `voice.json`.
4. Segmenter se pokusí načíst konfiguraci z neexistující cesty na disku D:.
5. Vznikne `FileNotFoundError`.
6. REST vrstva tuto výjimku skryje pod obecnou odpověď:

```json
{
  "reasonCode": 503,
  "reasonText": "Text segmentation is unavailable"
}
```

U hlasu jirka se chyba neprojeví, protože jeho cesta na disku D: stále existuje.

Chybějící WAV by se zpracovával až po úspěšné segmentaci a podle nové logiky by se měl pouze přeskočit.

Krátkodobým řešením je znovu nainstalovat ljspeech z aktuálního projektu. Správná systémová oprava je přestat ukládat nepřenosné absolutní cesty do `voice.json`, odvozovat soubory relativně od adresáře hlasu a při sestavení katalogu ověřovat jejich existenci. V této diagnostice jsem nic neměnil.

Provedl jsi diagnostiku? Pokud ne, napadlo mě, že bychom to mohli udělat takto. Pokud dojde při segmentaci textu k chybě, například protože chybí nějaký soubor nebo z jiného důvodu, tak to systém odchytí a provede fallback na jednoduchou segmentaci, kdy text rozdělí na věty pomocí toho, že detekuje tečky, otazníky a vykřičníky.

Řekni mi, jestli je to dobrý nápad nebo špatný. Zatím nic neimplementuj. Případně přijdi s vlastním návrhem, jak to vylepšit.

### Odpověď

Ano, diagnostiku jsem provedl. Původní příčina byla potvrzena: neplatné absolutní cesty v manifestu hlasu `ljspeech`. Tyto cesty jsme již opravili, včetně mechanismu stahování a importu hlasů.

Navržený fallback je dobrý jako dodatečná ochrana, ale neměl by řešit každou chybu segmentace.

Pokud chybí model nebo konfigurační soubor hlasu, jednoduchá segmentace sice proběhne, ale následná syntéza bude pravděpodobně stejně neúspěšná. V takovém případě je lepší vrátit konkrétní chybu typu:

```json
{
  "reasonCode": 503,
  "reasonText": "Selected voice is incomplete or unavailable"
}
```

Fallback doporučuji použít tehdy, když:

- hlas má platný model i konfiguraci,
- selže pouze pokročilý mechanismus rozdělování vět,
- text lze stále bezpečně předat syntéze.

Doporučené řešení:

1. Před segmentací ověřit existenci modelu a konfigurace vybraného hlasu.
2. Pokud hlas není kompletní, vrátit konkrétní diagnostickou chybu.
3. Pokud selže pouze pokročilá segmentace, zaznamenat varování do logu a použít jednoduchou segmentaci.
4. Jednoduchou segmentaci provádět samostatně uvnitř textových částí, aby zůstaly příkazy `{{play(...)}}` a `{{pause(...)}}` oddělené.
5. Zajistit, aby fallback nikdy neztratil ani nezměnil část původního textu.

Samotné dělení by nemělo být pouze na každé tečce. Je potřeba alespoň zohlednit:

- desetinná čísla jako `3.14`,
- trojtečky,
- více znamének jako `!?!`,
- interpunkci následovanou uvozovkou nebo závorkou,
- speciální příkazy `play` a `pause`.

Můj závěr: fallback je vhodný a zvýší odolnost serveru. Neměl by ale maskovat poškozenou nebo neúplnou instalaci hlasu. Nejlepší je kombinace kontroly hlasu, konkrétnější chybové odpovědi a jednoduché záložní segmentace pouze pro selhání segmentačního mechanismu.

V tomto kroku jsem nic neimplementoval ani nezměnil.
