/**
 * ESPTest - minimalni firmware na desce Zobo robota.
 *
 * Bliká červenou a umí přijmout další OTA z /devices/. Nic víc: bez BLE,
 * motorů, MQTT i spánku. Vychází z C:\Cloud\AI\Zobo\zobo_esp32.
 */

#include <stdbool.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/gpio.h"
#include "esp_log.h"
#include "nvs_flash.h"

#include "ota.h"
#include "telemetry.h"
#include "version.h"
#include "wifi.h"

static const char *TAG = "ESPTEST";

// RGB dioda robota, aktivni v LOW (0 = sviti). Viz Zobo main/led.c.
#define LED_RED   27
#define LED_GREEN 14
#define LED_BLUE  12
#define LED_MAIN  5

// Motory robota. Po resetu jsou piny ve vysoke impedanci a driver motoru by
// na plovoucim vstupu mohl rozjet pas, proto se drzi v nule (PWM 0 = stoji).
#define MOTOR_LEFT_PWM  25
#define MOTOR_LEFT_DIR  26
#define MOTOR_RIGHT_PWM 16
#define MOTOR_RIGHT_DIR 17

#define BLINK_MS 500

// Po zapnuti chvili pockat, nez se pusti WiFi: pri startu bere proudovou
// spicku a na slabsim zdroji deska brownoutovala. Staci ~1,25 s.
#define POWER_SETTLE_MS 1250

static void pins_init(void)
{
    gpio_config_t io = {
        .mode = GPIO_MODE_OUTPUT,
        .pin_bit_mask = (1ULL << LED_RED) | (1ULL << LED_GREEN) | (1ULL << LED_BLUE) | (1ULL << LED_MAIN) |
                        (1ULL << MOTOR_LEFT_PWM) | (1ULL << MOTOR_LEFT_DIR) |
                        (1ULL << MOTOR_RIGHT_PWM) | (1ULL << MOTOR_RIGHT_DIR),
    };
    gpio_config(&io);

    gpio_set_level(MOTOR_LEFT_PWM, 0);
    gpio_set_level(MOTOR_LEFT_DIR, 0);
    gpio_set_level(MOTOR_RIGHT_PWM, 0);
    gpio_set_level(MOTOR_RIGHT_DIR, 0);

    gpio_set_level(LED_RED, 1);
    gpio_set_level(LED_GREEN, 1);
    gpio_set_level(LED_BLUE, 1);
    gpio_set_level(LED_MAIN, 0);
}

void app_main(void)
{
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        // Smazani NVS by vzalo i WiFi od robota. Stane se jen po zmene
        // formatu NVS, pak pomuze WIFI_FALLBACK_* v device_config.h.
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);

    pins_init();
    ESP_LOGI(TAG, "ESPTest v%s", FIRMWARE_VERSION);

    ota_boot_check();
    vTaskDelay(POWER_SETTLE_MS * portTICK_PERIOD_MS);
    wifi_start();
    telemetry_start();

    bool on = false;
    while (1) {
        on = !on;
        gpio_set_level(LED_RED, on ? 0 : 1);
        vTaskDelay(pdMS_TO_TICKS(BLINK_MS));
    }
}
