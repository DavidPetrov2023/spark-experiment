"""H3: LED_RED se prepina kazdych 500 ms (skutecna delka vTaskDelay po prevodu na tiky FreeRTOS).

Chyba prevadi ms na tiky dvakrat (BLINK_MS = 500 / portTICK_PERIOD_MS a pak pdMS_TO_TICKS).
Opravit jde vic zpusoby, kontrola proto pocita vyslednou delku, ne konkretni zapis.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "suite"))
from csrc import call_args, defines, delay_ms, function, read, strip_comments  # noqa: E402


def check(ws):
    src = strip_comments(read(Path(ws) / "main/main.c"))
    defs = defines(src)
    app = function(src, "app_main") or ""
    i = app.find("while")
    if i < 0:
        return False, "v app_main chybi smycka blikani"
    loop = app[i:]
    delays = call_args(loop, "vTaskDelay")
    if not delays:
        return False, "smycka neceka vTaskDelay"
    ms = [delay_ms(a, defs) for a in delays]
    if any(m is None for m in ms):
        return False, f"delku zpozdeni neumim spocitat: {delays}"
    if any(m != 500 for m in ms):
        return False, f"LED se prepina po {ms} ms, ma po 500 ms"
    if not re.search(r"gpio_set_level\s*\(\s*LED_RED\s*,", loop):
        return False, "smycka uz neblika LED_RED"
    return True, "LED_RED se prepina po 500 ms"


if __name__ == "__main__":
    ok, detail = check(sys.argv[1])
    print(("OK: " if ok else "FAIL: ") + detail)
    sys.exit(0 if ok else 1)
