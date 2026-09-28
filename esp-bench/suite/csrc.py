"""Pomucky pro kontrolu C zdrojaku ESPTest: bez komentaru, vytazeni funkce, #define."""

import re
from pathlib import Path


def read(path):
    return Path(path).read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")


def strip_comments(src):
    """Odstrani // a /* */ komentare, retezce a znakove literaly nechava."""
    out, i, n = [], 0, len(src)
    while i < n:
        c = src[i]
        if c in "\"'":
            j = i + 1
            while j < n and src[j] != c:
                j += 2 if src[j] == "\\" else 1
            out.append(src[i:j + 1])
            i = j + 1
        elif src.startswith("//", i):
            j = src.find("\n", i)
            i = n if j < 0 else j
        elif src.startswith("/*", i):
            j = src.find("*/", i + 2)
            i = n if j < 0 else j + 2
            out.append(" ")
        else:
            out.append(c)
            i += 1
    return "".join(out)


def normalize(code):
    """Bez komentaru a s jednou mezerou misto libovolnych bilych znaku."""
    return re.sub(r"\s+", " ", strip_comments(code)).strip()


def function(src, name):
    """Text definice funkce `name` (hlavicka i telo), nebo None. Ocekava kod bez komentaru."""
    for m in re.finditer(r"\b" + re.escape(name) + r"\s*\([^;{)]*\)\s*\{", src):
        start = src.rfind("\n", 0, m.start()) + 1
        depth, i = 0, m.end() - 1
        while i < len(src):
            if src[i] in "\"'":
                q, i = src[i], i + 1
                while i < len(src) and src[i] != q:
                    i += 2 if src[i] == "\\" else 1
            elif src[i] == "{":
                depth += 1
            elif src[i] == "}":
                depth -= 1
                if depth == 0:
                    return src[start:i + 1]
            i += 1
    return None


def defines(src):
    """{jmeno: hodnota} z #define v kodu bez komentaru."""
    return {m.group(1): m.group(2).strip()
            for m in re.finditer(r"^[ \t]*#[ \t]*define[ \t]+(\w+)[ \t]+(.+)$", src, re.M)}


FREERTOS_HZ = 100  # CONFIG_FREERTOS_HZ v sdkconfig sady (vychozi ESP-IDF)
FREERTOS_CONST = {"portTICK_PERIOD_MS": 1000 // FREERTOS_HZ, "configTICK_RATE_HZ": FREERTOS_HZ,
                  "portTICK_RATE_MS": 1000 // FREERTOS_HZ}


def eval_int(expr, defs, depth=0):
    """Celociselna hodnota C vyrazu s #define a konstantami FreeRTOS, nebo None."""
    e = expr
    for _ in range(6):
        # makro pdMS_TO_TICKS(x) = x * configTICK_RATE_HZ / 1000 (i vnorene, napr. v #define)
        e = re.sub(r"\bpdMS_TO_TICKS\s*\(", "_MS2T(", e)
        while "_MS2T(" in e:
            i = e.index("_MS2T(") + 6
            depth, j = 1, i
            while j < len(e) and depth:
                depth += {"(": 1, ")": -1}.get(e[j], 0)
                j += 1
            e = e[:i - 6] + f"(({e[i:j - 1]}) * {FREERTOS_HZ} / 1000)" + e[j:]
        e2 = re.sub(r"\b[A-Za-z_]\w*\b",
                    lambda m: str(FREERTOS_CONST[m.group(0)]) if m.group(0) in FREERTOS_CONST
                    else f"({defs[m.group(0)]})" if m.group(0) in defs else m.group(0), e)
        if e2 == e:
            break
        e = e2
    e = re.sub(r"(\d+)[uUlL]+\b", r"\1", e)
    e = re.sub(r"\(\s*(?:u?int\d+_t|int|long|unsigned|TickType_t)\s*\)", "", e)
    if not re.fullmatch(r"[\s\d()+\-*/%]+", e):
        return None
    try:
        return int(eval(e.replace("/", "//"), {"__builtins__": {}}, {}))  # C celociselne deleni
    except Exception:  # noqa: BLE001
        return None


def delay_ms(arg, defs):
    """Skutecna delka vTaskDelay(arg) v ms: pdMS_TO_TICKS(x) zaokrouhli dolu na tiky, jinak arg jsou tiky."""
    m = re.fullmatch(r"\s*pdMS_TO_TICKS\s*\((.+)\)\s*", arg, re.S)
    if m:
        ms = eval_int(m.group(1), defs)
        return None if ms is None else (ms * FREERTOS_HZ // 1000) * (1000 // FREERTOS_HZ)
    ticks = eval_int(arg, defs)
    return None if ticks is None else ticks * (1000 // FREERTOS_HZ)


def call_args(src, name):
    """Argumenty vsech volani name(...) s ohledem na vnorene zavorky."""
    out = []
    for m in re.finditer(r"\b" + re.escape(name) + r"\s*\(", src):
        depth, i = 1, m.end()
        while i < len(src) and depth:
            depth += {"(": 1, ")": -1}.get(src[i], 0)
            i += 1
        out.append(src[m.end():i - 1])
    return out


def resolve(token, defs, depth=0):
    """Hodnota tokenu po rozvinuti #define (i vicenasobne), jako int, jinak None."""
    token = token.strip().strip("()").strip()
    if re.fullmatch(r"\d+[uUlL]*", token):
        return int(re.sub(r"[uUlL]+$", "", token))
    if token in defs and depth < 5:
        return resolve(defs[token], defs, depth + 1)
    return None


# ---------------------------------------------------------------- pomucky pro tezsi ulohy (X1-X4)

def identifiers(expr):
    return set(re.findall(r"\b[A-Za-z_]\w*\b", expr))


def match_paren(src, i):
    """Index za zavorkou, ktera uzavira zavorku ( { [ na pozici i."""
    pairs = {"(": ")", "{": "}", "[": "]"}
    open_ = src[i]
    close = pairs[open_]
    depth, j = 0, i
    while j < len(src):
        c = src[j]
        if c in "\"'":
            q, j = c, j + 1
            while j < len(src) and src[j] != q:
                j += 2 if src[j] == "\\" else 1
        elif c == open_:
            depth += 1
        elif c == close:
            depth -= 1
            if depth == 0:
                return j + 1
        j += 1
    return len(src)


def functions(src):
    """{jmeno: text definice} vsech funkci definovanych na urovni souboru (kod bez komentaru)."""
    out, depth, i = {}, 0, 0
    starts = {}
    for m in re.finditer(r"\b([A-Za-z_]\w*)\s*\([^;{)]*\)\s*\{", src):
        starts[m.start()] = m
    while i < len(src):
        c = src[i]
        if c in "\"'":
            q, i = c, i + 1
            while i < len(src) and src[i] != q:
                i += 2 if src[i] == "\\" else 1
        elif depth == 0 and i in starts and starts[i].group(1) not in ("if", "while", "for", "switch", "sizeof"):
            m = starts[i]
            end = match_paren(src, m.end() - 1)
            out[m.group(1)] = src[src.rfind("\n", 0, i) + 1:end]
            i = end
            continue
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        i += 1
    return out


def file_scope_decls(src):
    """{jmeno: {type, array, pointer, const, extern, atomic}} promennych na urovni souboru."""
    text = re.sub(r"^[ \t]*#.*$", "", src, flags=re.M)
    flat, depth = [], 0
    for c in text:  # obsah vsech {} pryc (tela funkci, struktury, inicializatory)
        if c == "{":
            depth += 1
            flat.append(";")
        elif c == "}":
            depth -= 1
            flat.append(";")
        elif depth == 0:
            flat.append(c)
    out = {}
    for piece in "".join(flat).split(";"):
        # _Atomic(T) je typ, ne volani funkce: "_Atomic(const char *) x" -> "_Atomic const char * x"
        piece = re.sub(r"\b_Atomic\s*\(([^()]*)\)", r"_Atomic \1", piece)
        decl = piece.split("=", 1)[0].strip()
        if not decl or "(" in decl or decl.startswith("typedef"):
            continue
        tokens = re.findall(r"\w+|\*|\[[^\]]*\]", decl)
        names = [t for t in tokens if re.fullmatch(r"[A-Za-z_]\w*", t)]
        if len(names) < 2:
            continue
        name = names[-1]
        pointer = "*" in tokens
        quals = {"extern", "static", "volatile", "const", "_Atomic", "register"}
        out[name] = {
            "type": " ".join(t for t in names[:-1] if t not in quals),
            "array": any(t.startswith("[") for t in tokens),
            "pointer": pointer,
            # const u ukazatele: jen "* const" dela konstantni promennou, "const char *" ne
            "const": ("const" in names[:-1]) and not pointer,
            "extern": "extern" in names,
            "atomic": "_Atomic" in names or any(t.startswith("atomic_") for t in names[:-1]),
        }
    return out


LOCK_RE = (r"\b(portENTER_CRITICAL\w*|taskENTER_CRITICAL\w*|vPortEnterCritical\w*|xSemaphoreTake\w*"
           r"|vTaskSuspendAll|\w*_lock|lock)\s*\(")
UNLOCK_RE = (r"\b(portEXIT_CRITICAL\w*|taskEXIT_CRITICAL\w*|vPortExitCritical\w*|xSemaphoreGive\w*"
             r"|xTaskResumeAll|\w*_unlock|unlock)\s*\(")


def lock_protected(body, pos):
    """Je pozice pos v tele funkce mezi zamcenim a odemcenim (kriticka sekce, mutex)?"""
    events = [(m.start(), "lock") for m in re.finditer(LOCK_RE, body)]
    events += [(m.start(), "unlock") for m in re.finditer(UNLOCK_RE, body)]
    before = [e for e in sorted(events) if e[0] < pos]
    after = [e for e in events if e[0] > pos and e[1] == "unlock"]
    return bool(before) and before[-1][1] == "lock" and bool(after)


def enclosing_conditions(text, pos):
    """Podminky vsech if (a else vetvi jako '!(...)'), uvnitr kterych lezi pozice pos."""
    conds = []
    for m in re.finditer(r"\bif\s*\(", text[:pos]):
        close = match_paren(text, m.end() - 1)
        cond = text[m.end():close - 1]
        j = close
        while j < len(text) and text[j].isspace():
            j += 1
        end = match_paren(text, j) if j < len(text) and text[j] == "{" else text.find(";", j) + 1
        if close <= pos < end:
            conds.append(cond)
            continue
        k = end
        while k < len(text) and text[k].isspace():
            k += 1
        if text.startswith("else", k):
            k += 4
            while k < len(text) and text[k].isspace():
                k += 1
            e_end = match_paren(text, k) if k < len(text) and text[k] == "{" else text.find(";", k) + 1
            if k <= pos < e_end:
                conds.append("!(" + cond + ")")
    return conds
