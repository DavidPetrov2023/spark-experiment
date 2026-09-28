#pragma once

// Zkopirovat na device_config.h (ten je v .gitignore) a vyplnit.

// Telemetrie na /devices/ vcetne tokenu zarizeni. Token urcuje zaznam
// v dashboardu a pres jeho odpoved chodi prikaz ota_update, takze bez nej
// se deska uz zadnou dalsi OTA nedozvi.
#define TELEMETRY_URL "https://example.invalid/devices/api.php?token=BENCHMARK"

// Nepovinne. WiFi se bere z NVS, kam ji ulozil firmware robota (pres BLE
// z aplikace), a OTA NVS nemaze. Tohle je jen pro cerstve flashnutou desku.
#define WIFI_FALLBACK_SSID ""
#define WIFI_FALLBACK_PASS ""
