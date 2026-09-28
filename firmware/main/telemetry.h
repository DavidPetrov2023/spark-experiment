#pragma once

// Kazdych TELEMETRY_INTERVAL_S posle stav na /devices/ a z odpovedi vezme
// prikaz. Umi jen ota_update, ostatni (set_led, sleep, wake) zaloguje.
void telemetry_start(void);
