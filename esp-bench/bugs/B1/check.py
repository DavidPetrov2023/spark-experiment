"""B1: blika cervena LED (pin 27), ne modra (12). Rozlozeni pinu podle README."""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "suite"))
from csrc import defines, function, read, resolve, strip_comments  # noqa: E402

EXPECTED = {"LED_RED": 27, "LED_GREEN": 14, "LED_BLUE": 12, "LED_MAIN": 5}


def check(ws):
    src = strip_comments(read(Path(ws) / "main/main.c"))
    defs = defines(src)
    leds = {n: resolve(n, defs) for n in EXPECTED}
    if leds != EXPECTED:
        return False, f"piny LED nesedi s README: {leds}"
    app = function(src, "app_main") or ""
    loop = app[app.find("while"):] if "while" in app else ""
    blinked = {resolve(m.group(1), defs) for m in re.finditer(r"gpio_set_level\s*\(\s*(\w+)\s*,", loop)}
    if blinked != {27}:
        return False, f"smycka nastavuje piny {sorted(p for p in blinked if p is not None)}, ma jen 27 (cervena)"
    init = function(src, "pins_init") or ""
    outputs = {resolve(m.group(1), defs) for m in re.finditer(r"1ULL\s*<<\s*(\w+)", init)}
    if 27 not in outputs:
        return False, "pin 27 neni v pins_init nastaveny jako vystup"
    return True, "blika cervena (27)"


if __name__ == "__main__":
    ok, detail = check(sys.argv[1])
    print(("OK: " if ok else "FAIL: ") + detail)
    sys.exit(0 if ok else 1)
