# Benchmark oprav chyb (esp-bench)

Obecná metoda, jak porovnat modely (a nástroje, ve kterých běží) na opravě chyby v reálném projektu. Výstupem je PDF. První sada je ESPTest (ESP32), ale runner ani report na ESP nezávisí.

## Princip

1. **Baseline:** ověřená, funkční kopie projektu.
2. **Chyby:** do baseline se vnese vždy jedna známá chyba. Model dostane jen popis příznaku, jako hlášení od uživatele.
3. **Stejné vstupy:** každá kombinace chyba × konfigurace × opakování dostane novou čistou kopii, stejné zadání, stejná pravidla i nástroje. Liší se jen model, případně harness. Opakování měří opakovatelnost.
4. **Automatické vyhodnocení** po skončení modelu, model do něj nemá jak zasáhnout:
   - **guard:** chráněné části projektu se nesmí změnit;
   - **build:** vždy s původním skriptem;
   - **kontrola opravy:** `check.py` dané chyby.
5. **Úspěch** = build projde **a** oprava projde **a** guard nenajde porušení.

## Metriky v PDF

| Metrika | Význam |
|---|---|
| Úspěšnost | podíl úspěšných běhů |
| Spolehlivost (pass^k) | podíl chyb opravených ve všech k opakováních |
| Shoda oprav | jak často opakování vedou ke stejné opravě (otisk diffu) |
| Disciplína | podíl běhů bez porušení guardu a bez zbytečně velké změny |
| Ověřil build | podíl běhů, kde model sám spustil build |
| Čas | medián a rozsah času modelu (rozptyl = opakovatelnost rychlosti) |
| Tokeny, cena | spotřeba; u lokálních modelů 0 $ |
| **Index kvality** | 100 × (0,5 × úspěšnost + 0,3 × spolehlivost + 0,2 × disciplína) |

## Struktura

```
suite.json          popis sady: baseline, chyby, build, guard, šablona zadání, povolené příkazy
baseline/           ověřená kopie projektu
bugs/<ID>/          bug.patch (vnese chybu), task.md (příznak), check.py (ověření opravy), meta.json,
                    fixes/*.patch a wrong/*.patch (vzorové a chybné opravy pro ověření check.py)
suite/              věci specifické pro sadu: build.ps1, guard.py, pomůcky (csrc.py), prompt.md
bench/              obecné: run_bench.py (runner), report.py (PDF), configs.json (modely), requirements.txt
C:\esp-bench-work\  pracovní kopie běhů (work_dir v suite.json): schválně MIMO strom projektu, jinak si
                    Claude Code načte CLAUDE.md z nadřazených složek; runner to kontroluje (context_leaks)
results/<čas>/      runs.jsonl, meta.json, runs/<běh>/ (zadání, přepis agenta, diff, build), benchmark.pdf
```

## Použití

```powershell
python -m venv .venv; .venv\Scripts\pip install -r bench\requirements.txt   # jednou

python bench\run_bench.py --verify                         # ověřit baseline, chyby a guard
python bench\run_bench.py --bugs B2 --reps 1               # pilot
python bench\run_bench.py --reps 3                         # plný běh
python bench\run_bench.py --resume results\<čas>           # dokončit přerušený běh
.venv\Scripts\python bench\report.py results\<čas>         # PDF
python bench\rescore.py results\<čas> [--write]            # po opravě kontroly přehodnotit uložené běhy
```

Výběr konfigurací: `--only haiku,opus,spark-coder-cc`, jinak všechny s `"enabled": true` v `bench/configs.json`.

## Konfigurace (harness × model)

- `claude-code`: `claude -p` se stejným nastavením pro všechny modely (`.claude/settings.json` v pracovní kopii: úpravy souborů, jen povolené příkazy, bez webu).
  - Claude modely jdou přes předplatné.
  - Model na Sparku přes `ANTHROPIC_BASE_URL` na LiteLLM. Proměnné se nastavují jen pro daný proces.
- `opencode`: `opencode run` s `opencode.json` v pracovní kopii (poskytovatel `spark`, stejná povolení).

## Nová sada pro jiný projekt

1. Zkopírovat ověřený projekt do `baseline/` bez tajných údajů a skriptů, které nasazují.
2. Napsat `suite/build.*` a `suite/guard.py` (funkce `check(ws) -> {"ok", "violations"}`) a upravit `suite.json`.
3. Pro každou chybu vytvořit `bugs/<ID>/`:
   - `bug.patch`;
   - `task.md` (jen příznak);
   - `check.py` (funkce `check(ws) -> (ok, detail)`, musí projít na baseline a selhat s chybou);
   - volitelně `fixes/*.patch` (správné opravy, musí uspět) a `wrong/*.patch` (chybné, nesmí uspět); patche jsou proti kopii s chybou;
   - úloha typu nová funkce: bez `bug.patch` a v `meta.json` `"baseline_passes": false`;
   - `meta.json`.
4. Spustit `--verify`. Teprve když všechno projde, pouštět modely.

## Sada ESPTest

- **Podklad:** `C:\Cloud\AI\ESPTest` @ `6fabfec` (bliká červenou, WiFi, telemetrie, OTA s rollbackem).
- **Chyby:** B1–B4 (základní), H1–H3 (těžší), X1–X4 (nejtěžší: dvě chyby naráz, souběh úloh, matoucí příznak u OTA, nová funkce), všechny jen mimo OTA.
- **Guard:** hlídá, že se nezmění OTA, WiFi, oddíly, sdkconfig, potvrzení firmwaru po telemetrii, `PowerMode: ACTIVE`, pořadí startu a motory v nule.
- **Nic se nenasazuje:** `device_config.h` má neplatnou URL, `release.py` ani `.env` v sadě nejsou a z benchmarku nic nejde na desku ani na server.
