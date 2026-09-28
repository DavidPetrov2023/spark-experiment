# Řešení úloh

Nejdřív zkuste úlohu sami, pak porovnejte.

## B1: Bliká modrá místo červené

`LED_RED` je definovaná na pinu 12 (modrá LED) místo 27. Oprava: `#define LED_RED 27`.

Chybu vnesla tahle změna:

```diff
diff --git a/main/main.c b/main/main.c
index d8429dc..c8cd1b9 100644
--- a/main/main.c
+++ b/main/main.c
@@ -20,7 +20,7 @@
 static const char *TAG = "ESPTEST";
 
 // RGB dioda robota, aktivni v LOW (0 = sviti). Viz Zobo main/led.c.
-#define LED_RED   27
+#define LED_RED   12
 #define LED_GREEN 14
 #define LED_BLUE  12
 #define LED_MAIN  5
```

## B2: Červená trvale svítí, nebliká

Smyčka blikání nepřepíná proměnnou `on`, takže LED pořád svítí. Oprava: v každém průchodu `on = !on;`.

Chybu vnesla tahle změna:

```diff
diff --git a/main/main.c b/main/main.c
index d8429dc..0f0f2b5 100644
--- a/main/main.c
+++ b/main/main.c
@@ -75,7 +75,7 @@ void app_main(void)
 
     bool on = false;
     while (1) {
-        on = !on;
+        on = true;
         gpio_set_level(LED_RED, on ? 0 : 1);
         vTaskDelay(pdMS_TO_TICKS(BLINK_MS));
     }
```

## B3: Uptime 1000× větší

Uptime se dělí 1000 místo 1 000 000: `esp_timer_get_time()` vrací mikrosekundy. Oprava: dělit 1 000 000.

Chybu vnesla tahle změna:

```diff
diff --git a/main/telemetry.c b/main/telemetry.c
index 98f4121..350255d 100644
--- a/main/telemetry.c
+++ b/main/telemetry.c
@@ -49,7 +49,7 @@ static char *payload(void)
     cJSON_AddStringToObject(info, "ID", s_id);
     cJSON_AddStringToObject(info, "Firmware", FIRMWARE_VERSION);
     cJSON *live = cJSON_AddObjectToObject(root, "LiveStatus");
-    cJSON_AddNumberToObject(live, "Uptime", (double)(esp_timer_get_time() / 1000000));
+    cJSON_AddNumberToObject(live, "Uptime", (double)(esp_timer_get_time() / 1000));
     cJSON_AddNumberToObject(live, "ErrorCode", 0);
     cJSON_AddStringToObject(live, "EventState", "blink");
     // ACTIVE natvrdo: push_ota na serveru odmitne desku, o ktere si mysli,
```

## B4: Únik paměti v telemetrii

V `payload()` chybí `cJSON_Delete(root)`, strom JSONu se každých 5 s neuvolní (únik paměti). Oprava: po `cJSON_PrintUnformatted` uvolnit strom.

Chybu vnesla tahle změna:

```diff
diff --git a/main/telemetry.c b/main/telemetry.c
index 98f4121..ae68d55 100644
--- a/main/telemetry.c
+++ b/main/telemetry.c
@@ -58,7 +58,6 @@ static char *payload(void)
     cJSON *product = cJSON_AddObjectToObject(root, "ProductInfo");
     cJSON_AddStringToObject(product, "Název zařízení", "ESP Test");
     char *out = cJSON_PrintUnformatted(root);
-    cJSON_Delete(root);
     return out;
 }
```

## H1: Watchdog IDLE0 (aktivní čekání)

Smyčka blikání čeká aktivně (`esp_rom_delay_us`), takže na jádře 0 nepustí úlohu IDLE a hlásí se watchdog. Oprava: `vTaskDelay(pdMS_TO_TICKS(BLINK_MS))`. Vypnout nebo krmit watchdog není oprava.

Chybu vnesla tahle změna:

```diff
diff --git a/main/main.c b/main/main.c
index d8429dc..1187715 100644
--- a/main/main.c
+++ b/main/main.c
@@ -10,6 +10,7 @@
 #include "freertos/task.h"
 #include "driver/gpio.h"
 #include "esp_log.h"
+#include "esp_rom_sys.h"
 #include "nvs_flash.h"
 
 #include "ota.h"
@@ -77,6 +78,6 @@ void app_main(void)
     while (1) {
         on = !on;
         gpio_set_level(LED_RED, on ? 0 : 1);
-        vTaskDelay(pdMS_TO_TICKS(BLINK_MS));
+        esp_rom_delay_us(BLINK_MS * 1000);
     }
 }
```

## H2: Uptime přeteče po 35 min

Uptime se přetypuje na `int32_t` ještě v mikrosekundách, což přeteče po 2^31 µs = 35,8 min. Oprava: nejdřív dělit v 64 bitech, zúžit až sekundy.

Chybu vnesla tahle změna:

```diff
diff --git a/main/telemetry.c b/main/telemetry.c
index 98f4121..484eae0 100644
--- a/main/telemetry.c
+++ b/main/telemetry.c
@@ -49,7 +49,7 @@ static char *payload(void)
     cJSON_AddStringToObject(info, "ID", s_id);
     cJSON_AddStringToObject(info, "Firmware", FIRMWARE_VERSION);
     cJSON *live = cJSON_AddObjectToObject(root, "LiveStatus");
-    cJSON_AddNumberToObject(live, "Uptime", (double)(esp_timer_get_time() / 1000000));
+    cJSON_AddNumberToObject(live, "Uptime", (double)((int32_t)esp_timer_get_time() / 1000000));
     cJSON_AddNumberToObject(live, "ErrorCode", 0);
     cJSON_AddStringToObject(live, "EventState", "blink");
     // ACTIVE natvrdo: push_ota na serveru odmitne desku, o ktere si mysli,
```

## H3: Blikání 10× rychleji (tiky)

`BLINK_MS` je převedené na tiky (`500 / portTICK_PERIOD_MS`) a smyčka ho převádí znovu přes `pdMS_TO_TICKS`, takže čeká 10× kratší dobu. Oprava: `#define BLINK_MS 500`.

Chybu vnesla tahle změna:

```diff
diff --git a/main/main.c b/main/main.c
index d8429dc..b15397c 100644
--- a/main/main.c
+++ b/main/main.c
@@ -32,7 +32,7 @@ static const char *TAG = "ESPTEST";
 #define MOTOR_RIGHT_PWM 16
 #define MOTOR_RIGHT_DIR 17
 
-#define BLINK_MS 500
+#define BLINK_MS (500 / portTICK_PERIOD_MS)
 
 static void pins_init(void)
 {
```

## X1: Dvě chyby: LED nezhasne + únik paměti

Dvě chyby. (1) Deklarace `bool on = false;` se přesunula dovnitř smyčky, takže se každým průchodem nastaví znovu a LED nezhasne. (2) Ladicí `char *dbg = cJSON_Print(root)` se nikdy neuvolní (únik). Oprava: deklaraci vrátit před smyčku (nebo `static`) a ladicí výpis smazat, případně `cJSON_free(dbg)`.

Chybu vnesla tahle změna:

```diff
diff --git a/main/main.c b/main/main.c
index d8429dc..9424640 100644
--- a/main/main.c
+++ b/main/main.c
@@ -73,8 +73,8 @@ void app_main(void)
     wifi_start();
     telemetry_start();
 
-    bool on = false;
     while (1) {
+        bool on = false;
         on = !on;
         gpio_set_level(LED_RED, on ? 0 : 1);
         vTaskDelay(pdMS_TO_TICKS(BLINK_MS));
diff --git a/main/telemetry.c b/main/telemetry.c
index 98f4121..4ae30f3 100644
--- a/main/telemetry.c
+++ b/main/telemetry.c
@@ -58,6 +58,8 @@ static char *payload(void)
     cJSON *product = cJSON_AddObjectToObject(root, "ProductInfo");
     cJSON_AddStringToObject(product, "Název zařízení", "ESP Test");
     char *out = cJSON_PrintUnformatted(root);
+    char *dbg = cJSON_Print(root);
+    ESP_LOGD(TAG, "payload: %s", dbg);
     cJSON_Delete(root);
     return out;
 }
```

Jedna ze správných oprav:

```diff
diff --git a/main/main.c b/main/main.c
index 9424640..d8429dc 100644
--- a/main/main.c
+++ b/main/main.c
@@ -73,8 +73,8 @@ void app_main(void)
     wifi_start();
     telemetry_start();
 
+    bool on = false;
     while (1) {
-        bool on = false;
         on = !on;
         gpio_set_level(LED_RED, on ? 0 : 1);
         vTaskDelay(pdMS_TO_TICKS(BLINK_MS));
diff --git a/main/telemetry.c b/main/telemetry.c
index 4ae30f3..98f4121 100644
--- a/main/telemetry.c
+++ b/main/telemetry.c
@@ -58,8 +58,6 @@ static char *payload(void)
     cJSON *product = cJSON_AddObjectToObject(root, "ProductInfo");
     cJSON_AddStringToObject(product, "Název zařízení", "ESP Test");
     char *out = cJSON_PrintUnformatted(root);
-    char *dbg = cJSON_Print(root);
-    ESP_LOGD(TAG, "payload: %s", dbg);
     cJSON_Delete(root);
     return out;
 }
```

## X2: Souběh: poškozený EventState

Smyčka blikání přepisuje sdílený řetězec `g_event_state` (`snprintf`) a telemetrie ho ve stejnou chvíli čte z jiné úlohy (ESP32 má dvě jádra). Výsledkem je občas `blink_onf`. Oprava: zámek (kritická sekce, mutex) kolem zápisu i čtení, nebo atomická hodnota (bool, případně ukazatel na konstantní řetězec).

Chybu vnesla tahle změna:

```diff
diff --git a/main/main.c b/main/main.c
index d8429dc..243bcf2 100644
--- a/main/main.c
+++ b/main/main.c
@@ -6,6 +6,7 @@
  */
 
 #include <stdbool.h>
+#include <stdio.h>
 #include "freertos/FreeRTOS.h"
 #include "freertos/task.h"
 #include "driver/gpio.h"
@@ -34,6 +35,9 @@ static const char *TAG = "ESPTEST";
 
 #define BLINK_MS 500
 
+// Stav pro telemetrii (EventState): "blink_on", kdyz cervena prave sviti, jinak "blink_off".
+char g_event_state[16] = "blink_off";
+
 static void pins_init(void)
 {
     gpio_config_t io = {
@@ -77,6 +81,7 @@ void app_main(void)
     while (1) {
         on = !on;
         gpio_set_level(LED_RED, on ? 0 : 1);
+        snprintf(g_event_state, sizeof(g_event_state), "blink_%s", on ? "on" : "off");
         vTaskDelay(pdMS_TO_TICKS(BLINK_MS));
     }
 }
diff --git a/main/telemetry.c b/main/telemetry.c
index 98f4121..8eba0c7 100644
--- a/main/telemetry.c
+++ b/main/telemetry.c
@@ -24,6 +24,9 @@ static const char *TAG = "TELEMETRY";
 
 static char s_id[24];
 
+// Stav cervene LED z main.c ("blink_on" / "blink_off").
+extern char g_event_state[16];
+
 typedef struct {
     char buf[1024];
     size_t len;
@@ -51,7 +54,7 @@ static char *payload(void)
     cJSON *live = cJSON_AddObjectToObject(root, "LiveStatus");
     cJSON_AddNumberToObject(live, "Uptime", (double)(esp_timer_get_time() / 1000000));
     cJSON_AddNumberToObject(live, "ErrorCode", 0);
-    cJSON_AddStringToObject(live, "EventState", "blink");
+    cJSON_AddStringToObject(live, "EventState", g_event_state);
     // ACTIVE natvrdo: push_ota na serveru odmitne desku, o ktere si mysli,
     // ze spi, a spanek tenhle firmware neumi.
     cJSON_AddStringToObject(live, "PowerMode", "ACTIVE");
```

Jedna ze správných oprav:

```diff
diff --git a/main/main.c b/main/main.c
index 243bcf2..b38a637 100644
--- a/main/main.c
+++ b/main/main.c
@@ -37,6 +37,7 @@ static const char *TAG = "ESPTEST";
 
 // Stav pro telemetrii (EventState): "blink_on", kdyz cervena prave sviti, jinak "blink_off".
 char g_event_state[16] = "blink_off";
+portMUX_TYPE g_event_mux = portMUX_INITIALIZER_UNLOCKED;
 
 static void pins_init(void)
 {
@@ -81,7 +82,9 @@ void app_main(void)
     while (1) {
         on = !on;
         gpio_set_level(LED_RED, on ? 0 : 1);
+        portENTER_CRITICAL(&g_event_mux);
         snprintf(g_event_state, sizeof(g_event_state), "blink_%s", on ? "on" : "off");
+        portEXIT_CRITICAL(&g_event_mux);
         vTaskDelay(pdMS_TO_TICKS(BLINK_MS));
     }
 }
diff --git a/main/telemetry.c b/main/telemetry.c
index 8eba0c7..b01105e 100644
--- a/main/telemetry.c
+++ b/main/telemetry.c
@@ -26,6 +26,7 @@ static char s_id[24];
 
 // Stav cervene LED z main.c ("blink_on" / "blink_off").
 extern char g_event_state[16];
+extern portMUX_TYPE g_event_mux;
 
 typedef struct {
     char buf[1024];
@@ -54,7 +55,11 @@ static char *payload(void)
     cJSON *live = cJSON_AddObjectToObject(root, "LiveStatus");
     cJSON_AddNumberToObject(live, "Uptime", (double)(esp_timer_get_time() / 1000000));
     cJSON_AddNumberToObject(live, "ErrorCode", 0);
-    cJSON_AddStringToObject(live, "EventState", g_event_state);
+    char state[16];
+    portENTER_CRITICAL(&g_event_mux);
+    strlcpy(state, g_event_state, sizeof(state));
+    portEXIT_CRITICAL(&g_event_mux);
+    cJSON_AddStringToObject(live, "EventState", state);
     // ACTIVE natvrdo: push_ota na serveru odmitne desku, o ktere si mysli,
     // ze spi, a spanek tenhle firmware neumi.
     cJSON_AddStringToObject(live, "PowerMode", "ACTIVE");
```

## X3: Rollback po OTA (zpoždění startu)

Čekání na ustálení napájení má být 1,25 s, ale `vTaskDelay(POWER_SETTLE_MS * portTICK_PERIOD_MS)` ms na tiky násobí místo dělení: 12 500 tiků = 125 s. První telemetrie, která potvrzuje nový firmware, přijde až po limitu rollbacku (120 s). Oprava je v `main.c`: `pdMS_TO_TICKS(POWER_SETTLE_MS)`. Měnit OTA (limit, potvrzení) je chyba, kterou lokální modely v testu dělaly.

Chybu vnesla tahle změna:

```diff
diff --git a/main/main.c b/main/main.c
index d8429dc..aaf04af 100644
--- a/main/main.c
+++ b/main/main.c
@@ -34,6 +34,10 @@ static const char *TAG = "ESPTEST";
 
 #define BLINK_MS 500
 
+// Po zapnuti chvili pockat, nez se pusti WiFi: pri startu bere proudovou
+// spicku a na slabsim zdroji deska brownoutovala. Staci ~1,25 s.
+#define POWER_SETTLE_MS 1250
+
 static void pins_init(void)
 {
     gpio_config_t io = {
@@ -70,6 +74,7 @@ void app_main(void)
     ESP_LOGI(TAG, "ESPTest v%s", FIRMWARE_VERSION);
 
     ota_boot_check();
+    vTaskDelay(POWER_SETTLE_MS * portTICK_PERIOD_MS);
     wifi_start();
     telemetry_start();
```

Jedna ze správných oprav:

```diff
diff --git a/main/main.c b/main/main.c
index aaf04af..1b506cc 100644
--- a/main/main.c
+++ b/main/main.c
@@ -74,7 +74,7 @@ void app_main(void)
     ESP_LOGI(TAG, "ESPTest v%s", FIRMWARE_VERSION);
 
     ota_boot_check();
-    vTaskDelay(POWER_SETTLE_MS * portTICK_PERIOD_MS);
+    vTaskDelay(pdMS_TO_TICKS(POWER_SETTLE_MS));
     wifi_start();
     telemetry_start();
```

## X4: Nová pole RSSI a MinFreeHeap

Nová funkce: do `LiveStatus` přidat `RSSI` jen při úspěšném `esp_wifi_sta_get_ap_info` (jinak pole neposílat) a `MinFreeHeap` z `esp_get_minimum_free_heap_size()` (ne aktuální volný heap).

Jedna ze správných oprav:

```diff
diff --git a/main/telemetry.c b/main/telemetry.c
index 98f4121..534740c 100644
--- a/main/telemetry.c
+++ b/main/telemetry.c
@@ -10,6 +10,8 @@
 #include "esp_log.h"
 #include "esp_mac.h"
 #include "esp_timer.h"
+#include "esp_system.h"
+#include "esp_wifi.h"
 
 #include "device_config.h"
 #include "ota.h"
@@ -55,6 +57,11 @@ static char *payload(void)
     // ACTIVE natvrdo: push_ota na serveru odmitne desku, o ktere si mysli,
     // ze spi, a spanek tenhle firmware neumi.
     cJSON_AddStringToObject(live, "PowerMode", "ACTIVE");
+    wifi_ap_record_t ap;
+    if (esp_wifi_sta_get_ap_info(&ap) == ESP_OK) {
+        cJSON_AddNumberToObject(live, "RSSI", ap.rssi);
+    }
+    cJSON_AddNumberToObject(live, "MinFreeHeap", esp_get_minimum_free_heap_size());
     cJSON *product = cJSON_AddObjectToObject(root, "ProductInfo");
     cJSON_AddStringToObject(product, "Název zařízení", "ESP Test");
     char *out = cJSON_PrintUnformatted(root);
```
