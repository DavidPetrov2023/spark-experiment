#include "telemetry.h"

#include <stdio.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "cJSON.h"
#include "esp_crt_bundle.h"
#include "esp_http_client.h"
#include "esp_log.h"
#include "esp_mac.h"
#include "esp_timer.h"

#include "device_config.h"
#include "ota.h"
#include "version.h"
#include "wifi.h"

static const char *TAG = "TELEMETRY";

// Musi sedet s active_interval_s produktu 'esptest' v robot/products.php,
// jinak dashboard hlasi desku jako neaktivni, nebo naopak prilis dlouho ne.
#define TELEMETRY_INTERVAL_S 5

static char s_id[24];

// Stav cervene LED z main.c ("blink_on" / "blink_off").
extern char g_event_state[16];

typedef struct {
    char buf[1024];
    size_t len;
} resp_t;

static esp_err_t on_http(esp_http_client_event_t *evt)
{
    resp_t *r = (resp_t *)evt->user_data;
    if (evt->event_id == HTTP_EVENT_ON_DATA && r && evt->data_len > 0) {
        size_t volno = sizeof(r->buf) - 1 - r->len;
        size_t n = (size_t)evt->data_len < volno ? (size_t)evt->data_len : volno;
        memcpy(r->buf + r->len, evt->data, n);
        r->len += n;
        r->buf[r->len] = '\0';
    }
    return ESP_OK;
}

static char *payload(void)
{
    cJSON *root = cJSON_CreateObject();
    cJSON *info = cJSON_AddObjectToObject(root, "DeviceInfo");
    cJSON_AddStringToObject(info, "ID", s_id);
    cJSON_AddStringToObject(info, "Firmware", FIRMWARE_VERSION);
    cJSON *live = cJSON_AddObjectToObject(root, "LiveStatus");
    cJSON_AddNumberToObject(live, "Uptime", (double)(esp_timer_get_time() / 1000000));
    cJSON_AddNumberToObject(live, "ErrorCode", 0);
    cJSON_AddStringToObject(live, "EventState", g_event_state);
    // ACTIVE natvrdo: push_ota na serveru odmitne desku, o ktere si mysli,
    // ze spi, a spanek tenhle firmware neumi.
    cJSON_AddStringToObject(live, "PowerMode", "ACTIVE");
    cJSON *product = cJSON_AddObjectToObject(root, "ProductInfo");
    cJSON_AddStringToObject(product, "Název zařízení", "ESP Test");
    char *out = cJSON_PrintUnformatted(root);
    cJSON_Delete(root);
    return out;
}

static void handle_command(const char *body)
{
    cJSON *root = cJSON_Parse(body);
    if (!root) return;
    cJSON *cmd = cJSON_GetObjectItem(root, "command");
    const char *action = cmd ? cJSON_GetStringValue(cJSON_GetObjectItem(cmd, "action")) : NULL;
    if (action && strcmp(action, "ota_update") == 0) {
        const char *url = cJSON_GetStringValue(cJSON_GetObjectItem(cmd, "url"));
        const char *ver = cJSON_GetStringValue(cJSON_GetObjectItem(cmd, "version"));
        ESP_LOGI(TAG, "prikaz OTA na verzi %s", ver ? ver : "?");
        if (url) {
            esp_err_t err = ota_start(url);
            if (err != ESP_OK) ESP_LOGE(TAG, "OTA se nerozbehla: %s", esp_err_to_name(err));
        }
    } else if (action) {
        ESP_LOGW(TAG, "prikaz %s tenhle firmware neumi, ignoruji", action);
    }
    cJSON_Delete(root);
}

static void post(void)
{
    char *body = payload();
    if (!body) return;
    resp_t resp = {0};
    esp_http_client_config_t cfg = {
        .url = TELEMETRY_URL,
        .method = HTTP_METHOD_POST,
        .timeout_ms = 10000,
        .crt_bundle_attach = esp_crt_bundle_attach,
        .event_handler = on_http,
        .user_data = &resp,
    };
    esp_http_client_handle_t c = esp_http_client_init(&cfg);
    if (c) {
        esp_http_client_set_header(c, "Content-Type", "application/json");
        esp_http_client_set_post_field(c, body, strlen(body));
        esp_err_t err = esp_http_client_perform(c);
        int status = esp_http_client_get_status_code(c);
        if (err == ESP_OK && status >= 200 && status < 300) {
            ESP_LOGI(TAG, "POST ok (HTTP %d)", status);
            // Firmware se dostal na server, takze umi prijmout i dalsi OTA.
            ota_confirm();
            handle_command(resp.buf);
        } else {
            ESP_LOGW(TAG, "POST selhal: %s, HTTP %d", esp_err_to_name(err), status);
        }
        esp_http_client_cleanup(c);
    }
    cJSON_free(body);
}

static void telemetry_task(void *arg)
{
    while (1) {
        if (wifi_connected()) post();
        vTaskDelay(pdMS_TO_TICKS(TELEMETRY_INTERVAL_S * 1000));
    }
}

void telemetry_start(void)
{
    uint8_t mac[6];
    esp_read_mac(mac, ESP_MAC_WIFI_STA);
    // Posledni tri bajty MAC jako u robota (Zobo-19CA30 -> ESPTest-19CA30),
    // at je v dashboardu videt, ze je to tataz deska.
    snprintf(s_id, sizeof(s_id), "ESPTest-%02X%02X%02X", mac[3], mac[4], mac[5]);
    ESP_LOGI(TAG, "%s, firmware %s", s_id, FIRMWARE_VERSION);
    xTaskCreate(telemetry_task, "telemetry", 8192, NULL, 3, NULL);
}
