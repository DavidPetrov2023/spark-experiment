"""H2: Uptime z esp_timer_get_time() (int64 v mikrosekundach) se nesmi pred delenim zuzit na 32 bitu.

(int32_t) na mikrosekundach pretece po 2^31 us = 35,8 min. Pretypovani az vysledku v sekundach
(napr. (uint32_t)(esp_timer_get_time() / 1000000)) je v poradku.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "suite"))
from csrc import function, read, strip_comments  # noqa: E402

# zuzeni primo volani: (int32_t)esp_timer_get_time() nebo (int32_t)(esp_timer_get_time()),
# ale ne (uint32_t)(esp_timer_get_time() / 1000000), kde se zuzuji az sekundy
NARROW = (r"\(\s*(?:u?int(?:8|16|32)_t|int|long|short|unsigned(?:\s+(?:int|long|short))?|signed(?:\s+int)?"
          r"|uint|size_t|float)\s*\)\s*(?:esp_timer_get_time\s*\(\s*\)|\(\s*esp_timer_get_time\s*\(\s*\)\s*\))")
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
    narrow = re.search(NARROW, expr)
    if narrow:
        return False, f"mikrosekundy se pred delenim zuzuji: {narrow.group(0)}"
    e = re.sub(CAST, "", expr.replace("esp_timer_get_time()", "(T)"))
    e = re.sub(r"(\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)(?:[uUlLfF]+)\b", r"\1", e)
    if not re.fullmatch(r"[\sT\d\.eE+\-*/()]+", e):
        return False, f"vyraz Uptime neumim vyhodnotit: {expr.strip()}"
    for t_us, want in ((1_000_000_000, 1000), (10_000_000_000, 10000)):  # 1000 s a 10000 s (> 35,8 min)
        try:
            value = eval(e, {"__builtins__": {}}, {"T": t_us})
        except Exception as ex:  # noqa: BLE001
            return False, f"vyraz Uptime nejde vyhodnotit ({ex})"
        if abs(value - want) > 1:
            return False, f"po {want} s by Uptime hlasil {value:g}"
    return True, "Uptime v sekundach bez preteceni"


if __name__ == "__main__":
    ok, detail = check(sys.argv[1])
    print(("OK: " if ok else "FAIL: ") + detail)
    sys.exit(0 if ok else 1)
