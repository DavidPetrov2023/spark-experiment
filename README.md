# Experiment: najde AI chybu ve firmwaru?

Demonstrátor k závěrečné zprávě **Spark proti Claude** (`Spark-proti-Claude.pdf`). Do funkčního firmwaru pro ESP32
jsme vnesli 10 chyb a přidali 1 úlohu na novou funkci. Tady si můžete sami vyzkoušet, jestli je AI najde (Claude,
model na Sparku nebo váš nástroj), zopakovat náš test, nebo si nechat udělat review vlastního kódu.

> Firmware je ořezaná verze autorova vlastního kódu pro robota. Nic nenahrávat na desku ani na server
> (`device_config.h` má schválně neplatnou adresu).

## Co je kde

| Větev / složka | Obsah |
|---|---|
| `main` | tento návod, zpráva (PDF), přehled úloh (`ulohy.md`), firmware bez chyb (`firmware/`) |
| `review/` | nástroj na review a test na 10 známých chybách |
| `esp-bench/` | celý benchmark: agenti opravují chyby, build, kontroly, PDF (návod v `esp-bench/README.md`, postup v `esp-bench/METODIKA.md`) |
| `vysledky/` | PDF našich běhů pro srovnání |
| `uloha/B1` … `uloha/X4` | poslední commit „Úprava firmwaru“ vnáší chybu, `ZADANI.md` = hlášení od uživatele |
| `reseni` | `RESENI.md`: co bylo špatně a jak to opravit. **Neotevírat před pokusem.** |

## Nastavení

1. `git clone <odkaz>` a Python 3.11+ (`pip install` není pro review potřeba).
2. **Spark** (máte Tailscale účet a osobní klíč): nastavit proměnné prostředí
   - `SPARK_URL` = adresa LiteLLM na Sparku (bez `/v1`, dá správce Sparku),
   - `LITELLM_API_KEY` = váš osobní klíč.

   Windows: `setx SPARK_URL "https://…"` a `setx LITELLM_API_KEY "sk-…"`, pak nový terminál.
   Klíč nikdy nedávat do souborů ani do gitu.
3. **Claude** (volitelně): Claude Code přihlášený vlastním předplatným.

## 1. Bez instalace: chat (Open WebUI na Sparku nebo claude.ai)

1. V `ulohy.md` vyberte úlohu a otevřete její větev (na GitHubu přepínač větví).
2. Do chatu vložte text ze `ZADANI.md` a obsah `firmware/main/main.c` a `firmware/main/telemetry.c`, například:
   > Jsi reviewer firmwaru ESP32 (ESP-IDF, FreeRTOS). Přišlo hlášení od uživatele: „…“. Najdi příčinu v kódu
   > a navrhni opravu. Na OTA (aktualizaci firmwaru) nesahej.
3. Porovnejte s `RESENI.md` ve větvi `reseni`.

V Open WebUI zkuste gpt-oss-120b na úrovni přemýšlení medium a high (pokročilé parametry chatu).

## 2. Test review na 10 známých chybách (jako my)

```
python review/test_review.py --backend spark --effort medium      # gpt-oss-120b na Sparku, asi 10–20 min
python review/test_review.py --backend claude --model sonnet      # Claude přes Claude Code (předplatné)
python review/test_review.py --dry-run                            # jen připraví texty, nic neodešle
```

Každá chyba se nasimuluje jako commit a review má najít, co je na něm špatně. Výsledek je v
`review/vystupy/test-…/souhrn.json` a u každého commitu zpráva v Markdownu. **Zprávy si přečtěte**,
automatické počítání je hrubé (hledá soubor a klíčová slova podle `review/ocekavane.json`).

### Naše výsledky testu review (28. 9. 2026)

| | gpt-oss-120b (Spark, medium) | Claude Sonnet (Claude Code) |
|---|---|---|
| Nalezené chyby | **9 z 10** | **10 z 10** |
| Nálezů celkem, včetně šumu | 24 | 11 |
| Čas celkem (na commit) | 8 min (14–77 s) | 7 min (17–80 s) |
| Přehlédl | B2 (smyčka nepřepíná `on`, LED pořád svítí) | nic |

- **Review je pro lokální model snazší než oprava.** gpt-oss v review našel i X3 (čekání 125 s místo 1,25 s),
  kterou jako agent nevyřešil ani jednou. V malé změně se chyba hledá snáz než podle příznaku v celém kódu.
- **gpt-oss přidává víc šumu:** nálezy ve starém kódu mimo změnu, občas planý poplach (třeba že pole struktury
  `gpio_config_t` nejsou inicializovaná, přestože je jazyk C doplní nulami) a někdy podhodnotí závažnost
  (souběh u X2 jen „střední“).
- Výsledky se mezi běhy mírně liší, u sebe čekejte podobné, ne stejné (±1 chyba).
- Doporučení: gpt-oss na Sparku jako noční „druhý pár očí“ na kód, který nesmí ven, se zprávou čtenou kriticky.
  Na důležité review Claude.

## 3. Review vlastního kódu

```
python review/spark_review.py C:/cesta/k/vasemu/repo --since "7 days ago" --dry-run   # nejdřív nanečisto
python review/spark_review.py C:/cesta/k/vasemu/repo --since "7 days ago"             # Spark, gpt-oss high
python review/spark_review.py C:/cesta/k/vasemu/repo --range main~3..main --backend claude --model sonnet
```

- Model jen čte a napíše zprávu (`review/vystupy/`), nic nemění.
- Citlivé soubory (`.env`, `device_config.h`, `release.py`, klíče) se k modelu nedostanou a text projde
  kontrolou tajných údajů. Při nálezu se nic neodešle.
- Pravidla projektu (co je kritické) dejte do `REVIEW-PRAVIDLA.md` v kořeni svého repozitáře. Vzor:
  `review/pravidla-vychozi.md`.
- Na Sparku se `--effort medium` hodí na rychlé review (minuty), `high` na noční (desítky minut).
- Bez nástroje: v Claude Code příkaz `/code-review` nad aktuálními změnami nebo větví.

## 4. Oprava agentem (Claude Code, OpenCode)

```
git checkout -b muj-pokus uloha/X3
```

Agentovi zadejte text ze `ZADANI.md` s pokynem „Najdi příčinu a oprav ji. Na OTA nesahej, nic nenahrávej
na desku.“ Build jde ověřit s ESP-IDF 5.2.6 (`idf.py build` ve `firmware/`), stačí ale porovnat s řešením.

## 5. Celý benchmark (agenti, build, kontroly, PDF)

Postup v `esp-bench/README.md`, metodika a bezpečnost v `esp-bench/METODIKA.md`. Potřeba: Windows, ESP-IDF 5.2.6
v `%USERPROFILE%\esp\v5.2.6\esp-idf`, Claude Code, OpenCode, Python venv s `esp-bench/bench/requirements.txt`.

```
cd esp-bench
python bench/run_bench.py --verify                                   # nejdřív ověřit sadu
python bench/run_bench.py --bugs X1,X2,X3,X4 --reps 1 --only sonnet,spark-gptoss-oc
```

Pracovní kopie jde do `C:\esp-bench-work` (mimo tento repozitář). Nesmí nad ní ležet žádný `CLAUDE.md`,
jinak ho agent načte a výsledky budou zkreslené; runner to kontroluje.

## Jak jsme dopadli my (nejtěžší úlohy X1–X4, oprava agentem)

| Model | Úspěšnost | Čas na úlohu |
|---|---|---|
| Claude Opus / Sonnet | 8/8 | 1,5 min |
| Claude Haiku | 7/8 | 1,7 min |
| gpt-oss-120b (Spark, medium) | 5/8 | 3,5–4,5 min |
| gpt-oss-120b (Spark, high, limit 60 min) | 4/7 | 7–18 min |
| qwen3-coder-next (Spark) | 4/12 | 4–6 min |

Nejzáludnější je **X3**: příznak ukazuje na aktualizaci firmwaru (OTA), ale příčina je jinde. Lokální modely ji
nevyřešily ani jednou a několikrát sahaly do OTA. Podrobnosti v `Spark-proti-Claude.pdf`.

Celý postup na jedné úloze (hlášení, skutečná příčina, oprava od Claude i od Sparku, jak se ověřila) ukazuje ve
zprávě kapitola **Příklad: jedna chyba od hlášení po opravu** (úloha X1). Včetně případu, kdy model opravil jen
polovinu a ohlásil hotovo. X1 je tím prozrazená, na vlastní pokus si vyberte jinou.

## Pravidla

- Do chatu ani nástrojů nevkládat hesla, klíče ani data zákazníků bez souhlasu. Co model přečte, vidí jeho
  provozovatel (u Clauda Anthropic, u Sparku správce v logu).
- Výstup AI je návrh ke kontrole, ne hotová oprava.
- Dlouhé běhy na Sparku ohlásit správci Sparku (sdílený server, najednou nejvýš 8 požadavků).
