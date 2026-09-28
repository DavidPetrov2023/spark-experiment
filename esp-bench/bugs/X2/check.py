"""X2: EventState ukazuje stav cervene LED bez soubehu mezi ulohami.

Chyba: smycka blikani (app_main) prepisuje sdileny retezec snprintf a telemetrie (jina uloha,
muze bezet na druhem jadru) ho soucasne cte -> obcas 'blink_onf' / 'blink_of'.
Oprav je vic: zamek (kriticka sekce, mutex) kolem zapisu i cteni pole, nebo misto pole
atomicky zapisovana hodnota (bool, ukazatel na konstantni retezec). Kontrola proto:
  - EventState neni pevny retezec a payload() cte stav, ktery smycka blikani meni;
  - hodnoty blink_on / blink_off zustaly;
  - kazdy pristup k nove sdilenemu poli znaku (mimo sizeof) je v obou souborech pod zamkem.
"""

import re
import sys
from pathlib import Path

SUITE = Path(__file__).resolve().parents[2] / "suite"
sys.path.insert(0, str(SUITE))
from csrc import (file_scope_decls, function, functions, identifiers, lock_protected,  # noqa: E402
                  match_paren, read, strip_comments)

BASELINE = SUITE.parent / "baseline"


def check(ws):
    ws = Path(ws)
    main = strip_comments(read(ws / "main/main.c"))
    tel = strip_comments(read(ws / "main/telemetry.c"))
    base = {f: strip_comments(read(BASELINE / f)) for f in ("main/main.c", "main/telemetry.c")}

    payload = function(tel, "payload") or ""
    m = re.search(r'"EventState"\s*,', payload)
    if not m:
        return False, "payload() neposila EventState"
    call = payload.rfind("(", 0, m.start())
    expr = payload[m.end():match_paren(payload, call) - 1].strip()
    if re.fullmatch(r'"[^"]*"', expr):
        return False, f"EventState je pevny retezec {expr}, neukazuje stav LED"

    base_names = set()
    for src in base.values():
        base_names |= set(file_scope_decls(src)) | set(functions(src))
    decls = {**file_scope_decls(main), **file_scope_decls(tel)}
    funcs = {"main.c": functions(main), "telemetry.c": functions(tel)}
    new_names = (set(decls) | set(funcs["main.c"]) | set(funcs["telemetry.c"])) - base_names

    app = function(main, "app_main") or ""
    w = app.find("while")
    if w < 0:
        return False, "v app_main chybi smycka blikani"
    if not identifiers(app[w:]) & new_names:
        return False, "smycka blikani nemeni stav, ze ktereho se bere EventState"
    if not identifiers(payload) & new_names:
        return False, "payload() necte stav LED"

    both = main + tel
    if not (("blink_on" in both and "blink_off" in both) or "blink_%s" in both):
        return False, "EventState uz nema hodnoty blink_on / blink_off"

    arrays = [n for n in new_names if n in decls and decls[n]["array"] and "char" in decls[n]["type"]
              and not decls[n]["const"]]
    for name in arrays:
        for fname, fns in funcs.items():
            for fn, body in fns.items():
                for r in re.finditer(r"\b" + re.escape(name) + r"\b", body):
                    if re.search(r"sizeof\s*\(?\s*$", body[:r.start()]):
                        continue
                    if not lock_protected(body, r.start()):
                        return False, f"{fname}: {fn}() pristupuje ke sdilenemu poli {name} bez zamku (soubeh)"
    how = f"pole {', '.join(arrays)} pod zamkem" if arrays else "atomicka hodnota"
    return True, f"EventState ze stavu LED bez soubehu ({how})"


if __name__ == "__main__":
    ok, detail = check(sys.argv[1])
    print(("OK: " if ok else "FAIL: ") + detail)
    sys.exit(0 if ok else 1)
