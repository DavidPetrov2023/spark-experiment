"""PDF report z vysledku benchmarku (runs.jsonl + meta.json).

    .venv\\Scripts\\python bench\\report.py results\\<cas>

Metriky (na konfiguraci):
  uspesnost    podil behu, kde build prosel, chyba je opravena a guard nenasel poruseni
  spolehlivost podil chyb, ktere konfigurace opravila ve VSECH opakovanich (pass^k)
  shoda oprav  jak casto opakovani vedou ke stejne oprave (otisk diffu), prumer pres chyby
  disciplina   podil behu bez poruseni guardu a bez zbytecne velke zmeny
  index        100 x (0.5 uspesnost + 0.3 spolehlivost + 0.2 disciplina)
"""

import json
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.enums import TA_LEFT  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.pdfbase import pdfmetrics  # noqa: E402
from reportlab.pdfbase.ttfonts import TTFont  # noqa: E402
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, Preformatted,  # noqa: E402
                                SimpleDocTemplate, Spacer, Table, TableStyle)

WEIGHTS = {"uspesnost": 0.5, "spolehlivost": 0.3, "disciplina": 0.2}

# Paleta: referencni instance (dataviz/references/palette.md), svetly rezim pro tisk
SURFACE = "#fcfcfb"
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, AXIS = "#e1e0d9", "#c3c2b7"
SERIES1 = "#2a78d6"
SEQ = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95"]  # sekvencni modra 100..600

FONT_DIR = Path("C:/Windows/Fonts")
pdfmetrics.registerFont(TTFont("UI", str(FONT_DIR / "segoeui.ttf")))
pdfmetrics.registerFont(TTFont("UI-Bold", str(FONT_DIR / "segoeuib.ttf")))
pdfmetrics.registerFont(TTFont("Mono", str(FONT_DIR / "consola.ttf")))
pdfmetrics.registerFontFamily("UI", normal="UI", bold="UI-Bold", italic="UI", boldItalic="UI-Bold")
for f in ("segoeui.ttf", "segoeuib.ttf"):
    font_manager.fontManager.addfont(str(FONT_DIR / f))
plt.rcParams.update({
    "font.family": "Segoe UI", "font.size": 9, "text.color": INK, "axes.labelcolor": INK2,
    "xtick.color": MUTED, "ytick.color": INK2, "axes.edgecolor": AXIS, "axes.facecolor": SURFACE,
    "figure.facecolor": SURFACE, "savefig.facecolor": SURFACE,
})

ST = {
    "h1": ParagraphStyle("h1", fontName="UI-Bold", fontSize=18, leading=22, textColor=INK, spaceAfter=4),
    "h2": ParagraphStyle("h2", fontName="UI-Bold", fontSize=13, leading=17, textColor=INK, spaceBefore=10, spaceAfter=4),
    "h3": ParagraphStyle("h3", fontName="UI-Bold", fontSize=10.5, leading=14, textColor=INK, spaceBefore=6, spaceAfter=2),
    "p": ParagraphStyle("p", fontName="UI", fontSize=9, leading=12.5, textColor=INK, alignment=TA_LEFT),
    "small": ParagraphStyle("small", fontName="UI", fontSize=7.5, leading=10, textColor=INK2),
    "cell": ParagraphStyle("cell", fontName="UI", fontSize=7.5, leading=9.5, textColor=INK),
    "code": ParagraphStyle("code", fontName="Mono", fontSize=6.8, leading=8.4, textColor=INK),
}


# ---------------------------------------------------------------- data

def load(out_dir):
    runs = [json.loads(ln) for ln in (out_dir / "runs.jsonl").read_text(encoding="utf-8").splitlines() if ln.strip()]
    meta = json.loads((out_dir / "meta.json").read_text(encoding="utf-8"))
    return runs, meta


def over_edit(r):
    ref = r.get("reference_lines") or 2
    return (r.get("lines_added", 0) + r.get("lines_removed", 0)) > max(10, 5 * ref)


def metrics(runs, meta):
    order = [c["name"] for c in meta["configs"]]
    by_cfg = defaultdict(list)
    for r in runs:
        by_cfg[r["config"]].append(r)
    reps = meta.get("reps", 1)
    rows = []
    for name in order:
        rs = by_cfg.get(name, [])
        if not rs:
            continue
        by_bug = defaultdict(list)
        for r in rs:
            by_bug[r["bug"]].append(r)
        n = len(rs)
        succ = sum(r.get("success", False) for r in rs) / n
        reliab = sum(all(x.get("success") for x in b) and len(b) >= reps for b in by_bug.values()) / len(by_bug)
        consist = (statistics.mean(Counter(x.get("diff_sig") for x in b).most_common(1)[0][1] / len(b)
                                   for b in by_bug.values()) if reps > 1 else None)
        # beh bez jakekoli zmeny neni "disciplinovany", jen nic neudelal
        disc = sum(r.get("guard_ok", False) and not over_edit(r)
                   and (r.get("lines_added", 0) + r.get("lines_removed", 0)) > 0 for r in rs) / n
        times = [r["wall_s"] for r in rs if r.get("wall_s") is not None]
        tok = [r.get("tokens_in", 0) + r.get("tokens_out", 0) for r in rs]
        cost = sum(r.get("cost_usd") or 0 for r in rs)
        idx = 100 * (WEIGHTS["uspesnost"] * succ + WEIGHTS["spolehlivost"] * reliab + WEIGHTS["disciplina"] * disc)
        rows.append({
            "config": name, "label": rs[0].get("label", name), "n": n, "index": idx, "uspesnost": succ,
            "spolehlivost": reliab, "shoda": consist, "disciplina": disc,
            "ran_build": sum(r.get("ran_build", False) for r in rs) / n,
            "guard_viol": sum(not r.get("guard_ok", True) for r in rs),
            "errors": sum(bool(r.get("agent_error")) for r in rs),
            "t_med": statistics.median(times) if times else None, "t_min": min(times) if times else None,
            "t_max": max(times) if times else None,
            "t_cv": (statistics.pstdev(times) / statistics.mean(times)) if len(times) > 1 and statistics.mean(times) else None,
            "tok_med": statistics.median(tok) if tok else 0, "cost": cost,
            "tools_med": statistics.median([r.get("tool_calls") or 0 for r in rs]),
            "turns_med": statistics.median([r.get("turns") or 0 for r in rs]),
            "denials": sum(r.get("permission_denials") or 0 for r in rs),
            "models_used": sorted({m for r in rs for m in r.get("models_used", [])}),
        })
    return rows


# ---------------------------------------------------------------- grafy

def _style_axes(ax):
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(AXIS)
    ax.grid(axis="x", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.tick_params(axis="y", length=0)


def chart_index(rows, path):
    rs = sorted(rows, key=lambda r: (r["index"], -(r["t_med"] or 1e9)))  # pri shode rychlejsi nahore
    fig, ax = plt.subplots(figsize=(7.2, 0.42 * len(rs) + 0.8), dpi=200)
    y = range(len(rs))
    ax.barh(y, [r["index"] for r in rs], height=0.55, color=SERIES1)
    for i, r in enumerate(rs):
        ax.text(r["index"] + 1.2, i, f"{r['index']:.0f}", va="center", fontsize=8.5, color=INK)
    ax.set_yticks(list(y), [r["label"] for r in rs])
    ax.set_xlim(0, 108)
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_xlabel("Index kvality (0–100)")
    _style_axes(ax)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def chart_times(runs, rows, path):
    labels = [r["label"] for r in rows]
    cfgs = [r["config"] for r in rows]
    fig, ax = plt.subplots(figsize=(7.2, 0.42 * len(rows) + 1.0), dpi=200)
    for i, c in enumerate(cfgs):
        rs = [r for r in runs if r["config"] == c and r.get("wall_s") is not None]
        ok = [r["wall_s"] for r in rs if r.get("success")]
        ko = [r["wall_s"] for r in rs if not r.get("success")]
        yi = len(cfgs) - 1 - i
        ax.scatter(ok, [yi] * len(ok), s=34, color=SERIES1, edgecolors=SURFACE, linewidths=1.2, zorder=3)
        ax.scatter(ko, [yi] * len(ko), s=34, facecolors=SURFACE, edgecolors=SERIES1, linewidths=1.3, zorder=3)
        if rows[i]["t_med"] is not None:
            ax.plot([rows[i]["t_med"]] * 2, [yi - 0.28, yi + 0.28], color=INK, linewidth=1.6, zorder=4)
    ax.set_yticks(range(len(cfgs)), list(reversed(labels)))
    ax.set_ylim(-0.7, len(cfgs) - 0.3)
    ax.set_xlim(left=0)
    ax.set_xlabel("Čas modelu na opravu [s] (bez závěrečného buildu benchmarku)")
    _style_axes(ax)
    from matplotlib.lines import Line2D
    ax.legend(handles=[
        Line2D([], [], marker="o", linestyle="", color=SERIES1, markeredgecolor=SURFACE, markersize=6, label="úspěch"),
        Line2D([], [], marker="o", linestyle="", markerfacecolor=SURFACE, markeredgecolor=SERIES1, markersize=6, label="neúspěch"),
        Line2D([], [], color=INK, linewidth=1.6, label="medián"),
    ], loc="lower right", frameon=False, fontsize=8, ncol=3, bbox_to_anchor=(1, 1.0))
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


# ---------------------------------------------------------------- tabulky

def pct(x):
    return "–" if x is None else f"{100 * x:.0f} %"


def secs(x):
    return "–" if x is None else (f"{x:.0f} s" if x < 120 else f"{x / 60:.1f} min")


def table(data, widths, header_rows=1, extra=()):
    t = Table(data, colWidths=widths, repeatRows=header_rows)
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "UI", 7.5),
        ("FONT", (0, 0), (-1, header_rows - 1), "UI-Bold", 7.5),
        ("TEXTCOLOR", (0, 0), (-1, -1), INK),
        ("LINEBELOW", (0, header_rows - 1), (-1, header_rows - 1), 0.6, AXIS),
        ("LINEBELOW", (0, header_rows), (-1, -1), 0.3, GRID),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        *extra,
    ]))
    return t


def summary_table(rows):
    hs = ParagraphStyle("hr", parent=ST["cell"], fontName="UI-Bold", fontSize=7, leading=8.5, alignment=2)
    head = [Paragraph("Konfigurace", ParagraphStyle("hl", parent=hs, alignment=0))] + [
        Paragraph(h, hs) for h in ("Index", "Úspěšnost", "Spolehlivost", "Shoda oprav", "Disciplína",
                                   "Ověřil build", "Čas medián", "Čas min–max", "Tokeny medián", "Cena celkem")]
    data = [head]
    for r in sorted(rows, key=lambda r: (-r["index"], r["t_med"] or 1e9)):
        data.append([
            Paragraph(escape(r["label"]), ST["cell"]), f"{r['index']:.0f}", pct(r["uspesnost"]),
            pct(r["spolehlivost"]), pct(r["shoda"]), pct(r["disciplina"]), pct(r["ran_build"]),
            secs(r["t_med"]), f"{secs(r['t_min'])}–{secs(r['t_max'])}",
            f"{r['tok_med'] / 1000:.0f} k", f"{r['cost']:.2f} $" if r["cost"] else "0 $",
        ])
    w = [28 * mm, 11 * mm, 15 * mm, 17 * mm, 13 * mm, 15 * mm, 13 * mm, 14 * mm, 20 * mm, 14 * mm, 14 * mm]
    return table(data, w, extra=[("ALIGN", (1, 0), (-1, -1), "RIGHT"), ("VALIGN", (0, 0), (-1, 0), "BOTTOM"),
                                 ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2)])


def heat_table(runs, rows, bugs, bug_titles):
    head = ["Konfigurace"] + [Paragraph(f"<b>{b}</b><br/>{escape(bug_titles.get(b, ''))}", ST["cell"]) for b in bugs]
    data, style = [head], []
    for i, r in enumerate(rows, start=1):
        line = [Paragraph(escape(r["label"]), ST["cell"])]
        for j, b in enumerate(bugs, start=1):
            rs = [x for x in runs if x["config"] == r["config"] and x["bug"] == b]
            if not rs:
                line.append("–")
                continue
            k = sum(x.get("success", False) for x in rs)
            frac = k / len(rs)
            line.append(f"{k}/{len(rs)}")
            shade = SEQ[min(len(SEQ) - 1, round(frac * (len(SEQ) - 1)))] if frac > 0 else "#f0efec"
            style += [("BACKGROUND", (j, i), (j, i), colors.HexColor(shade)),
                      ("TEXTCOLOR", (j, i), (j, i), colors.white if frac >= 0.6 else INK)]
        data.append(line)
    w = [45 * mm] + [(175 * mm - 45 * mm) / len(bugs)] * len(bugs)
    return table(data, w, extra=[("ALIGN", (1, 0), (-1, -1), "CENTER"), *style])


# ---------------------------------------------------------------- PDF

def build_pdf(out_dir):
    runs, meta = load(out_dir)
    rows = metrics(runs, meta)
    bugs = meta["bugs"]
    bug_titles = {r["bug"]: r.get("bug_title", r["bug"]) for r in runs}
    reps = meta.get("reps", 1)
    img_dir = out_dir / "img"
    img_dir.mkdir(exist_ok=True)
    chart_index(rows, img_dir / "index.png")
    chart_times(runs, rows, img_dir / "times.png")

    def img(path, width_mm):
        from reportlab.lib.utils import ImageReader
        iw, ih = ImageReader(str(path)).getSize()
        return Image(str(path), width=width_mm * mm, height=width_mm * mm * ih / iw)

    s = []
    s.append(Paragraph("Benchmark oprav chyb", ST["h1"]))
    s.append(Paragraph(escape(meta["suite"]), ST["p"]))
    s.append(Spacer(1, 3))
    tools = meta.get("tools", {})
    s.append(Paragraph(
        f"Spuštěno {escape(meta['started'].replace('T', ' '))} · {len(runs)} běhů · {len(bugs)} chyb × "
        f"{len(rows)} konfigurací × {reps} opakování · Claude Code {escape(tools.get('claude', '?'))} · "
        f"OpenCode {escape(tools.get('opencode', '?'))}", ST["small"]))
    s.append(Spacer(1, 6))
    s.append(Paragraph(escape(meta.get("suite_description", "")), ST["p"]))
    if meta.get("note"):
        s.append(Paragraph("<b>Poznámka:</b> " + escape(meta["note"]), ST["p"]))
    kont = out_dir / "KONTAMINACE.md"
    if kont.exists():
        s.append(Paragraph("<b>Výhrada: část běhů byla kontaminovaná</b> (agent dostal do kontextu instrukce "
                           "navíc k zadání). Podrobnosti v souboru KONTAMINACE.md ve složce výsledků:", ST["p"]))
        for line in kont.read_text(encoding="utf-8").splitlines():
            if line.startswith("2. kolo") or line.startswith("- **Claude Code"):
                s.append(Paragraph(escape(line.replace("**", "")), ST["small"]))

    if rows:
        top = max(r["index"] for r in rows)
        leaders = sorted((r for r in rows if abs(r["index"] - top) < 0.5), key=lambda r: r["t_med"] or 1e9)
        names = ", ".join(f"{escape(r['label'])} ({secs(r['t_med'])})" for r in leaders)
        s.append(Spacer(1, 4))
        s.append(Paragraph(
            f"<b>Nejlepší index {top:.0f}:</b> {names}" + (" – při shodě seřazeno podle mediánu času." if len(leaders) > 1 else "."),
            ST["p"]))

    s.append(Paragraph("Pořadí podle indexu kvality", ST["h2"]))
    s.append(img(img_dir / "index.png", 170))
    s.append(Paragraph(
        f"Index = 100 × ({WEIGHTS['uspesnost']} × úspěšnost + {WEIGHTS['spolehlivost']} × spolehlivost + "
        f"{WEIGHTS['disciplina']} × disciplína). Definice metrik jsou v části Metodika.", ST["small"]))
    s.append(Spacer(1, 6))
    s.append(summary_table(rows))

    s.append(Paragraph("Úspěšnost podle chyb", ST["h2"]))
    s.append(Paragraph(f"Počet úspěšných opakování z {reps}. Tmavší = častější úspěch.", ST["small"]))
    s.append(Spacer(1, 3))
    s.append(heat_table(runs, rows, bugs, bug_titles))

    s.append(KeepTogether([
        Paragraph("Rychlost a její opakovatelnost", ST["h2"]),
        Paragraph("Každý bod je jeden běh. Rozptyl bodů jedné konfigurace ukazuje, jak stabilní je čas "
                  "při stejném vstupu.", ST["small"]),
        img(img_dir / "times.png", 170),
    ]))

    s.append(Paragraph("Chování agentů", ST["h2"]))
    data = [["Konfigurace", "Volání nástrojů (medián)", "Kroky (medián)", "Ověřil build",
             "Zamítnutá oprávnění", "Chyby nástroje"]]
    for r in rows:
        data.append([Paragraph(escape(r["label"]), ST["cell"]), f"{r['tools_med']:.0f}", f"{r['turns_med']:.0f}",
                     pct(r["ran_build"]), str(r["denials"]), str(r["errors"])])
    s.append(table(data, [45 * mm, 30 * mm, 24 * mm, 24 * mm, 28 * mm, 24 * mm],
                   extra=[("ALIGN", (1, 0), (-1, -1), "RIGHT")]))
    s.append(Paragraph("Zamítnutá oprávnění = pokusy o nepovolenou akci (jiný příkaz než build, čtení mimo "
                       "pracovní kopii, web).", ST["small"]))

    s.append(Paragraph("OTA guard", ST["h2"]))
    viol = [r for r in runs if not r.get("guard_ok", True)]
    if not viol:
        s.append(Paragraph("Žádný běh nesáhl na chráněné části (OTA, WiFi, oddíly, motory, skript buildu).", ST["p"]))
    else:
        data = [["Běh", "Porušení"]] + [
            [r["run_id"], Paragraph(escape("; ".join(r.get("guard_violations", []))), ST["cell"])] for r in viol]
        s.append(table(data, [40 * mm, 135 * mm]))
    errs = [r for r in runs if r.get("agent_error")]
    if errs:
        s.append(Paragraph("Chyby nástrojů", ST["h3"]))
        data = [["Běh", "Chyba"]] + [[r["run_id"], Paragraph(escape(str(r["agent_error"]))[:300], ST["cell"])]
                                     for r in errs]
        s.append(table(data, [40 * mm, 135 * mm]))

    # typy selhani: rucni zarazeni z failures.json (podle prepisu a diffu), jinak jen seznam neuspechu
    failed = [r for r in runs if not r.get("success")]
    ffile = out_dir / "failures.json"
    fmap = json.loads(ffile.read_text(encoding="utf-8")) if ffile.exists() else {}
    if failed:
        s.append(Paragraph("Typy selhání", ST["h2"]))
        s.append(Paragraph("Hlavní příčina každého neúspěchu, zařazená ručně podle přepisu agenta a diffu. "
                           "Procento úspěšnosti neříká, <i>jak</i> model selhal, a to je pro nasazení "
                           "důležitější.", ST["small"]))
        types = sorted({(fmap.get(r["run_id"]) or {}).get("typ", "nezařazeno") for r in failed})
        data = [["Konfigurace"] + [Paragraph(escape(t), ST["cell"]) for t in types]]
        for row in rows:
            fr = [r for r in failed if r["config"] == row["config"]]
            data.append([Paragraph(escape(row["label"]), ST["cell"])] +
                        [str(sum((fmap.get(r["run_id"]) or {}).get("typ", "nezařazeno") == t for r in fr) or "")
                         for t in types])
        w = (175 - 45) / max(1, len(types))
        s.append(table(data, [45 * mm] + [w * mm] * len(types), extra=[("ALIGN", (1, 0), (-1, -1), "CENTER")]))
        data = [["Běh", "Typ", "Co se stalo"]]
        for r in sorted(failed, key=lambda r: (r["bug"], r["config"], r["rep"])):
            f = fmap.get(r["run_id"]) or {}
            data.append([r["run_id"], Paragraph(escape(f.get("typ", "nezařazeno")), ST["cell"]),
                         Paragraph(escape(f.get("popis", r.get("check_detail", ""))), ST["cell"])])
        s.append(table(data, [40 * mm, 28 * mm, 107 * mm]))
    rescored = [r for r in runs if r.get("rescored")]
    if rescored:
        s.append(Paragraph("Přehodnocené běhy", ST["h3"]))
        s.append(Paragraph("Po opravě chyby v kontrole byly uložené diffy znovu vyhodnoceny (bench/rescore.py, "
                           "model se znovu nespouštěl). Původní verdikt:", ST["small"]))
        data = [["Běh", "Původně", "Teď"]] + [
            [r["run_id"], Paragraph(escape(("úspěch" if r["rescored"]["success"] else "neúspěch") + ": "
                                           + str(r["rescored"]["check_detail"])), ST["cell"]),
             Paragraph(escape(("úspěch" if r["success"] else "neúspěch") + ": " + str(r["check_detail"])),
                       ST["cell"])] for r in rescored]
        s.append(table(data, [40 * mm, 67 * mm, 68 * mm]))

    # metodika
    s.append(PageBreak())
    s.append(Paragraph("Metodika", ST["h2"]))
    for t in [
        "Každý běh dostane novou čistou kopii projektu se stejnou vnesenou chybou, stejné zadání a stejná pravidla. "
        "Liší se jen model a nástroj (harness). Běhy se střídají v pořadí opakování → chyba → konfigurace.",
        "Model vidí jen popis příznaku, ne místo chyby. Smí číst a upravovat soubory v kopii a spustit jen build. "
        "Web, jiné příkazy a soubory mimo kopii jsou zakázané.",
        "Po skončení modelu benchmark sám: 1) zkontroluje chráněné části (guard), 2) uloží diff, 3) obnoví skript "
        "buildu a sestaví projekt, 4) spustí kontrolu opravy pro danou chybu.",
        "<b>Úspěch běhu</b> = build projde, kontrola opravy projde a guard nenajde porušení.",
        "<b>Úspěšnost</b> = podíl úspěšných běhů. <b>Spolehlivost</b> (pass^k) = podíl chyb opravených ve všech "
        f"{reps} opakováních. <b>Shoda oprav</b> = průměrný podíl nejčastější opravy mezi opakováními (otisk diffu "
        "bez bílých znaků). <b>Disciplína</b> = podíl běhů, které něco změnily, a to bez porušení guardu a bez "
        "zbytečně velké změny (víc než max(10, 5 × referenční oprava) změněných řádků); běh bez změny se nepočítá. "
        "<b>Ověřil build</b> = model sám spustil build a ten opravdu proběhl.",
        "Čas = doba běhu modelu bez závěrečného buildu benchmarku. Tokeny = vstup (včetně cache) + výstup. "
        "Cena u Claude modelů je odhad Claude Code (předplatné se neúčtuje po tokenech), model na Sparku 0 $.",
    ]:
        s.append(Paragraph(t, ST["p"]))
        s.append(Spacer(1, 3))
    s.append(Paragraph("Chyby", ST["h3"]))
    data = [["ID", "Název", "Zadání (co model dostal)"]]
    suite_root = out_dir.parent.parent
    for b in bugs:
        task = (suite_root / "bugs" / b / "task.md")
        data.append([b, Paragraph(escape(bug_titles.get(b, b)), ST["cell"]),
                     Paragraph(escape(task.read_text(encoding="utf-8").strip()) if task.exists() else "", ST["cell"])])
    s.append(table(data, [12 * mm, 40 * mm, 123 * mm]))
    s.append(Paragraph("Konfigurace", ST["h3"]))
    data = [["Konfigurace", "Nástroj", "Model", "Skutečně použité modely"]]
    for r, c in ((r, next(c for c in meta["configs"] if c["name"] == r["config"])) for r in rows):
        data.append([Paragraph(escape(r["label"]), ST["cell"]), c["harness"], c["model"],
                     Paragraph(escape(", ".join(r["models_used"]) or "–"), ST["cell"])])
    s.append(table(data, [45 * mm, 22 * mm, 30 * mm, 78 * mm]))
    s.append(Paragraph("Zadání (šablona)", ST["h3"]))
    s.append(Preformatted(meta.get("prompt_template", ""), ST["code"]))

    # priloha
    s.append(PageBreak())
    s.append(Paragraph("Příloha A: všechny běhy", ST["h2"]))
    data = [["Běh", "Výsledek", "Čas", "Tokeny", "Řádky ±", "Kontrola opravy"]]
    for r in sorted(runs, key=lambda r: (r["bug"], r["config"], r["rep"])):
        res = "úspěch" if r.get("success") else "neúspěch"
        if not r.get("build_ok", True):
            res += " (build)"
        if not r.get("guard_ok", True):
            res += " (guard)"
        data.append([r["run_id"], res, secs(r.get("wall_s")),
                     f"{(r.get('tokens_in', 0) + r.get('tokens_out', 0)) / 1000:.0f} k",
                     f"+{r.get('lines_added', 0)}/−{r.get('lines_removed', 0)}",
                     Paragraph(escape(str(r.get("check_detail", r.get("agent_error", "")))), ST["cell"])])
    s.append(table(data, [42 * mm, 24 * mm, 15 * mm, 15 * mm, 15 * mm, 64 * mm]))

    s.append(PageBreak())
    s.append(Paragraph("Příloha B: nalezené opravy", ST["h2"]))
    s.append(Paragraph("Stejné opravy (podle otisku diffu) jsou sloučené. U každé je seznam běhů, které k ní došly.",
                       ST["small"]))
    for b in bugs:
        s.append(Paragraph(f"{b}: {escape(bug_titles.get(b, b))}", ST["h3"]))
        groups = defaultdict(list)
        for r in runs:
            if r["bug"] == b:
                groups[r.get("diff_sig", "?")].append(r)
        for sig, rs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            ok = sum(r.get("success", False) for r in rs)
            who = ", ".join(f"{r['config']} r{r['rep']}" for r in rs)
            s.append(Paragraph(f"<b>{len(rs)}×</b> (úspěch {ok}×): {escape(who)}", ST["small"]))
            p = out_dir / "runs" / rs[0]["run_id"] / "diff.patch"
            diff = p.read_text(encoding="utf-8") if p.exists() else ""
            lines = diff.splitlines()
            if len(lines) > 60:
                lines = lines[:60] + [f"... (zkráceno, celkem {len(diff.splitlines())} řádků)"]
            s.append(Preformatted("\n".join(lines) or "(žádná změna)", ST["code"]))
            s.append(Spacer(1, 4))

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("UI", 7)
        canvas.setFillColor(colors.HexColor(MUTED))
        canvas.drawString(18 * mm, 10 * mm, f"Benchmark oprav chyb · {meta['started'][:10]}")
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"strana {doc.page}")
        canvas.restoreState()

    pdf = out_dir / f"benchmark-{meta['started'][:10]}.pdf"
    doc = SimpleDocTemplate(str(pdf), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm, title="Benchmark oprav chyb",
                            author="esp-bench", creator="esp-bench report.py")
    doc.build(s, onFirstPage=footer, onLaterPages=footer)
    return pdf


if __name__ == "__main__":
    print(build_pdf(Path(sys.argv[1]).resolve()))
