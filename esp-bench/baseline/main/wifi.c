#include "wifi.h"

#include <string.h>
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_wifi.h"
#include "nvs.h"

#include "device_config.h"

static const char *TAG = "WIFI";
static volatile bool s_connected = false;

static void on_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
    } else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        s_connected = false;
        wifi_event_sta_disconnected_t *d = (wifi_event_sta_disconnected_t *)data;
        ESP_LOGW(TAG, "odpojeno (reason %d), zkousim znovu", d->reason);
        // Bez limitu pokusu, na rozdil od robota (ten po peti skonci ve
        // FAILED). Tahle deska se aktualizuje jen pres WiFi, takze vzdat to
        // znamena ztratit ji az do restartu.
        esp_wifi_connect();
    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *e = (ip_event_got_ip_t *)data;
        ESP_LOGI(TAG, "pripojeno, IP " IPSTR, IP2STR(&e->ip_info.ip));
        s_connected = true;
    }
}

// Stejny namespace a klice jako wifi_manager.c v robotovi, takze po OTA
// z robota se deska pripoji bez jakehokoli nastavovani.
static bool load_nvs(char *ssid, size_t ssid_len, char *pass, size_t pass_len)
{
    nvs_handle_t h;
    if (nvs_open("wifi_creds", NVS_READONLY, &h) != ESP_OK) return false;
    esp_err_t a = nvs_get_str(h, "ssid", ssid, &ssid_len);
    esp_err_t b = nvs_get_str(h, "password", pass, &pass_len);
    nvs_close(h);
    return a == ESP_OK && b == ESP_OK && ssid[0] != '\0';
}

esp_err_t wifi_start(void)
{
    char ssid[33] = {0}, pass[65] = {0};
    if (load_nvs(ssid, sizeof(ssid), pass, sizeof(pass))) {
        ESP_LOGI(TAG, "WiFi z NVS: %s", ssid);
    } else if (WIFI_FALLBACK_SSID[0] != '\0') {
        strncpy(ssid, WIFI_FALLBACK_SSID, sizeof(ssid) - 1);
        strncpy(pass, WIFI_FALLBACK_PASS, sizeof(pass) - 1);
        ESP_LOGI(TAG, "WiFi z device_config.h: %s", ssid);
    } else {
        ESP_LOGE(TAG, "zadne udaje k WiFi (NVS prazdne, fallback nevyplneny)");
        return ESP_ERR_NOT_FOUND;
    }

    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(WIFI_EVENT, ESP_EVENT_ANY_ID, on_event, NULL, NULL));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(IP_EVENT, IP_EVENT_STA_GOT_IP, on_event, NULL, NULL));

    wifi_config_t wc = {0};
    memcpy(wc.sta.ssid, ssid, strlen(ssid));
    memcpy(wc.sta.password, pass, strlen(pass));
    wc.sta.threshold.authmode = pass[0] ? WIFI_AUTH_WPA_WPA2_PSK : WIFI_AUTH_OPEN;
    wc.sta.scan_method = WIFI_ALL_CHANNEL_SCAN;
    wc.sta.sort_method = WIFI_CONNECT_AP_BY_SIGNAL;

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wc));
    ESP_ERROR_CHECK(esp_wifi_start());
    return ESP_OK;
}

bool wifi_connected(void)
{
    return s_connected;
}
