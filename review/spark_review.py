"""Code review změn v gitu: diff -> model -> zpráva v Markdownu. Model jen čte, nic nemění.

Backendy:
  spark   gpt-oss-120b na Sparku přes LiteLLM (OpenAI API). Kód zůstává ve firmě (vidí ho správce Sparku).
  claude  Claude přes Claude Code (předplatné), bez nástrojů: dostane jen stejný připravený text jako Spark.

Bezpečnost:
  - citlivé soubory (.env, device_config.h, release.py, klíče ...) se do diffu vůbec nedostanou;
  - celý text projde kontrolou tajných údajů (tools/secret_scan.py), při nálezu se nic neodešle;
  - Claude běží v prázdné dočasné složce, takže si nenačte žádný CLAUDE.md ani soubory projektu.

Použití:
  python review/spark_review.py C:/cesta/k/repo --since "24 hours ago"
  python review/spark_review.py C:/cesta/k/repo --range main~3..main --backend claude
  python review/spark_review.py C:/cesta/k/repo --since "1 day ago" --dry-run   (jen připraví a zkontroluje, nic neodešle)
"""

import argparse
import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tools"))
import secret_scan  # noqa: E402

EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
# Citlivé soubory: do textu pro model se nedostanou ani v diffu, ani jako kontext.
EXCLUDE = [".env", ".env.*", "*.env", "device_config.h", "release.py", "*.key", "*.pem", "*.p12", "*.pfx",
           "id_rsa*", "id_ed25519*", "*secret*", "*credential*", "*.token", "sdkconfig", "sdkconfig.old"]
EXCLUDE_DIRS = ["build", ".venv", "node_modules", "managed_components"]
CODE_EXT = {".c", ".h", ".cpp", ".hpp", ".cc", ".py", ".ts", ".js", ".cs", ".java", ".go", ".rs", ".cmake",
            ".txt", ".md", ".json", ".yml", ".yaml", ".ini", ".csv", ".ps1", ".sh"}

INSTRUCTIONS = """Jsi zkušený reviewer kódu, hlavně firmwaru pro ESP32 (C, ESP-IDF, FreeRTOS). Dostaneš změny z gitu
(diff) a plné znění změněných souborů. Najdi skutečné chyby, které změny zavádějí nebo odhalují.

Zaměř se na:
- logické chyby a chyby v jednotkách (ms / tiky / µs / s), přetečení, přetypování, znaménka;
- paměť: úniky, použití po uvolnění, přetečení bufferů, špatné velikosti a typy ukazatelů;
- souběh úloh a přerušení: sdílená data bez zámku, dvoujádrové ESP32;
- blokující čekání, watchdog, časování;
- ošetření chyb a návratových hodnot;
- bezpečnost a spolehlivost aktualizací (OTA, rollback, potvrzení firmwaru) a vše, co je v pravidlech projektu níže.

Pravidla odpovědi:
- Uváděj jen konkrétní problémy, u kterých umíš popsat, co se stane (scénář). Styl ani formátování nekomentuj.
- Nevymýšlej. Když si nejsi jistý, dej to do sekce „Nejisté“.
- Když nic nenajdeš, napiš „Bez nálezů“.
- Piš česky, stručně.

Formát odpovědi:
## Nálezy
Pro každý nález: **závažnost** (kritická / vysoká / střední / nízká), soubor a funkce (případně řádek),
co je špatně, co se kvůli tomu stane, návrh opravy.
## Nejisté
## Souhrn
Nakonec vlož blok ```json se seznamem nálezů pro automatické zpracování:
[{"zavaznost": "vysoká", "soubor": "main/main.c", "funkce": "app_main", "popis": "..."}]
(prázdný seznam [], když nic nenajdeš)."""


def git(repo, *args):
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    if r.returncode:
        raise SystemExit(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout


def pathspec():
    return (["--", "."] + [f":(exclude,glob)**/{p}" for p in EXCLUDE]
            + [f":(exclude,glob)**/{d}/**" for d in EXCLUDE_DIRS])


def resolve_range(repo, since, rng):
    """(base, konec, popis) rozsahu změn."""
    if rng:
        a, _, b = rng.partition("..")
        return git(repo, "rev-parse", a).strip(), git(repo, "rev-parse", b or "HEAD").strip(), rng
    commits = git(repo, "log", f"--since={since}", "--reverse", "--format=%H").split()
    if not commits:
        return None, None, f"od {since}"
    parent = subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify", "-q", commits[0] + "^"],
                            capture_output=True, text=True).stdout.strip()
    return parent or EMPTY_TREE, git(repo, "rev-parse", "HEAD").strip(), f"od {since} ({len(commits)} commitů)"


def excluded(path):
    name = Path(path).name
    return (any(Path(name).match(p) for p in EXCLUDE)
            or any(part in EXCLUDE_DIRS for part in Path(path).parts))


def collect(repo, base, end, max_file_chars):
    """(zprávy commitů, diff, {soubor: obsah}) mezi base a end."""
    log = git(repo, "log", "--format=- %h %s", f"{base}..{end}") if base != EMPTY_TREE else \
        git(repo, "log", "--format=- %h %s", end)
    diff = git(repo, "diff", "--no-color", "-U5", base, end, *pathspec())
    files = {}
    for path in git(repo, "diff", "--name-only", "--diff-filter=AM", base, end, *pathspec()).splitlines():
        if excluded(path) or Path(path).suffix.lower() not in CODE_EXT:
            continue
        r = subprocess.run(["git", "-C", str(repo), "show", f"{end}:{path}"], capture_output=True)
        text = r.stdout.decode("utf-8", errors="replace")
        if r.returncode == 0 and "\x00" not in text:
            files[path] = text if len(text) <= max_file_chars else text[:max_file_chars] + "\n... (zkráceno)"
    return log, diff, files


def build_prompt(rules, log, diff, files):
    parts = [f"# Pravidla projektu\n\n{rules.strip()}\n" if rules else "",
             f"# Commity\n\n{log.strip()}\n", f"# Změny (diff)\n\n```diff\n{diff.strip()}\n```\n",
             "# Plné znění změněných souborů\n"]
    for p, t in files.items():
        parts.append(f"## {p}\n\n```\n{t}\n```\n")
    return "\n".join(x for x in parts if x)


def scan_secrets(text):
    """Seznam kategorií tajných údajů v textu (hodnoty se nikdy nevypisují)."""
    found = set()
    for cat, vals in secret_scan.known_secrets().items():
        if any(v in text for v in vals):
            found.add(cat)
    for cat, rx in secret_scan.GENERIC.items():
        if re.search(rx, text):
            found.add(cat)
    return sorted(found)


def spark_endpoint():
    """(adresa Sparku, název proměnné s klíčem): z proměnné SPARK_URL, jinak z configs.json benchmarku."""
    url = secret_scan.user_env("SPARK_URL")
    cfg_file = ROOT / "esp-bench" / "bench" / "configs.json"
    if not url and cfg_file.exists():
        url = json.loads(cfg_file.read_text(encoding="utf-8"))["spark_provider"]["base_url"]
    if not url:
        raise SystemExit("chybí adresa Sparku: nastav proměnnou prostředí SPARK_URL (adresu dá správce Sparku)")
    return url.rstrip("/").removesuffix("/v1"), "LITELLM_API_KEY"


def call_spark(prompt, model, effort, timeout):
    base_url, key_env = spark_endpoint()
    key = secret_scan.user_env(key_env)
    if not key:
        raise SystemExit(f"chybí klíč v proměnné prostředí {key_env} (osobní klíč dá správce Sparku)")
    body = {"model": model, "reasoning_effort": effort, "max_tokens": 32000,
            "messages": [{"role": "system", "content": INSTRUCTIONS}, {"role": "user", "content": prompt}]}
    req = urllib.request.Request(base_url + "/v1/chat/completions", data=json.dumps(body).encode("utf-8"),
                                 headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as r:
        j = json.loads(r.read().decode("utf-8"))
    u = j.get("usage", {})
    return j["choices"][0]["message"].get("content") or "", f"vstup {u.get('prompt_tokens')} tok, výstup {u.get('completion_tokens')} tok"


def call_claude(prompt, model, effort, timeout):
    claude = shutil.which("claude")
    if not claude:
        raise SystemExit("claude (Claude Code) není v PATH")
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("ANTHROPIC", "CLAUDE"))}
    no_tools = ["Read", "Grep", "Glob", "Edit", "Write", "Bash", "WebFetch", "WebSearch", "Task", "NotebookEdit"]
    with tempfile.TemporaryDirectory(prefix="review-") as d:  # prázdná složka: žádný CLAUDE.md, žádné soubory
        r = subprocess.run([claude, "-p", "--model", model, "--effort", effort, "--output-format", "json",
                            "--no-session-persistence", "--disallowedTools", *no_tools],
                           input=INSTRUCTIONS + "\n\n" + prompt, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", cwd=d, env=env, timeout=timeout)
    try:
        j = json.loads(r.stdout)
    except ValueError:
        raise SystemExit(f"Claude Code nevrátil výsledek: {r.stderr[-500:]}")
    return j.get("result") or "", f"cena podle Claude Code ${j.get('total_cost_usd', 0):.2f} (předplatné)"


def findings(report):
    """Nálezy z bloku ```json na konci zprávy (nebo [] když chybí)."""
    m = re.findall(r"```json\s*(\[.*?\])\s*```", report, re.S)
    try:
        return json.loads(m[-1]) if m else []
    except ValueError:
        return []


def review(repo, base, end, desc, backend="spark", model=None, effort="high", rules_path=None, out_dir=None,
           max_chars=300_000, timeout=3600, dry_run=False, label=None):
    """Proveď review; vrátí (cesta ke zprávě nebo None, nálezy)."""
    repo = Path(repo).resolve()
    model = model or ("gpt-oss-120b" if backend == "spark" else "opus")
    rules_file = Path(rules_path) if rules_path else next(
        (p for p in (repo / "REVIEW-PRAVIDLA.md", HERE / "pravidla-vychozi.md") if p.exists()), None)
    rules = rules_file.read_text(encoding="utf-8") if rules_file else ""
    log, diff, files = collect(repo, base, end, 60_000)
    if not diff.strip():
        print("Žádné změny ke kontrole.")
        return None, []
    prompt = build_prompt(rules, log, diff, files)
    hits = scan_secrets(prompt)
    if hits:
        raise SystemExit("STOP: v textu pro model jsou tajné údaje (" + ", ".join(hits) + "). Nic se neodeslalo.")
    if len(prompt) > max_chars:
        raise SystemExit(f"STOP: text má {len(prompt)} znaků (limit {max_chars}). Zúžit rozsah (--since / --range).")
    out = Path(out_dir) if out_dir else HERE / "vystupy"
    out.mkdir(parents=True, exist_ok=True)
    stem = f"{label or repo.name}-{datetime.now():%Y%m%d-%H%M}-{backend}"
    print(f"Review {repo.name} {desc}: {len(files)} souborů, {len(prompt)} znaků, pravidla: "
          f"{rules_file.name if rules_file else 'žádná'}, backend {backend}/{model}/{effort}")
    if dry_run:
        (out / f"{stem}-vstup.md").write_text(prompt, encoding="utf-8")
        print(f"Nanečisto: kontrola tajných údajů OK, text uložen do {out / (stem + '-vstup.md')}. Nic se neodeslalo.")
        return None, []
    t0 = time.time()
    text, usage = (call_spark if backend == "spark" else call_claude)(prompt, model, effort, timeout)
    secs = time.time() - t0
    head = (f"# Review {repo.name}\n\n- Rozsah: {desc} (`{base[:10]}..{end[:10]}`)\n- Backend: {backend}, model {model}, "
            f"úroveň {effort}\n- Čas: {secs / 60:.1f} min, {usage}\n- Vytvořeno: {datetime.now():%Y-%m-%d %H:%M}\n\n"
            "> Nálezy jsou návrhy modelu. Rozhoduje člověk, nic se automaticky neopravuje.\n\n")
    path = out / f"{stem}.md"
    path.write_text(head + text, encoding="utf-8")
    f = findings(text)
    print(f"Hotovo za {secs / 60:.1f} min: {len(f)} nálezů -> {path}")
    return path, f


def main():
    ap = argparse.ArgumentParser(description="Code review změn v gitu (jen čtení)")
    ap.add_argument("repo")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--since", default="24 hours ago", help='např. "24 hours ago", "7 days ago"')
    g.add_argument("--range", help="rozsah commitů, např. main~3..main")
    ap.add_argument("--backend", choices=["spark", "claude"], default="spark")
    ap.add_argument("--model", help="spark: gpt-oss-120b (výchozí), claude: opus / sonnet (výchozí opus)")
    ap.add_argument("--effort", default="high", help="spark: low/medium/high, claude: low/medium/high/xhigh/max")
    ap.add_argument("--rules", help="soubor s pravidly projektu (výchozí REVIEW-PRAVIDLA.md v repozitáři)")
    ap.add_argument("--out", help="složka pro zprávy (výchozí review/vystupy, mimo git)")
    ap.add_argument("--max-chars", type=int, default=300_000)
    ap.add_argument("--timeout", type=int, default=3600)
    ap.add_argument("--dry-run", action="store_true", help="jen připravit a zkontrolovat text, nic neodeslat")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    base, end, desc = resolve_range(a.repo, a.since, a.range)
    if not base:
        print(f"Žádné commity {desc}.")
        return
    review(a.repo, base, end, desc, a.backend, a.model, a.effort, a.rules, a.out, a.max_chars, a.timeout, a.dry_run)


if __name__ == "__main__":
    main()
