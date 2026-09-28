"""X3: mezi startem app_main a telemetry_start() se ceka nejvys 10 s.

Chyba: cekani na ustaleni napajeni ma byt 1,25 s, ale ms se na tiky nasobi misto deli
(POWER_SETTLE_MS * portTICK_PERIOD_MS = 12 500 tiku = 125 s). Prvni telemetrie, ktera potvrzuje
firmware po OTA, tak prijde az po limitu 120 s v ota.c a nastane rollback. Oprava je v main.c
(spravny prevod, nebo cekani pryc). Prodlouzit limit v ota.c je zasah do OTA a chyti ho guard.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "suite"))
from csrc import defines, delay_ms, eval_int, function, match_paren, read, strip_comments  # noqa: E402

LIMIT_MS = 10_000
BUSY = {"esp_rom_delay_us": 0.001, "ets_delay_us": 0.001, "usleep": 0.001, "sleep": 1000.0}


def waits(text, defs):
    """Soucet cekani v useku kodu v ms (vTaskDelay, aktivni cekani, smycky for s pevnou mezi)."""
    total = 0
    for m in list(re.finditer(r"\bfor\s*\(", text))[::-1]:
        head_end = match_paren(text, m.end() - 1)
        head = text[m.end():head_end - 1].split(";")
        j = head_end
        while j < len(text) and text[j].isspace():
            j += 1
        end = match_paren(text, j) if text[j] == "{" else text.find(";", j) + 1
        body_ms = waits(text[j:end], defs)
        if body_ms is None:
            return None
        if body_ms:
            start = re.search(r"=\s*([^,;]+)$", head[0].strip()) if len(head) == 3 else None
            bound = re.search(r"(<=|<)\s*(.+)$", head[1].strip()) if len(head) == 3 else None
            lo = eval_int(start.group(1), defs) if start else None
            hi = eval_int(bound.group(2), defs) if bound else None
            if lo is None or hi is None:
                return None
            total += body_ms * max(0, hi - lo + (1 if bound.group(1) == "<=" else 0))
        text = text[:m.start()] + text[end:]
    if re.search(r"\b(while|do)\b", text) and re.search(r"vTaskDelay|delay_us|sleep", text):
        return None
    for arg in re.findall(r"vTaskDelay\s*\(((?:[^()]|\([^()]*(?:\([^()]*\))*[^()]*\))*)\)", text):
        ms = delay_ms(arg, defs)
        if ms is None:
            return None
        total += ms
    for fn, factor in BUSY.items():
        for arg in re.findall(r"\b" + fn + r"\s*\(([^;]*)\)\s*;", text):
            v = eval_int(arg, defs)
            if v is None:
                return None
            total += v * factor
    return total


def check(ws):
    main = strip_comments(read(Path(ws) / "main/main.c"))
    defs = defines(main)
    app = function(main, "app_main") or ""
    t = app.find("telemetry_start(")
    if t < 0:
        return False, "app_main nevola telemetry_start()"
    ms = waits(app[:t], defs)
    if ms is None:
        return False, "cekani pred telemetry_start() neumim spocitat"
    if ms > LIMIT_MS:
        return False, f"pred prvni telemetrii se ceka {ms / 1000:g} s (limit potvrzeni OTA 120 s, ma byt do 10 s)"
    return True, f"pred telemetry_start() se ceka {ms / 1000:g} s"


if __name__ == "__main__":
    ok, detail = check(sys.argv[1])
    print(("OK: " if ok else "FAIL: ") + detail)
    sys.exit(0 if ok else 1)
