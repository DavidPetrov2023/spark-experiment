# ESPTest

Minimální firmware na desku Zobo robota (ESP32): bliká červenou LED
a umí přijmout další OTA. Nic víc, žádné BLE, motory, MQTT ani spánek.
Vychází z `C:\Cloud\AI\Zobo\zobo_esp32`.

Vlastní deska to není. Robot se na test dočasně přepne a potom se mu vrátí
jeho firmware.

## Jak to jede

```
python release.py --push     # build, nahrát na server, OTA na desku, počkat na potvrzení
python release.py --robot    # vrátit desce firmware robota
```

Před každým `release.py` zvednout `FIRMWARE_VERSION` v `main/version.h`.
Stejnou verzi dvakrát nenahraje: dashboard by pak nepoznal, že OTA doběhla.

`--push` přepne záznamu desky na `/devices/` produkt na **ESP Test**, pošle
Push OTA a čeká, až deska nahlásí novou verzi. `--robot` udělá totéž
s produktem **Robot**, takže deska dostane poslední `zobo_esp32.bin`
ze serveru. Jde to i ručně v `/devices/`: přepínač produktu a Push OTA.

## Co je kde

| | |
|---|---|
| `main/main.c` | piny, blikání |
| `main/wifi.c` | WiFi z NVS robota (namespace `wifi_creds`), připojuje se donekonečna |
| `main/telemetry.c` | POST na `/devices/` každých 5 s, z odpovědi příkaz `ota_update` |
| `main/ota.c` | stažení a instalace, rollback |
| `main/device_config.h` | token záznamu a nepovinná WiFi, v `.gitignore`, vzor je `.example` |
| `release.py` | build, upload do slotu `esptest` na `/robot/`, OTA |

Na serveru má ESPTest vlastní slot (`robot/products.php`, produkt
`esptest`, soubor `esptest.bin`). Kdyby šel do robotího, přepsal by
`zobo_esp32.bin`, který si stahuje i aplikace.

## Pojistka: rollback

Deska jde aktualizovat jen po síti. Firmware, který se nedostane na server,
by ji odřízl a zachránit ji by šlo jen kabelem. Proto:

- nový firmware po OTA naběhne jako zkušební a potvrdí se až **první
  úspěšnou telemetrií** (`ota_confirm()` v `telemetry.c`);
- když se do 120 s nepotvrdí, vrátí se předchozí firmware (`ota.c`).

Kdo bude přepisovat `telemetry.c` nebo `wifi.c`, ať to potvrzení zachová,
jinak rollback proběhne po každé OTA.

Chráněný je start, ne běh. Firmware, který se jednou potvrdí a pak spadne
nebo přestane posílat telemetrii, už se sám nevrátí.

## Piny

LED jsou aktivní v LOW: červená 27, zelená 14, modrá 12, hlavní 5.
Motory (PWM 25 a 16, směr 26 a 17) drží firmware v nule. Po resetu jsou
ve vysoké impedanci a driver motoru by na plovoucím vstupu mohl rozjet pás.

## Build

ESP-IDF **v5.2.6**, stejná verze jako robot. Bootloader na desce je z jeho
buildu a OTA ho nemění. `release.py` si ho najde sám. Ručně z PowerShellu:

```powershell
. "$env:USERPROFILE\esp\v5.2.6\esp-idf\export.ps1" *> $null
idf.py build
```

Z Git Bashe `idf.py` nejede.
