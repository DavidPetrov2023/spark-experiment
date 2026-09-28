"""X1: dve chyby v jednom hlaseni, uspech jen kdyz jsou opravene obe.

a) Cervena LED ve smycce app_main strida uroven a mezi zmenami ceka 500 ms. Vyhodnocuje se
   simulaci smycky vcetne deklaraci: promenna deklarovana uvnitr smycky se kazdym pruchodem
   nastavi znovu (chyba), static uvnitr smycky jen jednou (spravne).
b) payload() nic neztraci: strom se po vytisteni smaze a kazdy vystup cJSON_Print*, ktery se
   nevraci, se uvolni (cJSON_free / free).
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "suite"))
from csrc import defines, delay_ms, function, match_paren, read, strip_comments  # noqa: E402

TYPES = {"bool": (1, False), "_Bool": (1, False), "int": (32, True), "int32_t": (32, True),
         "uint32_t": (32, False), "unsigned": (32, False), "uint8_t": (8, False), "int8_t": (8, True),
         "uint16_t": (16, False), "int16_t": (16, True), "char": (8, True), "long": (32, True)}


def store(val, typ):
    bits, signed = TYPES[typ]
    if bits == 1:
        return 1 if val else 0
    val = int(val) & ((1 << bits) - 1)
    return val - (1 << bits) if signed and val >= 1 << (bits - 1) else val


def c_to_py(expr):
    e = re.sub(r"\(\s*(?:bool|_Bool|int|unsigned|u?int\d+_t)\s*\)", "", expr.strip())
    m = re.fullmatch(r"(.+?)\?(.+):(.+)", e, re.S)
    if m:
        return f"(({c_to_py(m.group(2))}) if ({c_to_py(m.group(1))}) else ({c_to_py(m.group(3))}))"
    e = re.sub(r"\btrue\b", "1", e)
    e = re.sub(r"\bfalse\b", "0", e)
    e = e.replace("&&", " and ").replace("||", " or ")
    return re.sub(r"!(?!=)", " not ", e)


def evaluate(expr, env):
    try:
        return int(eval(c_to_py(expr), {"__builtins__": {}}, dict(env)))
    except Exception:  # noqa: BLE001
        return None


def parse_block(text):
    """Seznam prikazu: ('if', podminka, then, else) nebo ('stmt', text)."""
    out, i = [], 0
    while i < len(text):
        while i < len(text) and (text[i].isspace() or text[i] == ";"):
            i += 1
        if i >= len(text):
            break
        if text[i] == "{":
            end = match_paren(text, i)
            out.extend(parse_block(text[i + 1:end - 1]))
            i = end
        elif re.match(r"if\s*\(", text[i:]):
            p = text.index("(", i)
            close = match_paren(text, p)
            then, i = parse_one(text, close)
            els = []
            j = i
            while j < len(text) and text[j].isspace():
                j += 1
            if text.startswith("else", j) and not re.match(r"\w", text[j + 4:j + 5]):
                els, i = parse_one(text, j + 4)
            out.append(("if", text[p + 1:close - 1], then, els))
        else:
            j, depth = i, 0
            while j < len(text) and not (text[j] == ";" and depth == 0):
                depth += {"(": 1, ")": -1}.get(text[j], 0)
                j += 1
            out.append(("stmt", text[i:j].strip()))
            i = j + 1
    return out


def parse_one(text, i):
    while i < len(text) and text[i].isspace():
        i += 1
    if i < len(text) and text[i] == "{":
        end = match_paren(text, i)
        return parse_block(text[i + 1:end - 1]), end
    j, depth = i, 0
    while j < len(text) and not (text[j] == ";" and depth == 0):
        depth += {"(": 1, ")": -1}.get(text[j], 0)
        j += 1
    return parse_block(text[i:j + 1]), j + 1


def run(block, env, types, defs, events):
    for kind, *rest in block:
        if kind == "if":
            cond = evaluate(rest[0], env)
            if cond is None:
                raise ValueError(f"podminka {rest[0]!r}")
            run(rest[1] if cond else rest[2], env, types, defs, events)
            continue
        s = rest[0]
        m = re.fullmatch(r"gpio_set_level\s*\(\s*LED_RED\s*,(.+)\)", s, re.S)
        if m:
            v = evaluate(m.group(1), env)
            if v is None:
                raise ValueError(f"uroven {m.group(1).strip()!r}")
            events.append(("set", 1 if v else 0))
            continue
        m = re.fullmatch(r"vTaskDelay\s*\((.+)\)", s, re.S)
        if m:
            ms = delay_ms(m.group(1), defs)
            if ms is None:
                raise ValueError(f"zpozdeni {m.group(1).strip()!r}")
            events.append(("delay", ms))
            continue
        m = re.fullmatch(r"(static\s+)?(?:volatile\s+)?(" + "|".join(TYPES) + r")\s+(\w+)\s*(?:=\s*(.+))?", s, re.S)
        if m:
            static, typ, name, init = m.groups()
            types[name] = typ
            if static and ("static", name) in env:
                continue
            val = evaluate(init, env) if init else 0
            if val is None:
                raise ValueError(f"deklarace {s!r}")
            env[name] = store(val, typ)
            if static:
                env[("static", name)] = True
            continue
        m = re.fullmatch(r"(\w+)\s*([\^+\-|&*]?)=(?!=)\s*(.+)", s, re.S)
        if m and m.group(1) in types:
            name, op, rhs = m.groups()
            val = evaluate(f"{name} {op} ({rhs})" if op else rhs, env)
            if val is None:
                raise ValueError(f"prirazeni {s!r}")
            env[name] = store(val, types[name])
            continue
        m = re.fullmatch(r"(\+\+|--)?\s*(\w+)\s*(\+\+|--)?", s)
        if m and m.group(2) in types and (m.group(1) or m.group(3)):
            step = 1 if "++" in (m.group(1) or m.group(3)) else -1
            env[m.group(2)] = store(env[m.group(2)] + step, types[m.group(2)])
            continue
        if re.search(r"\bLED_RED\b", s):
            raise ValueError(f"prikaz {s!r}")


def check_led(main):
    defs = defines(main)
    app = function(main, "app_main") or ""
    w = re.search(r"\bwhile\s*\(\s*(1|true)\s*\)\s*\{", app)
    if not w:
        return False, "v app_main chybi smycka while (1)"
    body = app[w.end():match_paren(app, w.end() - 1) - 1]
    types, env = {}, {}
    decl_area = main[:main.find(app)] + app[:w.start()]
    for m in re.finditer(r"\b(?:static\s+)?(?:volatile\s+)?(" + "|".join(TYPES) + r")\s+(\w+)\s*(?:=\s*([^;]+))?;",
                         decl_area):
        types[m.group(2)] = m.group(1)
        init = evaluate(m.group(3), {}) if m.group(3) else 0
        env[m.group(2)] = store(init or 0, m.group(1))
    events = []
    try:
        block = parse_block(body)
        for _ in range(4):
            run(block, env, types, defs, events)
    except ValueError as ex:
        return False, f"smycku neumim vyhodnotit: {ex}"
    sets = [i for i, e in enumerate(events) if e[0] == "set"]
    if len(sets) < 4:
        return False, "smycka nenastavuje LED_RED"
    levels = [events[i][1] for i in sets]
    if any(a == b for a, b in zip(levels, levels[1:])):
        return False, f"LED_RED nestrida uroven: {levels[:6]}"
    for a, b in zip(sets, sets[1:]):
        wait = sum(e[1] for e in events[a:b] if e[0] == "delay")
        if wait != 500:
            return False, f"mezi zmenami LED_RED se ceka {wait} ms, ma 500 ms"
    return True, "LED_RED strida po 500 ms"


def check_leak(tel):
    payload = function(tel, "payload") or ""
    root = re.search(r"cJSON\s*\*\s*(\w+)\s*=\s*cJSON_CreateObject\s*\(\s*\)", payload)
    if not root:
        return False, "payload() nevytvari korenovy objekt"
    var = root.group(1)
    ret = re.search(r"return\s+(\w+)\s*;", payload)
    if not ret:
        return False, "payload() nic nevraci"
    out = ret.group(1)
    printed = list(re.finditer(r"cJSON_Print(?:Unformatted|Buffered)?\s*\(", payload))
    if not printed:
        return False, "payload() JSON netiskne"
    for m in printed:
        a = re.search(r"(\w+)\s*=\s*$", payload[:m.start()])
        if not a:
            return False, "vystup cJSON_Print se nikam neulozi, takze se neuvolni (unik)"
        name = a.group(1)
        if name == out:
            if not re.search(r"cJSON_Delete\s*\(\s*" + var + r"\s*\)", payload[m.end():]):
                return False, f"strom '{var}' se po vytisteni neuvolni (unik)"
            continue
        if not re.search(r"\b(?:cJSON_free|free)\s*\(\s*" + name + r"\s*\)", payload[m.end():]):
            return False, f"retezec '{name}' z cJSON_Print se neuvolni (unik)"
    if re.search(r"\b(?:cJSON_free|free)\s*\(\s*" + out + r"\s*\)", payload):
        return False, f"payload() uvolni i vraceny retezec '{out}'"
    return True, "payload() nic neztraci"


def check(ws):
    main = strip_comments(read(Path(ws) / "main/main.c"))
    tel = strip_comments(read(Path(ws) / "main/telemetry.c"))
    ok_led, d_led = check_led(main)
    ok_leak, d_leak = check_leak(tel)
    return ok_led and ok_leak, f"LED: {d_led}; pamet: {d_leak}"


if __name__ == "__main__":
    ok, detail = check(sys.argv[1])
    print(("OK: " if ok else "FAIL: ") + detail)
    sys.exit(0 if ok else 1)
