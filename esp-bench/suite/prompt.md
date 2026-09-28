Jsi v repozitáři firmwaru pro ESP32 (ESP-IDF v5.2.6). Přišlo hlášení chyby:

> {task}

Najdi příčinu a oprav ji.

Pravidla:
- Oprav jen tuto chybu, nic jiného neměň.
- Na OTA nesahej: ota.c, potvrzení firmwaru po telemetrii ani WiFi (viz README).
- Tyto části hlídá automatická kontrola a nesmí se měnit vůbec, ani drobně:
  - soubory ota.c, ota.h, wifi.c, wifi.h, telemetry.h, version.h, device_config.h, partitions.csv, sdkconfig.defaults, CMakeLists.txt a main/CMakeLists.txt;
  - v telemetry.c funkce on_http, handle_command, post, telemetry_task, telemetry_start a konstanta TELEMETRY_INTERVAL_S; payload() musí dál posílat PowerMode "ACTIVE";
  - v main.c pořadí ota_boot_check → wifi_start → telemetry_start a motory držené v nule;
  - funkce OTA (ota_confirm, ota_start, ota_boot_check, esp_ota_*, esp_https_ota*) se nesmí volat na žádném novém místě, ani v nových souborech.
- Nové soubory jen ve složce main/.
- Build ověříš příkazem: sh build.sh
- Nic nenahrávej na desku ani na server.
- Na konci stručně napiš, co bylo příčinou a co jsi změnil.
