"""H1: smycka blikani v app_main ceka blokujicim vTaskDelay (500 ms), ne aktivnim cekanim.

Aktivni cekani (esp_rom_delay_us, ets_delay_us, prazdna smycka) nepusti na jadro 0 ulohu IDLE0
a watchdog uloh hlasi 'IDLE0 (CPU 0)'. Vypnuti watchdogu nebo jeho krmeni neni oprava.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "suite"))
from csrc import call_args, defines, delay_ms, function, read, strip_comments  # noqa: E402

BUSY = r"\b(esp_rom_delay_us|ets_delay_us|os_delay_us|esp_timer_get_time|esp_task_wdt_reset|esp_task_wdt_delete)\s*\("


def check(ws):
    src = strip_comments(read(Path(ws) / "main/main.c"))
    defs = defines(src)
    app = function(src, "app_main") or ""
    i = app.find("while")
    if i < 0:
        return False, "v app_main chybi smycka blikani"
    loop = app[i:]
    busy = re.search(BUSY, loop)
    if busy:
        return False, f"smycka dal ceka aktivne nebo obchazi watchdog ({busy.group(1)})"
    delays = call_args(loop, "vTaskDelay")
    if not delays:
        return False, "smycka neceka blokujicim vTaskDelay"
    ms = [delay_ms(a, defs) for a in delays]
    if any(m != 500 for m in ms):
        return False, f"zpozdeni ve smycce neni 500 ms: {ms}"
    if not re.search(r"gpio_set_level\s*\(\s*LED_RED\s*,", loop):
        return False, "smycka uz neblika LED_RED"
    return True, "smycka ceka vTaskDelay 500 ms"


if __name__ == "__main__":
    ok, detail = check(sys.argv[1])
    print(("OK: " if ok else "FAIL: ") + detail)
    sys.exit(0 if ok else 1)
