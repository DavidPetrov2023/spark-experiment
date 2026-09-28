"""Kontrola tajnych udaju pred commitem (spousti ji .git/hooks/pre-commit).

Hleda ve staged souborech:
  - obecne vzory (sk-... klice, GitHub tokeny, privatni klice, AWS klice);
  - skutecne hodnoty, ktere se nacitaji az za behu a nikde se neukladaji ani nevypisuji:
    klic LITELLM_API_KEY z uzivatelskych promennych prostredi, hodnoty z .env,
    device_config.h a release.py originalniho firmwaru ESPTest (adresa serveru, token, IP, root@).

Pri nalezu vypise jen soubor a kategorii, nikdy hodnotu, a commit zastavi.

    python tools/secret_scan.py            # staged soubory (pre-commit)
    python tools/secret_scan.py --all      # vsechny soubory v repozitari
"""

import os
import re
import subprocess
import sys
import urllib.parse
from pathlib import Path

ESPTEST = Path(os.environ.get("ESPTEST_DIR", r"C:\Cloud\AI\ESPTest"))
GENERIC = {
    "sk- klic": r"\bsk-[A-Za-z0-9_\-]{16,}",
    "GitHub token": r"\bgh[pousr]_[A-Za-z0-9]{20,}",
    "privatni klic": r"BEGIN [A-Z ]*PRIVATE KEY",
    "AWS klic": r"\bAKIA[0-9A-Z]{16}\b",
}


def user_env(name):
    val = os.environ.get(name)
    if val or os.name != "nt":
        return val
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            return winreg.QueryValueEx(k, name)[0]
    except OSError:
        return None


def known_secrets():
    """{kategorie: {hodnoty}} ze skutecnych zdroju. Hodnoty se nikdy nevypisuji."""
    out = {}

    def add(cat, v):
        v = (v or "").strip().strip("\"'")
        if len(v) >= 6:
            out.setdefault(cat, set()).add(v)

    add("klic LiteLLM", user_env("LITELLM_API_KEY"))
    env = ESPTEST / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.match(r"\s*[A-Za-z_]\w*\s*=\s*(.+)$", line)
            if m and not line.strip().startswith("#"):
                add("hodnota z .env", m.group(1))
    dc = ESPTEST / "main" / "device_config.h"
    if dc.exists():
        for name, val in re.findall(r'^\s*#\s*define\s+(\w+)\s+"([^"]*)"', dc.read_text(encoding="utf-8", errors="replace"), re.M):
            add("device_config.h " + name, val)
            u = urllib.parse.urlparse(val)
            add("adresa serveru telemetrie", u.hostname)
            for _, q in urllib.parse.parse_qsl(u.query):
                add("token v URL telemetrie", q)
    rp = ESPTEST / "release.py"
    if rp.exists():
        t = rp.read_text(encoding="utf-8", errors="replace")
        for v in re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", t):
            add("IP z release.py", v)
        for v in re.findall(r"https?://([^/\s\"']+)", t):
            add("adresa z release.py", v)
        for v in re.findall(r"root@[\w.\-]+", t):
            add("root@ z release.py", v)
    return out


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, check=True).stdout


def files(all_files):
    if all_files:
        names = git("ls-files", "-z").decode("utf-8").split("\0")
        return [(n, lambda n=n: Path(n).read_bytes()) for n in names if n and Path(n).is_file()]
    names = git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z").decode("utf-8").split("\0")
    return [(n, lambda n=n: git("show", ":" + n)) for n in names if n]


def main():
    secrets = known_secrets()
    found = []
    for name, read in files("--all" in sys.argv):
        text = read().decode("utf-8", errors="replace")
        for cat, vals in secrets.items():
            if any(v in text for v in vals):
                found.append((name, cat))
        for cat, rx in GENERIC.items():
            if re.search(rx, text):
                found.append((name, cat))
    if found:
        print("TAJNE UDAJE ve souborech, commit zastaven:")
        for name, cat in found:
            print(f"  {name}: {cat}")
        print("Odstran je (hodnoty patri jen do promennych prostredi) a zkus to znovu.")
        return 1
    print(f"secret_scan: OK ({sum(len(v) for v in secrets.values())} znamych hodnot + obecne vzory)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
