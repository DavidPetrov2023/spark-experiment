#include "ota.h"

#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_crt_bundle.h"
#include "esp_https_ota.h"
#include "esp_log.h"
#include "esp_ota_ops.h"
#include "esp_system.h"

static const char *TAG = "OTA";

// Dost na pripojeni k WiFi i na prvni telemetrii s rezervou. Deska jde
// aktualizovat jen po siti, takze firmware, ktery se na server nedostane,
// se nesmi potvrdit: bez toho by zustala viset s obrazem, ktery dalsi OTA
// uz neprijme, a zachranit ji pujde jen kabelem.
#define OTA_CONFIRM_TIMEOUT_S 120

static volatile bool s_pending = false;
static volatile bool s_running = false;

static void confirm_watchdog(void *arg)
{
    vTaskDelay(pdMS_TO_TICKS(OTA_CONFIRM_TIMEOUT_S * 1000));
    if (s_pending) {
        ESP_LOGE(TAG, "firmware se do %d s nepotvrdil, vracim predchozi", OTA_CONFIRM_TIMEOUT_S);
        esp_ota_mark_app_invalid_rollback_and_reboot();
    }
    vTaskDelete(NULL);
}

void ota_boot_check(void)
{
    esp_ota_img_states_t state;
    const esp_partition_t *running = esp_ota_get_running_partition();
    if (esp_ota_get_state_partition(running, &state) == ESP_OK && state == ESP_OTA_IMG_PENDING_VERIFY) {
        ESP_LOGW(TAG, "zkusebni firmware z OTA, potvrdi se po prvni telemetrii");
        s_pending = true;
        xTaskCreate(confirm_watchdog, "ota_watchdog", 2048, NULL, 5, NULL);
    }
}

void ota_confirm(void)
{
    if (!s_pending) return;
    s_pending = false;
    esp_ota_mark_app_valid_cancel_rollback();
    ESP_LOGI(TAG, "firmware potvrzeny, rollback zrusen");
}

static void ota_task(void *arg)
{
    char *url = (char *)arg;
    ESP_LOGI(TAG, "stahuji %s", url);

    esp_http_client_config_t http = {
        .url = url,
        .timeout_ms = 30000,
        .keep_alive_enable = true,
        .crt_bundle_attach = esp_crt_bundle_attach,
        .buffer_size = 1024,
        .buffer_size_tx = 1024,
    };
    esp_https_ota_config_t cfg = { .http_config = &http };

    esp_err_t err = esp_https_ota(&cfg);
    free(url);
    if (err == ESP_OK) {
        ESP_LOGI(TAG, "hotovo, restart");
        vTaskDelay(pdMS_TO_TICKS(500));
        esp_restart();
    }
    ESP_LOGE(TAG, "OTA selhala: %s", esp_err_to_name(err));
    s_running = false;
    vTaskDelete(NULL);
}

esp_err_t ota_start(const char *url)
{
    if (s_running) return ESP_ERR_INVALID_STATE;
    char *copy = strdup(url);
    if (!copy) return ESP_ERR_NO_MEM;
    s_running = true;
    if (xTaskCreate(ota_task, "ota", 8192, copy, 5, NULL) != pdPASS) {
        free(copy);
        s_running = false;
        return ESP_FAIL;
    }
    return ESP_OK;
}
