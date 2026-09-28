"""Obecny runner benchmarku oprav chyb.

Model dostane cistou pracovni kopii projektu s jednou vnesenou chybou a popis
priznaku. Po jeho behu benchmark sam overi guard (chranene casti), sestavi build
a zkontroluje opravu. Kazda kombinace chyba x konfigurace x opakovani ma stejne
vstupy, takze jde merit i opakovatelnost.

Sadu popisuje suite.json (baseline, chyby v bugs/<ID>/ s task.md, bug.patch,
check.py a meta.json, build, guard, sablona zadani). Modely jsou v configs.json.

    python bench/run_bench.py --verify                 # overit baseline, chyby a guard
    python bench/run_bench.py --bugs B2 --reps 1       # pilot
    python bench/run_bench.py --reps 3                 # plny beh
    python bench/run_bench.py --resume results/<cas>   # dokoncit preruseny beh
"""

import argparse
import glob
import hashlib
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

BENCH_DIR = Path(__file__).resolve().parent
GIT = ["git", "-c", "core.autocrlf=false", "-c", "user.name=bench", "-c", "user.email=bench@local"]
HARNESS_CONFIGS = [".claude", "opencode.json"]


# ---------------------------------------------------------------- pomucky

def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_suite(path):
    suite = load_json(path)
    suite["_root"] = Path(path).resolve().parent
    return suite


def sp(suite, key):
    return suite["_root"] / suite[key]


# Soubory s instrukcemi, ktere si harness nacte sam: Claude Code prochazi CLAUDE.md ve vsech nadrazenych
# slozkach pracovni kopie a v ~/.claude, OpenCode AGENTS.md / CLAUDE.md (do korene git repozitare) a globalni
# pravidla. Cokoli z nich by se dostalo do kontextu modelu navic k zadani (27. 9.: CLAUDE.md projektu v 16 bezich).
INSTRUCTION_FILES = ["CLAUDE.md", "CLAUDE.local.md", "AGENTS.md", ".claude/CLAUDE.md"]


def context_leaks(ws):
    """Soubory s instrukcemi v nadrazenych slozkach pracovni kopie a v globalni konfiguraci harnessu."""
    found = []
    for d in Path(ws).resolve().parents:
        found += [d / f for f in INSTRUCTION_FILES if (d / f).exists()]
    home = Path.home()
    for p in (home / ".claude" / "CLAUDE.md", home / ".config" / "opencode" / "AGENTS.md"):
        if p.exists():
            found.append(p)
    return found


def list_bugs(suite):
    root = sp(suite, "bugs_dir")
    return sorted(p.name for p in root.iterdir() if (p / "task.md").exists())


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(Path(path).parent))
    spec.loader.exec_module(mod)
    return mod


def user_env(name):
    """Promenna prostredi, i kdyz byla ulozena do uzivatelskych az po startu shellu."""
    if os.environ.get(name):
        return os.environ[name]
    if os.name == "nt":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                return winreg.QueryValueEx(k, name)[0]
        except OSError:
            return None
    return None


def rmtree(path):
    def onerror(func, p, _exc):
        os.chmod(p, stat.S_IWRITE)  # objekty v .git jsou na Windows jen pro cteni
        func(p)
    if Path(path).exists():
        shutil.rmtree(path, onerror=onerror)


def git(ws, *args, check=True):
    r = subprocess.run(GIT + list(args), cwd=ws, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout


def run_process(cmd, cwd, env, timeout, stdin_text=None):
    """(exit, stdout, stderr, timed_out, sekundy). Pri timeoutu zabije cely strom procesu."""
    t0 = time.time()
    p = subprocess.Popen(cmd, cwd=cwd, env=env, stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    data = stdin_text.encode("utf-8") if stdin_text is not None else None
    try:
        out, err = p.communicate(input=data, timeout=timeout)
        timed_out = False
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True)
        else:
            p.kill()
        out, err = p.communicate()
        timed_out = True
    dec = lambda b: (b or b"").decode("utf-8", errors="replace")  # noqa: E731
    return p.returncode, dec(out), dec(err), timed_out, time.time() - t0


# ---------------------------------------------------------------- pracovni kopie

def claude_allowed_tools(suite):
    """Povoleni pro Claude Code pres --allowedTools. Projektove .claude/settings.json by v nedueryhodne
    slozce ignoroval. Read/Edit/Write/Glob/Grep se zamerne nepovoluji: holy 'Read' by povolil cteni
    kdekoli na disku (i originalu projektu s opravou); v pracovni slozce je Claude Code povoli sam."""
    rules = []
    for c in suite.get("allowed_commands", []):
        rules += [f"Bash({c})", f"Bash({c}:*)"]
    return rules


def opencode_settings(suite, spark):
    bash = {"*": "deny"}
    for c in suite.get("allowed_commands", []):
        bash[c + "*"] = "allow"
    models = {m: {"name": m, "limit": {"context": v["context"], "output": v["output"]}} for m, v in spark["models"].items()}
    for m, v in spark["models"].items():
        if v.get("reasoning"):  # uroven premysleni (gpt-oss: low / medium / high), jinak vychozi serveru
            models[m]["options"] = {"reasoningEffort": v["reasoning"]}
    return {
        "$schema": "https://opencode.ai/config.json",
        "provider": {"spark": {
            "npm": "@ai-sdk/openai-compatible",
            "name": "Spark (LiteLLM)",
            "options": {"baseURL": spark["base_url"] + "/v1", "apiKey": "{env:" + spark["api_key_env"] + "}"},
            "models": models,
        }},
        "permission": {
            "read": "allow", "edit": "allow", "glob": "allow", "grep": "allow", "lsp": "allow",
            "task": "allow", "bash": bash,
            "webfetch": "deny", "websearch": "deny", "external_directory": "deny",
            "question": "deny", "skill": "deny", "doom_loop": "deny",
        },
    }


def install_harness_files(suite, ws):
    for dst, src in suite.get("harness_files", {}).items():
        shutil.copy(suite["_root"] / src, ws / dst)


def make_workspace(suite, spark, bug, ws, harness=None):
    """Cista kopie: baseline + skripty harnessu + patch chyby, commit 'start'.
    Vsechny konfigurace dostanou stejny obsah; navic jen opencode.json pro OpenCode
    (Claude Code dostane nastaveni parametry prikazove radky).

    build.persist (napr. build/, sdkconfig) se mezi behy v teze slozce zachova, at se neprekladá
    cele ESP-IDF znovu. Zdrojaky se kopiruji s aktualnim casem zmeny (shutil.copy, ne copy2),
    takze je ninja urcite prelozi znovu a nezustanou objekty z predchoziho behu."""
    persist = suite["build"].get("persist", [])
    saved = ws.parent / (ws.name + ".persist")
    rmtree(saved)
    if ws.exists() and persist:
        saved.mkdir(parents=True)
        for rel in persist:
            if (ws / rel).exists():
                shutil.move(str(ws / rel), str(saved / rel))
    rmtree(ws)
    shutil.copytree(sp(suite, "baseline"), ws, copy_function=shutil.copy)
    for rel in persist:
        if (saved / rel).exists():
            shutil.move(str(saved / rel), str(ws / rel))
    rmtree(saved)
    install_harness_files(suite, ws)
    if harness == "opencode":
        (ws / "opencode.json").write_text(json.dumps(opencode_settings(suite, spark), indent=2), encoding="utf-8")
    # Nejdriv vlastni repozitar: git apply uvnitr ciziho repozitare (work/ lezi v esp-bench)
    # bere cesty relativne k nemu a soubory mimo aktualni slozku potichu preskoci.
    git(ws, "init", "-q")
    patch = sp(suite, "bugs_dir") / bug / "bug.patch" if bug else None
    if patch and patch.exists():  # uloha typu nova funkce patch nema, zacina z baseline
        git(ws, "apply", "--whitespace=nowarn", str(patch))
        for rel in re.findall(r"^\+\+\+ b/(.+)$", patch.read_text(encoding="utf-8"), re.M):
            if (ws / rel).read_bytes() == (sp(suite, "baseline") / rel).read_bytes():
                raise RuntimeError(f"{bug}: patch se neaplikoval na {rel}")
    git(ws, "add", "-A")
    git(ws, "commit", "-qm", "start")  # jediny commit: historie neprozradi, co chyba zmenila


def workspace_diff(suite, ws):
    """(diff, pridane, odebrane, soubory) proti commitu 'start', bez souboru harnessu."""
    git(ws, "add", "-A")
    exclude = [f":!{p}" for p in list(suite.get("harness_files", {})) + HARNESS_CONFIGS + [".opencode"]]
    spec = ["--", "."] + exclude
    diff = git(ws, "diff", "--cached", *spec)
    added = removed = 0
    files = []
    for line in git(ws, "diff", "--cached", "--numstat", *spec).splitlines():
        a, r, f = line.split("\t", 2)
        added += int(a) if a.isdigit() else 0
        removed += int(r) if r.isdigit() else 0
        files.append(f)
    return diff, added, removed, files


def diff_signature(diff):
    """Otisk opravy: jen pridane/odebrane radky bez bilych znaku (pro shodu mezi opakovanimi)."""
    lines = [re.sub(r"\s+", "", ln) for ln in diff.splitlines()
             if ln[:1] in "+-" and not ln.startswith(("+++", "---"))]
    return hashlib.sha1("\n".join(lines).encode("utf-8")).hexdigest()[:10] if lines else "bez-zmen"


# ---------------------------------------------------------------- build a kontroly

def build(suite, ws):
    b = suite["build"]
    rc, out, err, timed_out, secs = run_process(b["cmd"], ws, os.environ.copy(), b.get("timeout_s", 900))
    log = ws / b.get("log", "build.log")
    text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else out
    warnings = len(re.findall(b.get("warning_regex", "warning:"), text))
    return {"build_ok": rc == 0 and not timed_out, "build_s": round(secs, 1), "warnings": warnings,
            "build_output": (out + err)[-4000:]}


def run_check(suite, bug, ws):
    mod = load_module(sp(suite, "bugs_dir") / bug / "check.py", f"check_{bug}")
    try:
        ok, detail = mod.check(ws)
    except Exception as ex:  # noqa: BLE001
        ok, detail = False, f"kontrola spadla: {ex}"
    return bool(ok), detail


def run_guard(suite, ws):
    if not suite.get("guard"):
        return {"ok": True, "violations": []}
    mod = load_module(sp(suite, "guard"), "suite_guard")
    return mod.check(ws)


def cleanup(suite, ws):
    for rel in suite["build"].get("cleanup", []):
        rmtree(ws / rel)


# ---------------------------------------------------------------- agenti

def clean_env():
    """Prostredi bez promennych Claude Code / Anthropic z nadrazene session."""
    return {k: v for k, v in os.environ.items() if not k.upper().startswith(("CLAUDE", "ANTHROPIC"))}


def find_opencode():
    exe = shutil.which("opencode")
    if exe:
        return exe
    hits = glob.glob(os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\SST.opencode*\opencode.exe"))
    if not hits:
        raise RuntimeError("opencode nenalezen")
    return hits[0]


def run_claude(suite, cfg, spark, prompt, ws, timeout):
    env = clean_env()
    if cfg.get("spark"):
        key = user_env(spark["api_key_env"])
        m = cfg["model"]
        env.update({
            "ANTHROPIC_BASE_URL": spark["base_url"], "ANTHROPIC_AUTH_TOKEN": key or "",
            "ANTHROPIC_MODEL": m, "ANTHROPIC_DEFAULT_HAIKU_MODEL": m, "ANTHROPIC_DEFAULT_SONNET_MODEL": m,
            "ANTHROPIC_DEFAULT_OPUS_MODEL": m, "CLAUDE_CODE_SUBAGENT_MODEL": m,
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        })
        # Claude Code si jinak rekne o 32000 vystupnich tokenu; u modelu s kontextem 32k
        # vLLM pozadavek odmitne jeste pred prvni odpovedi (ContextWindowExceeded).
        out_limit = spark["models"].get(m, {}).get("output")
        if out_limit:
            env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] = str(out_limit)
        # Uroven premysleni: Claude Code 2.1.220 posila thinking {"type": "adaptive"} a output_config
        # {"effort": ...}, vychozi "high" (zachyceno lokalne 27. 9.), MAX_THINKING_TOKENS ignoruje. Uroven
        # nastavuje prepinac --effort. LiteLLM effort prevadi na gpt-oss (low ~1 000, medium ~1 300,
        # high ~5 500 znaku uvah).
    # build ESP-IDF muze trvat dele nez vychozi 2 min limit nastroje Bash
    env.update({"BASH_DEFAULT_TIMEOUT_MS": "600000", "BASH_MAX_TIMEOUT_MS": "900000"})
    cmd = [shutil.which("claude"), "-p", "--model", cfg["model"], "--output-format", "stream-json", "--verbose",
           "--setting-sources", "project", "--no-session-persistence", "--permission-mode", "acceptEdits",
           "--allowedTools", *claude_allowed_tools(suite), "--disallowedTools", "WebFetch", "WebSearch"]
    effort = spark["models"].get(cfg["model"], {}).get("reasoning") if cfg.get("spark") else None
    if effort:
        cmd += ["--effort", effort]
    rc, out, err, timed_out, secs = run_process(cmd, ws, env, timeout, stdin_text=prompt)

    rec = {"agent_exit": rc, "timed_out": timed_out, "wall_s": round(secs, 1), "tool_calls": 0,
           "build_attempts": 0, "ran_build": False, "permission_denials": 0, "turns": None,
           "tokens_in": 0, "tokens_out": 0, "cost_usd": None, "models_used": [], "final_text": "",
           "agent_error": None}
    result, build_ids = None, set()
    for line in out.splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        content = (ev.get("message") or {}).get("content")
        blocks = content if isinstance(content, list) else []
        if ev.get("type") == "assistant":
            for block in blocks:
                if block.get("type") == "tool_use":
                    rec["tool_calls"] += 1
                    if "build.sh" in json.dumps(block.get("input", {})):
                        rec["build_attempts"] += 1
                        build_ids.add(block.get("id"))
        elif ev.get("type") == "user":
            for block in blocks:
                if block.get("type") == "tool_result" and block.get("tool_use_id") in build_ids:
                    if re.search(r"BUILD (OK|FAILED)", json.dumps(block.get("content"), ensure_ascii=False)):
                        rec["ran_build"] = True  # build opravdu probehl, ne jen pokus
        elif ev.get("type") == "result":
            result = ev
    if result:
        rec["turns"] = result.get("num_turns")
        rec["cost_usd"] = result.get("total_cost_usd")
        rec["final_text"] = (result.get("result") or "")[:3000]
        rec["permission_denials"] = len(result.get("permission_denials") or [])
        if result.get("is_error"):
            rec["agent_error"] = (result.get("result") or result.get("subtype") or "is_error")[:300]
        for model, u in (result.get("modelUsage") or {}).items():
            rec["models_used"].append(model)
            rec["tokens_in"] += (u.get("inputTokens", 0) + u.get("cacheReadInputTokens", 0)
                                 + u.get("cacheCreationInputTokens", 0))
            rec["tokens_out"] += u.get("outputTokens", 0)
    else:
        rec["agent_error"] = "timeout" if timed_out else f"bez vysledku (exit {rc})"
    if cfg.get("spark"):
        rec["cost_usd"] = 0.0  # lokalni model; LiteLLM pocita ceny Claude modelu, ne Sparku
    return rec, out, err


def run_opencode(suite, cfg, spark, prompt, ws, timeout):
    env = clean_env()
    env[spark["api_key_env"]] = user_env(spark["api_key_env"]) or ""
    cmd = [find_opencode(), "run", "-m", f"spark/{cfg['model']}", "--format", "json", "--dir", str(ws), prompt]
    rc, out, err, timed_out, secs = run_process(cmd, ws, env, timeout)

    rec = {"agent_exit": rc, "timed_out": timed_out, "wall_s": round(secs, 1), "tool_calls": 0,
           "build_attempts": 0, "ran_build": False, "permission_denials": 0, "turns": 0,
           "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0,
           "models_used": [f"spark/{cfg['model']}"], "final_text": "", "agent_error": None}
    texts = []
    for line in out.splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        part = ev.get("part") or {}
        if ev.get("type") == "tool_use":
            rec["tool_calls"] += 1
            state = part.get("state") or {}
            if "build.sh" in json.dumps(state.get("input", {})):
                rec["build_attempts"] += 1
                if re.search(r"BUILD (OK|FAILED)", str(state.get("output", ""))):
                    rec["ran_build"] = True
            if state.get("status") == "error" and "permission" in str(state.get("error", "")).lower():
                rec["permission_denials"] += 1
        elif ev.get("type") == "step_finish":
            rec["turns"] += 1
            t = part.get("tokens") or {}
            rec["tokens_in"] += t.get("input", 0) + (t.get("cache") or {}).get("read", 0)
            rec["tokens_out"] += t.get("output", 0) + t.get("reasoning", 0)
        elif ev.get("type") == "text":
            texts.append(part.get("text", ""))
        elif ev.get("type") == "error":
            rec["agent_error"] = ((ev.get("error") or {}).get("data") or {}).get("message") or "error"
    rec["final_text"] = (texts[-1] if texts else "")[:3000]
    if timed_out:
        rec["agent_error"] = "timeout"
    elif rc != 0 and not rec["agent_error"]:
        rec["agent_error"] = f"exit {rc}"
    return rec, out, err


# ---------------------------------------------------------------- jeden beh

def workspace_path(suite, run_id):
    """S build.persist jedna pevna slozka pro vsechny behy (bezi po sobe), jinak slozka na beh."""
    return sp(suite, "work_dir") / ("run" if suite["build"].get("persist") else run_id)


def one_run(suite, spark, cfg, bug, rep, out_dir):
    run_id = f"{bug}-{cfg['name']}-r{rep}"
    ws = workspace_path(suite, run_id)
    rdir = out_dir / "runs" / run_id
    rdir.mkdir(parents=True, exist_ok=True)

    make_workspace(suite, spark, bug, ws, cfg["harness"])
    task = (sp(suite, "bugs_dir") / bug / "task.md").read_text(encoding="utf-8").strip()
    prompt = (suite["_root"] / suite["prompt_template"]).read_text(encoding="utf-8").replace("{task}", task)
    (rdir / "prompt.txt").write_text(prompt, encoding="utf-8")

    started = datetime.now().isoformat(timespec="seconds")
    runner = run_claude if cfg["harness"] == "claude-code" else run_opencode
    rec, out, err = runner(suite, cfg, spark, prompt, ws, suite.get("run_timeout_s", 900))
    (rdir / "agent.jsonl").write_text(out, encoding="utf-8")
    (rdir / "agent.stderr.txt").write_text(err, encoding="utf-8")

    guard = run_guard(suite, ws)
    diff, added, removed, files = workspace_diff(suite, ws)
    (rdir / "diff.patch").write_text(diff, encoding="utf-8", newline="\n")  # LF, jinak git apply patch odmitne
    install_harness_files(suite, ws)  # build vzdy s puvodnim skriptem, i kdyby ho model zmenil
    b = build(suite, ws)
    (rdir / "build.txt").write_text(b.pop("build_output"), encoding="utf-8")
    fixed, detail = run_check(suite, bug, ws)  # kontroluje zdrojaky, bezi i pri neuspesnem buildu
    cleanup(suite, ws)

    meta = load_json(sp(suite, "bugs_dir") / bug / "meta.json")
    rec.update({
        "run_id": run_id, "bug": bug, "bug_title": meta.get("title", bug), "config": cfg["name"],
        "label": cfg["label"], "harness": cfg["harness"], "model": cfg["model"], "rep": rep,
        "started": started, **b, "fixed": fixed, "check_detail": detail,
        "guard_ok": guard["ok"], "guard_violations": guard["violations"],
        "files_changed": files, "lines_added": added, "lines_removed": removed,
        "reference_lines": meta.get("reference_lines"), "diff_sig": diff_signature(diff),
    })
    rec["success"] = bool(rec["build_ok"] and rec["fixed"] and rec["guard_ok"])
    return rec


# ---------------------------------------------------------------- overeni sady

def verify(suite, spark, out_dir):
    bugs = list_bugs(suite)
    rows = []

    def bug_meta(bug):
        return load_json(sp(suite, "bugs_dir") / bug / "meta.json")

    def case(name, bug, expect_fixed_bug):
        ws = workspace_path(suite, f"verify-{name}")
        make_workspace(suite, spark, bug, ws)
        b = build(suite, ws)
        checks = {x: run_check(suite, x, ws)[0] for x in bugs}
        guard = run_guard(suite, ws)
        # baseline: vsechny kontroly projdou (krome uloh, ktere po baseline chteji novou funkci:
        # meta baseline_passes=false); kopie s chybou: jeji vlastni kontrola selze
        # (ostatni kontroly muze vnesena chyba ovlivnit, napr. H1 odstrani vTaskDelay, na kterem stavi B2)
        expected = ({x: True for x in bugs if bug_meta(x).get("baseline_passes", True)}
                    if bug is None else {bug: False})
        ok = b["build_ok"] and all(checks[x] == v for x, v in expected.items()) and guard["ok"]
        rows.append({"case": name, "build_ok": b["build_ok"], "warnings": b["warnings"], "checks": checks,
                     "expected_checks": expected, "guard_ok": guard["ok"], "violations": guard["violations"],
                     "pass": ok})
        cleanup(suite, ws)
        print(f"  {name:10s} build={'OK' if b['build_ok'] else 'FAIL'} warn={b['warnings']} "
              f"checks={checks} guard={'OK' if guard['ok'] else guard['violations']} -> {'PASS' if ok else 'FAIL'}")
        return ws

    def variant(bug, patch, expect_success):
        """Vzorova oprava (fixes/) musi uspet, chybna (wrong/) ne: overuje samotnou kontrolu."""
        ws = workspace_path(suite, f"verify-{bug}-var")
        make_workspace(suite, spark, bug, ws)
        git(ws, "apply", "--whitespace=nowarn", str(patch))
        fixed, detail = run_check(suite, bug, ws)
        guard = run_guard(suite, ws)
        b = build(suite, ws) if fixed and guard["ok"] else {"build_ok": None}
        success = bool(fixed and guard["ok"] and b["build_ok"])
        ok = success == expect_success
        name = f"{patch.parent.name}/{patch.stem}"
        rows.append({"case": f"{bug}:{name}", "expect_success": expect_success, "success": success,
                     "check": detail, "guard_ok": guard["ok"], "violations": guard["violations"],
                     "build_ok": b["build_ok"], "pass": ok})
        cleanup(suite, ws)
        print(f"    {name:32s} kontrola={'OK' if fixed else 'FAIL'} ({detail}) guard={'OK' if guard['ok'] else 'PORUSEN'}"
              f" build={b['build_ok']} -> {'PASS' if ok else 'FAIL'}")

    print("baseline:")
    base_ws = case("baseline", None, None)
    for bug in bugs:
        print(f"{bug}:")
        case(bug, bug, bug)
        for kind, expect in (("fixes", True), ("wrong", False)):
            for patch in sorted((sp(suite, "bugs_dir") / bug / kind).glob("*.patch")):
                variant(bug, patch, expect)

    # negativni testy guardu: zasah do OTA musi byt odhalen
    negatives = {
        "ota.c": ("main/ota.c", "#define OTA_CONFIRM_TIMEOUT_S 120", "#define OTA_CONFIRM_TIMEOUT_S 12"),
        "ota_confirm": ("main/telemetry.c", "            ota_confirm();\n", ""),
        "PowerMode": ("main/telemetry.c", '"PowerMode", "ACTIVE"', '"PowerMode", "SLEEP"'),
        "motor": ("main/main.c", "gpio_set_level(MOTOR_LEFT_PWM, 0);", "gpio_set_level(MOTOR_LEFT_PWM, 1);"),
        # obejiti pojistky novym souborem (27. 9. gpt-oss: po 15 s sam volal ota_confirm())
        "ota-novy-soubor": ("main/early_confirm.c", None,
                            '#include "ota.h"\nvoid early_confirm(void) { ota_confirm(); }\n'),
    }
    for name, (rel, old, new) in negatives.items():
        ws = sp(suite, "work_dir") / "verify-neg"
        make_workspace(suite, spark, None, ws)
        p = ws / rel
        if old is None:  # novy soubor
            p.write_text(new, encoding="utf-8", newline="\n")
        else:
            text = p.read_text(encoding="utf-8")
            assert old in text, f"{rel}: '{old}' nenalezeno"
            p.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")
        guard = run_guard(suite, ws)
        ok = not guard["ok"]
        rows.append({"case": f"neg-{name}", "guard_ok": guard["ok"], "violations": guard["violations"], "pass": ok})
        print(f"  neg-{name:10s} guard={'OK' if guard['ok'] else 'ODHALIL'} -> {'PASS' if ok else 'FAIL'}")
    rmtree(sp(suite, "work_dir") / "verify-neg")

    (out_dir / "verify.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    all_ok = all(r["pass"] for r in rows)
    print("OVERENI:", "VSE PROSLO" if all_ok else "NEPROSLO")
    return all_ok


# ---------------------------------------------------------------- main

def tool_versions():
    v = {}
    for name, cmd in (("claude", [shutil.which("claude"), "--version"]), ("opencode", [find_opencode(), "--version"])):
        try:
            v[name] = subprocess.run(cmd, capture_output=True, text=True, timeout=60).stdout.strip()
        except Exception as ex:  # noqa: BLE001
            v[name] = f"? ({ex})"
    return v


def main():
    ap = argparse.ArgumentParser(description="Benchmark oprav chyb (obecny runner)")
    ap.add_argument("--suite", default=str(BENCH_DIR.parent / "suite.json"))
    ap.add_argument("--configs", default=str(BENCH_DIR / "configs.json"))
    ap.add_argument("--bugs", help="carkou oddelene ID chyb (vychozi vsechny)")
    ap.add_argument("--only", help="carkou oddelene nazvy konfiguraci (vychozi vsechny enabled)")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--out", help="vystupni slozka (vychozi results/<cas>)")
    ap.add_argument("--resume", help="pokracovat v existujici vystupni slozce")
    ap.add_argument("--verify", action="store_true", help="jen overit baseline, chyby a guard")
    ap.add_argument("--timeout", type=int, help="limit na jeden beh v s (vychozi run_timeout_s ze suite.json)")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # konzole na Windows je cp1250

    suite = load_suite(args.suite)
    if args.timeout:
        suite["run_timeout_s"] = args.timeout
    cfgfile = load_json(args.configs)
    spark = cfgfile["spark_provider"]
    # adresa Sparku z proměnné prostředí má přednost (sdílená kopie ji v configs.json nemá)
    spark["base_url"] = (user_env("SPARK_URL") or spark.get("base_url") or "").rstrip("/").removesuffix("/v1")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = Path(args.resume or args.out or sp(suite, "results_dir") / (("verify-" if args.verify else "") + stamp))
    out_dir.mkdir(parents=True, exist_ok=True)
    sp(suite, "work_dir").mkdir(parents=True, exist_ok=True)

    if args.verify:
        sys.exit(0 if verify(suite, spark, out_dir) else 1)

    leaks = context_leaks(workspace_path(suite, "x"))
    if leaks:
        sys.exit("STOP: agent by si nacetl cizi instrukce (kontaminace zadani):\n  " + "\n  ".join(map(str, leaks)) +
                 "\nPresun pracovni slozku (suite.json work_dir) mimo strom s temito soubory, nebo je odstran.")

    bugs = args.bugs.split(",") if args.bugs else list_bugs(suite)
    configs = [c for c in cfgfile["configs"]
               if (c["name"] in args.only.split(",") if args.only else c.get("enabled", True))]

    runs_file = out_dir / "runs.jsonl"
    done = set()
    if runs_file.exists():
        done = {json.loads(ln)["run_id"] for ln in runs_file.read_text(encoding="utf-8").splitlines() if ln.strip()}

    meta_file = out_dir / "meta.json"
    if not meta_file.exists():
        meta_file.write_text(json.dumps({
            "suite": suite["name"], "suite_description": suite.get("description", ""),
            "started": datetime.now().isoformat(timespec="seconds"), "bugs": bugs, "reps": args.reps,
            "configs": configs, "spark_models": spark["models"], "run_timeout_s": suite.get("run_timeout_s", 900),
            "tools": tool_versions(),
            "prompt_template": (suite["_root"] / suite["prompt_template"]).read_text(encoding="utf-8"),
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    # poradi: opakovani -> chyba -> konfigurace, at se konfigurace strida v case (fer vuci zatezi a limitum)
    plan = [(rep, bug, cfg) for rep in range(1, args.reps + 1) for bug in bugs for cfg in configs]
    todo = [p for p in plan if f"{p[1]}-{p[2]['name']}-r{p[0]}" not in done]
    print(f"Behu celkem {len(plan)}, hotovo {len(plan) - len(todo)}, zbyva {len(todo)}. Vystup: {out_dir}")

    for i, (rep, bug, cfg) in enumerate(todo, 1):
        t0 = time.time()
        print(f"[{i}/{len(todo)}] {bug} {cfg['name']} r{rep} ...", flush=True)
        try:
            rec = one_run(suite, spark, cfg, bug, rep, out_dir)
        except Exception as ex:  # noqa: BLE001
            rec = {"run_id": f"{bug}-{cfg['name']}-r{rep}", "bug": bug, "config": cfg["name"],
                   "label": cfg["label"], "harness": cfg["harness"], "model": cfg["model"], "rep": rep,
                   "success": False, "agent_error": f"chyba runneru: {ex}"}
        with runs_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"    -> {'USPECH' if rec.get('success') else 'neuspech'}"
              f" | build={rec.get('build_ok')} oprava={rec.get('fixed')} guard={rec.get('guard_ok')}"
              f" | {rec.get('wall_s')} s, tokeny {rec.get('tokens_in')}/{rec.get('tokens_out')}"
              f"{', chyba: ' + str(rec.get('agent_error')) if rec.get('agent_error') else ''}"
              f" ({time.time() - t0:.0f} s vcetne buildu)", flush=True)

    print(f"Hotovo. Vysledky: {runs_file}")


if __name__ == "__main__":
    main()
