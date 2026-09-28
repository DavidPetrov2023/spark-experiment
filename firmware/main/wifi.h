#pragma once

#include <stdbool.h>
#include "esp_err.h"

// Spusti WiFi a pripojuje se porad dokola. ESP_ERR_NOT_FOUND = zadne udaje.
esp_err_t wifi_start(void);

bool wifi_connected(void);
