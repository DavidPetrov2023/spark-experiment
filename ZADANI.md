# Úloha X4: hlášení od uživatele

Dashboard u desky ukazuje prázdné sloupce RSSI a MinFreeHeap. Server je čeká v objektu LiveStatus:

- `RSSI`: síla signálu WiFi v dBm (celé číslo);
- `MinFreeHeap`: nejnižší volný heap od startu, v bajtech.

Deska je zatím vůbec neposílá. Když se RSSI zrovna nepodaří zjistit, pole RSSI neposílej vůbec (server by jinak uložil nesmysl). Ostatní pole telemetrie musí zůstat beze změny.
