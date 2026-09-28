# Úlohy

Každá úloha je větev. Zadání je hlášení od uživatele, model dostane jen příznak.

| Úloha | Obtížnost | Větev | Zadání (příznak) |
|---|---|---|---|
| B1 | základní | `uloha/B1` | Po nahrání tohoto firmwaru na desku bliká modrá LED místo červené. Červená nesvítí vůbec. Podle zadání projektu má blikat červená. |
| B2 | základní | `uloha/B2` | Červená LED po startu desky trvale svítí a nebliká. Má blikat: 500 ms svítí, 500 ms nesvítí. |
| B3 | základní | `uloha/B3` | Dashboard ukazuje u desky uptime zhruba 1000× větší, než odpovídá skutečnosti: po minutě provozu hlásí kolem 60 000. Server čeká uptime v sekundách. |
| B4 | základní | `uloha/B4` | Deska po několika hodinách provozu spadne a restartuje se. Při sledování volné paměti (esp_get_free_heap_size) je vidět, že volný heap klesá o několik set bajtů zhruba každých 5 sekund. |
| H1 | těžší | `uloha/H1` | V sériovém výpisu desky se zhruba každých 5 sekund opakuje: |
| H2 | těžší | `uloha/H2` | Uptime desky v dashboardu roste správně, ale zhruba po 35 minutách provozu skočí do záporných hodnot (kolem −2147) a odtud zase roste. Asi po dalších 70 minutách se to opakuje. Restart desky to vždy na chvíli spraví. Server čeká uptime v sekundách. |
| H3 | těžší | `uloha/H3` | Červená LED bliká mnohem rychleji, než má: přepíná se zhruba každých 50 ms. Má svítit 500 ms a 500 ms nesvítit. |
| X1 | nejtěžší | `uloha/X1` | Po poslední úpravě firmwaru jsou na desce dvě potíže: |
| X2 | nejtěžší | `uloha/X2` | Pole EventState v telemetrii má ukazovat, jestli červená LED právě svítí: `blink_on`, nebo `blink_off`. Většinou to sedí, ale zhruba jednou za pár dní přijde nesmyslná hodnota, třeba `blink_onf` nebo `blink_of`. Server ji odmítne a v dashboardu zůstane díra. Hlásí to víc desek a restart nepomáhá. |
| X3 | nejtěžší | `uloha/X3` | Po každé OTA se deska zhruba po dvou minutách vrátí na předchozí firmware. V sériovém výpisu je: |
| X4 | nejtěžší | `uloha/X4` | Dashboard u desky ukazuje prázdné sloupce RSSI a MinFreeHeap. Server je čeká v objektu LiveStatus: |
