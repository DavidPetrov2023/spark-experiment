"""B4: payload() po vytisteni JSONu uvolni strom (cJSON_Delete), vraceny retezec neuvolni."""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "suite"))
from csrc import function, read, strip_comments  # noqa: E402


def check(ws):
    src = strip_comments(read(Path(ws) / "main/telemetry.c"))
    payload = function(src, "payload") or ""
    root = re.search(r"cJSON\s*\*\s*(\w+)\s*=\s*cJSON_CreateObject\s*\(\s*\)", payload)
    if not root:
        return False, "payload() nevytvari korenovy objekt"
    var = root.group(1)
    printed = re.search(r"(\w+)\s*=\s*cJSON_Print(?:Unformatted)?\s*\(\s*" + var + r"\s*\)", payload)
    if not printed:
        return False, "payload() JSON netiskne"
    delete = re.search(r"cJSON_Delete\s*\(\s*" + var + r"\s*\)", payload[printed.end():])
    if not delete:
        return False, f"strom '{var}' se po vytisteni neuvolni (unik pameti)"
    out = printed.group(1)
    if re.search(r"(cJSON_)?free\s*\(\s*" + out + r"\s*\)", payload):
        return False, f"payload() uvolni i vraceny retezec '{out}'"
    if not re.search(r"return\s+" + out + r"\s*;", payload):
        return False, f"payload() nevraci '{out}'"
    return True, "strom JSONu se uvolni"


if __name__ == "__main__":
    ok, detail = check(sys.argv[1])
    print(("OK: " if ok else "FAIL: ") + detail)
    sys.exit(0 if ok else 1)
