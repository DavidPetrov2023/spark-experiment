"""Prehodnoti ulozene behy aktualnimi kontrolami a guardem (po oprave chyby v check.py nebo guardu).

Model se znovu nespousti: z runs/<beh>/diff.patch se na ciste kopii (baseline + bug.patch)
obnovi kod, ktery model odevzdal, a znovu se pusti check.py dane ulohy a guard. Build se
neopakuje (kod je stejny, plati puvodni build_ok). Zmenene zaznamy dostanou pole "rescored"
s puvodnimi hodnotami a datem, puvodni runs.jsonl se zazalohuje jako runs.jsonl.pred-rescore.

    python bench/rescore.py results/<slozka>            # jen vypise, co by se zmenilo
    python bench/rescore.py results/<slozka> --write    # zmeny zapise
"""

import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import run_bench as rb


def restore(suite, bug, diff, ws):
    shutil.copytree(rb.sp(suite, "baseline"), ws)
    rb.git(ws, "init", "-q")
    patch = rb.sp(suite, "bugs_dir") / bug / "bug.patch"
    if patch.exists():
        rb.git(ws, "apply", "--whitespace=nowarn", str(patch))
    rb.install_harness_files(suite, ws)
    rb.git(ws, "add", "-A")
    rb.git(ws, "-c", "user.name=rescore", "-c", "user.email=rescore@local", "commit", "-qm", "start")
    if diff.stat().st_size:
        # starsi behy (25.-26. 9.) maji diff s CRLF, ktery git apply odmitne: prevest na LF
        lf = ws.parent / "diff-lf.patch"
        lf.write_bytes(diff.read_bytes().replace(b"\r\n", b"\n"))
        subprocess.run(["git", "apply", "--whitespace=nowarn", str(lf)], cwd=ws, check=True,
                       capture_output=True)


def main():
    out_dir = Path(sys.argv[1])
    write = "--write" in sys.argv
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    suite = rb.load_suite(str(rb.BENCH_DIR.parent / "suite.json"))
    runs_file = out_dir / "runs.jsonl"
    recs = [json.loads(ln) for ln in runs_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
    changed = 0
    for rec in recs:
        diff = out_dir / "runs" / rec["run_id"] / "diff.patch"
        if not diff.exists() or (rec.get("agent_error") or "").startswith("chyba runneru"):
            continue
        with tempfile.TemporaryDirectory() as d:
            ws = Path(d) / "ws"
            restore(suite, rec["bug"], diff, ws)
            fixed, detail = rb.run_check(suite, rec["bug"], ws)
            guard = rb.run_guard(suite, ws)
        success = bool(rec.get("build_ok") and fixed and guard["ok"])
        if (fixed, guard["ok"], success) != (rec.get("fixed"), rec.get("guard_ok"), rec.get("success")):
            changed += 1
            print(f"{rec['run_id']}: uspech {rec.get('success')} -> {success} | {rec.get('check_detail')} -> {detail}")
            rec["rescored"] = {"date": datetime.now().isoformat(timespec="seconds"), "fixed": rec.get("fixed"),
                               "check_detail": rec.get("check_detail"), "guard_ok": rec.get("guard_ok"),
                               "guard_violations": rec.get("guard_violations"), "success": rec.get("success")}
            rec.update({"fixed": fixed, "check_detail": detail, "guard_ok": guard["ok"],
                        "guard_violations": guard["violations"], "success": success})
    print(f"Prehodnoceno {len(recs)} behu, zmenenych {changed}.")
    if write and changed:
        shutil.copy(runs_file, runs_file.with_name("runs.jsonl.pred-rescore"))
        runs_file.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs), encoding="utf-8")
        print(f"Zapsano do {runs_file} (zaloha runs.jsonl.pred-rescore).")


if __name__ == "__main__":
    main()
