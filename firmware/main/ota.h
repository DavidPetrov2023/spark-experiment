#pragma once

#include "esp_err.h"

// Po startu: kdyz je tohle cerstva OTA ("zkusebni" image), spusti hlidani.
// Nepotvrdi-li se do OTA_CONFIRM_TIMEOUT_S, vrati se predchozi firmware.
void ota_boot_check(void);

// Firmware funguje (dostal se na server), zrusit rollback.
void ota_confirm(void);

// Stahne a nainstaluje firmware z URL, pak restart. Bezi ve vlastnim tasku.
esp_err_t ota_start(const char *url);
