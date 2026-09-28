"""X4 (nova funkce): LiveStatus posila RSSI a MinFreeHeap, ostatni pole beze zmeny.

- RSSI: z esp_wifi_sta_get_ap_info (ap.rssi) nebo esp_wifi_sta_get_rssi; pridava se jen pri
  uspechu (volani je v podmince, ktera testuje navratovou hodnotu).
- MinFreeHeap: minimum od startu (esp_get_minimum_free_heap_size nebo
  heap_caps_get_minimum_free_size), ne aktualni volny heap.
- Obe pole v objektu LiveStatus (primo v payload(), nebo v pomocne funkci, ktere payload preda
  LiveStatus). Vsechna puvodni pole payload() zustala.
"""

import re
import sys
from pathlib import Path

SUITE = Path(__file__).resolve().parents[2] / "suite"
sys.path.insert(0, str(SUITE))
from csrc import (call_args, enclosing_conditions, function, functions, identifiers, match_paren,  # noqa: E402
                  normalize, read, strip_comments)

BASELINE = SUITE.parent / "baseline"
WIFI = r"\besp_wifi_sta_get_(?:ap_info|rssi)\s*\("
MIN_HEAP = r"\b(?:esp_get_minimum_free_heap_size|heap_caps_get_minimum_free_size)\s*\("
ADD = r'\bcJSON_Add(?:Number|Item)ToObject\s*\(\s*(\w+)\s*,\s*"{field}"\s*,'


def uses(expr, pattern, scope, funcs, depth=0):
    """Pouziva vyraz (primo, pres promennou nebo pres pomocnou funkci) volani podle pattern?"""
    if re.search(pattern, expr):
        return True
    if depth > 2:
        return False
    for ident in identifiers(expr):
        if ident in funcs and re.search(pattern, funcs[ident]):
            return True
        for a in re.finditer(r"\b" + ident + r"\s*=(?!=)\s*([^;]+);", scope):
            if uses(a.group(1), pattern, scope, funcs, depth + 1):
                return True
        for c in re.finditer(r"(\w+)\s*\([^;]*&\s*" + ident + r"\b", scope):
            if re.search(pattern, c.group(0)) or (c.group(1) in funcs and re.search(pattern, funcs[c.group(1)])):
                return True
    return False


def early_exits(body, pos):
    """Podminky 'if (...) return/goto' pred pozici pos: pri chybe se k pridani pole nedojde."""
    conds = []
    for m in re.finditer(r"\bif\s*\(", body[:pos]):
        close = match_paren(body, m.end() - 1)
        j = close
        while j < len(body) and body[j].isspace():
            j += 1
        end = match_paren(body, j) if body[j] == "{" else body.find(";", j) + 1
        if end <= pos and re.search(r"\b(return|goto)\b", body[j:end]):
            conds.append(body[m.end():close - 1])
    return conds


def find_add(field, payload, live, funcs):
    """(telo funkce, pozice, vyraz hodnoty) pridani pole do LiveStatus, nebo chyba."""
    for fn, body in [("payload", payload)] + [(n, b) for n, b in funcs.items() if n != "payload"]:
        for m in re.finditer(ADD.format(field=field), body):
            if fn == "payload" and m.group(1) != live:
                return None, f"{field} se pridava do '{m.group(1)}', ne do LiveStatus"
            if fn != "payload" and not re.search(r"\b" + fn + r"\s*\([^;]*\b" + live + r"\b", payload):
                return None, f"{field} se pridava ve funkci {fn}(), ktera nedostane LiveStatus z payload()"
            args = call_args(body[m.start():], re.search(r"cJSON_Add\w+", m.group(0)).group(0))[0]
            return (body, m.start(), args.split(",", 2)[2].strip()), None
    return None, f"LiveStatus neobsahuje {field}"


def check(ws):
    tel = strip_comments(read(Path(ws) / "main/telemetry.c"))
    funcs = functions(tel)
    payload = funcs.get("payload") or ""
    base_payload = function(strip_comments(read(BASELINE / "main/telemetry.c")), "payload")
    now = normalize(payload)
    for stmt in re.findall(r"cJSON_Add\w+\s*\([^;]*\)\s*;", base_payload):
        if normalize(stmt) not in now:
            return False, f"zmenene nebo chybejici puvodni pole: {normalize(stmt)}"
    live = re.search(r"cJSON\s*\*\s*(\w+)\s*=\s*cJSON_AddObjectToObject\s*\(\s*\w+\s*,\s*\"LiveStatus\"", payload)
    if not live:
        return False, "payload() nevytvari LiveStatus"
    live = live.group(1)

    found, err = find_add("MinFreeHeap", payload, live, funcs)
    if err:
        return False, err
    body, _, expr = found
    if not uses(expr, MIN_HEAP, body, funcs):
        return False, f"MinFreeHeap neni minimum od startu: {expr}"

    found, err = find_add("RSSI", payload, live, funcs)
    if err:
        return False, err
    body, pos, expr = found
    if not uses(expr, WIFI, body, funcs):
        return False, f"RSSI se nebere z WiFi (esp_wifi_sta_get_ap_info / esp_wifi_sta_get_rssi): {expr}"
    conds = enclosing_conditions(body, pos) + early_exits(body, pos)
    if not any(re.search(r"\bESP_OK\b|\bESP_FAIL\b", c) or uses(c, WIFI, body, funcs) for c in conds):
        return False, "RSSI se posila, i kdyz se ho nepodari zjistit (chybi test navratove hodnoty)"
    return True, "LiveStatus posila RSSI (jen pri uspechu) a MinFreeHeap"


if __name__ == "__main__":
    ok, detail = check(sys.argv[1])
    print(("OK: " if ok else "FAIL: ") + detail)
    sys.exit(0 if ok else 1)
