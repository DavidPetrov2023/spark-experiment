"""B2: cervena LED ve smycce app_main blika (strida uroven), perioda 500 ms."""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "suite"))
from csrc import defines, function, read, resolve, strip_comments  # noqa: E402


def check(ws):
    src = strip_comments(read(Path(ws) / "main/main.c"))
    defs = defines(src)
    app = function(src, "app_main") or ""
    i = app.find("while")
    if i < 0:
        return False, "v app_main chybi smycka"
    loop = app[i:]

    delays = re.findall(r"vTaskDelay\s*\(\s*pdMS_TO_TICKS\s*\(\s*(\w+)\s*\)\s*\)", loop)
    if not delays or any(resolve(d, defs) != 500 for d in delays):
        return False, f"zpozdeni ve smycce neni 500 ms: {delays}"

    # a) promenna, ktera se kazdym pruchodem neguje a urcuje uroven LED_RED
    for m in re.finditer(r"gpio_set_level\s*\(\s*LED_RED\s*,\s*([^;]+)\)\s*;", loop):
        for var in set(re.findall(r"\b[a-zA-Z_]\w*\b", m.group(1))):
            toggles = re.search(r"\b" + var + r"\s*=\s*!\s*" + var + r"\b", loop) or \
                re.search(r"\b" + var + r"\s*\^=\s*(1|true)\b", loop)
            constant = re.search(r"\b" + var + r"\s*=\s*(true|false|0|1)\s*;", loop)
            if toggles and not constant:
                return True, f"smycka neguje '{var}' a podle ni nastavuje LED_RED"

    # b) dve pevne urovne se zpozdenim mezi nimi
    levels = re.findall(r"gpio_set_level\s*\(\s*LED_RED\s*,\s*(\w+)\s*\)", loop)
    if {"0", "1"} <= set(levels) and len(delays) >= 2:
        return True, "smycka strida LED_RED 0/1 se dvema zpozdenimi"

    return False, "smycka LED_RED nestrida"


if __name__ == "__main__":
    ok, detail = check(sys.argv[1])
    print(("OK: " if ok else "FAIL: ") + detail)
    sys.exit(0 if ok else 1)
