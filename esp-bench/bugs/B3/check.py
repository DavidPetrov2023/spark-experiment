"""B3: Uptime v telemetrii je v sekundach (esp_timer_get_time vraci mikrosekundy)."""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "suite"))
from csrc import function, read, strip_comments  # noqa: E402

CAST = r"\(\s*(?:const\s+)?(?:double|float|int|long|unsigned|u?int\d+_t|size_t|long\s+long)\s*\)"


def check(ws):
    src = strip_comments(read(Path(ws) / "main/telemetry.c"))
    payload = function(src, "payload") or ""
    m = re.search(r'cJSON_AddNumberToObject\s*\(\s*\w+\s*,\s*"Uptime"\s*,(.+?)\)\s*;', payload, re.S)
    if not m:
        return False, "v payload() chybi Uptime"
    expr = m.group(1)
    if "esp_timer_get_time()" not in expr:
        return False, f"Uptime se nepocita z esp_timer_get_time(): {expr.strip()}"
    # dosadit 1000 s v mikrosekundach, vyhodit pretypovani a pripony cisel, vysledek ma byt 1000
    e = expr.replace("esp_timer_get_time()", "(T)")
    e = re.sub(CAST, "", e)
    e = re.sub(r"(\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)(?:[uUlLfF]+)\b", r"\1", e)
    if not re.fullmatch(r"[\sT\d\.eE+\-*/()]+", e):
        return False, f"vyraz Uptime neumim vyhodnotit: {expr.strip()}"
    try:
        value = eval(e, {"__builtins__": {}}, {"T": 1_000_000_000})
    except Exception as ex:  # noqa: BLE001
        return False, f"vyraz Uptime nejde vyhodnotit ({ex}): {expr.strip()}"
    if abs(value - 1000) > 1:
        return False, f"po 1000 s by Uptime hlasil {value:g}"
    return True, "Uptime v sekundach"


if __name__ == "__main__":
    ok, detail = check(sys.argv[1])
    print(("OK: " if ok else "FAIL: ") + detail)
    sys.exit(0 if ok else 1)
