"""Test kvality review na chybách z benchmarku (odpoledne 28. 9.).

Každá vnesená chyba z esp-bench (B1–B4, H1–H3, X1–X3; X4 je nová funkce bez chyby) se nasimuluje jako commit:
baseline -> commit „Úprava firmwaru“ s chybou. Review má změnu projít a chybu najít.
Volitelně i negativní test: commit se vzorovou opravou (fixes/1-*) nemá dostat nález vysoké závažnosti.

    python review/test_review.py --backend spark                (gpt-oss-120b na high)
    python review/test_review.py --backend claude --model sonnet
    python review/test_review.py --bugs B4,X3 --dry-run         (jen připraví texty, nic neodešle)
    python review/test_review.py --negativni                    (i plané poplachy na vzorových opravách)
"""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import spark_review as sr  # noqa: E402

BENCH = HERE.parent / "esp-bench"
EXPECT = json.loads((HERE / "ocekavane.json").read_text(encoding="utf-8"))
SERIOUS = {"kritická", "vysoká"}


def plain(s):
    return "".join(c for c in unicodedata.normalize("NFKD", str(s).lower()) if not unicodedata.combining(c))


def run(cmd, cwd):
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True)


def make_repo(d, bug, fix_patch=None):
    """Dočasný repozitář: baseline, pak commit s chybou (případně ještě commit se vzorovou opravou)."""
    repo = Path(d) / "ESPTest"
    shutil.copytree(BENCH / "baseline", repo)
    run(["git", "init", "-q"], repo)
    run(["git", "-c", "user.name=test", "-c", "user.email=test@local", "add", "-A"], repo)
    run(["git", "-c", "user.name=test", "-c", "user.email=test@local", "commit", "-qm", "Firmware ESPTest"], repo)
    run(["git", "apply", str(BENCH / "bugs" / bug / "bug.patch")], repo)
    run(["git", "-c", "user.name=test", "-c", "user.email=test@local", "commit", "-qam", "Úprava firmwaru"], repo)
    if fix_patch:
        run(["git", "apply", str(fix_patch)], repo)
        run(["git", "add", "-A"], repo)
        run(["git", "-c", "user.name=test", "-c", "user.email=test@local", "commit", "-qm", "Oprava"], repo)
    return repo


def score(bug, found):
    """(zasažených očekávaných chyb, očekávaných celkem)."""
    exp = EXPECT[bug]
    hit = 0
    for e in exp:
        for f in found:
            text = plain(f.get("popis", "")) + " " + plain(f.get("funkce", ""))
            file_ok = not e["soubor"] or plain(e["soubor"]).split("/")[-1] in plain(f.get("soubor", ""))
            if file_ok and any(plain(w) in text for w in e["slova"]):
                hit += 1
                break
    return hit, len(exp)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["spark", "claude"], default="spark")
    ap.add_argument("--model")
    ap.add_argument("--effort", default="high")
    ap.add_argument("--bugs", help="čárkou oddělené ID (výchozí všechny kromě X4)")
    ap.add_argument("--negativni", action="store_true", help="i vzorové opravy (plané poplachy)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--timeout", type=int, default=600, help="limit na jeden commit v s (výchozí 10 min)")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    bugs = a.bugs.split(",") if a.bugs else [b for b in EXPECT if not b.startswith("_")]
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    out = HERE / "vystupy" / f"test-{stamp}-{a.backend}"
    rows = []
    for bug in bugs:
        with tempfile.TemporaryDirectory(prefix="review-test-") as d:
            repo = make_repo(d, bug)
            t0 = time.time()
            try:
                path, found = sr.review(repo, sr.git(repo, "rev-parse", "HEAD~1").strip(),
                                        sr.git(repo, "rev-parse", "HEAD").strip(), "poslední commit", a.backend, a.model,
                                        a.effort, rules_path=HERE / "pravidla-vychozi.md", out_dir=out,
                                        timeout=a.timeout, dry_run=a.dry_run, label=f"{bug}-chyba")
                err = None
            except (Exception, SystemExit) as ex:  # noqa: BLE001 - jeden neúspěch nesmí shodit celý test
                path, found, err = None, [], f"{type(ex).__name__}: {str(ex)[:200]}"
                print(f"  {bug}: CHYBA {err}")
            hit, total = score(bug, found)
            rows.append({"test": f"{bug} chyba", "nalezu": len(found), "zasah": f"{hit}/{total}",
                         "ok": hit == total, "sekund": round(time.time() - t0), "chyba": err,
                         "zprava": str(path) if path else None})
            print(f"  {bug}: nalezů {len(found)}, správně {hit}/{total}, {time.time() - t0:.0f} s")
        if a.negativni:
            fix = sorted((BENCH / "bugs" / bug / "fixes").glob("1-*.patch"))
            if fix:
                with tempfile.TemporaryDirectory(prefix="review-test-") as d:
                    repo = make_repo(d, bug, fix[0])
                    path, found = sr.review(repo, sr.git(repo, "rev-parse", "HEAD~1").strip(),
                                            sr.git(repo, "rev-parse", "HEAD").strip(), "vzorová oprava", a.backend,
                                            a.model, a.effort, rules_path=HERE / "pravidla-vychozi.md", out_dir=out,
                                            dry_run=a.dry_run, label=f"{bug}-oprava")
                    false = [f for f in found if f.get("zavaznost") in SERIOUS]
                    rows.append({"test": f"{bug} vzorová oprava", "nalezu": len(found), "plane_vazne": len(false),
                                 "ok": not false, "zprava": str(path) if path else None})
                    print(f"  {bug} oprava: nalezů {len(found)}, z toho vážných (planý poplach) {len(false)}")
    if not a.dry_run:
        out.mkdir(parents=True, exist_ok=True)
        (out / "souhrn.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        ok = sum(r["ok"] for r in rows if "chyba" in r["test"])
        n = sum(1 for r in rows if "chyba" in r["test"])
        print(f"\nNalezené chyby: {ok}/{n}. Souhrn: {out / 'souhrn.json'}")


if __name__ == "__main__":
    main()
