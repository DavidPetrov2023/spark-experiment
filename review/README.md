# Code review změn (Spark nebo Claude)

Nástroj projde změny v gitu a napíše zprávu s nálezy. **Model jen čte, nic nemění.** Nálezy jsou návrhy, rozhoduje člověk.

| Backend | Kde běží | Kdy použít |
|---|---|---|
| `spark` (výchozí) | gpt-oss-120b na Sparku | kód, který nesmí mimo firmu; `--effort medium` na rychlé review (minuty), `high` na noční |
| `claude` | Claude přes Claude Code (předplatné) | přesnější review a srovnání se Sparkem |

Bez nástroje jde i v Claude Code příkaz `/code-review` (aktuální změny, větev nebo PR).

## Nastavení

- Spark: proměnné prostředí `SPARK_URL` (adresa LiteLLM na Sparku, bez `/v1`) a `LITELLM_API_KEY` (osobní klíč).
- Claude: Claude Code přihlášený předplatným.
- Python 3.11+, git. Nic dalšího se neinstaluje.

## Použití

```
python review/spark_review.py C:/cesta/k/repo --since "24 hours ago" --dry-run    # nanečisto, nic neodešle
python review/spark_review.py C:/cesta/k/repo --since "24 hours ago"              # Spark, high
python review/spark_review.py C:/cesta/k/repo --since "7 days ago" --effort medium
python review/spark_review.py C:/cesta/k/repo --range main~3..main --backend claude --model sonnet
```

- Pravidla projektu (co je kritické) patří do `REVIEW-PRAVIDLA.md` v kořeni repozitáře. Jinak se použije
  `review/pravidla-vychozi.md` (firmware ESP32: OTA, motory, tiky, souběh).
- Zprávy jdou do `review/vystupy/` (mimo git). Velké rozsahy nástroj odmítne (300 000 znaků), pak zúžit rozsah.

## Bezpečnost

- Citlivé soubory (`.env`, `device_config.h`, `release.py`, klíče, `sdkconfig`) se k modelu nedostanou.
- Celý text projde kontrolou tajných údajů (`tools/secret_scan.py`). Při nálezu se **nic neodešle**.
- Claude běží v prázdné dočasné složce bez nástrojů, dostane jen připravený text.
- Co model přečte, vidí jeho provozovatel: u Sparku správce (logy LiteLLM), u Clauda Anthropic.

## Test kvality na 10 známých chybách

```
python review/test_review.py --backend spark --effort medium
python review/test_review.py --backend claude --model sonnet
python review/test_review.py --negativni      # navíc plané poplachy na vzorových opravách
```

Každá vnesená chyba z `esp-bench/bugs` se nasimuluje jako commit a review ji má najít (soubor a klíčová slova
podle `ocekavane.json`). Souhrn v `review/vystupy/test-…/souhrn.json`, zprávy si přečtěte.

## Noční spouštění

Plánovač úloh Windows (počítač nesmí v noci spát), cestu upravit podle sebe:

```
schtasks /Create /TN "Review mujprojekt" /SC DAILY /ST 02:00 /TR "python C:\cesta\review\spark_review.py C:\cesta\k\repo --since \"24 hours ago\""
```

Ráno zpráva v `review/vystupy/`.

## Soubory

| Soubor | Co dělá |
|---|---|
| `spark_review.py` | nástroj: diff → kontrola → model → zpráva |
| `pravidla-vychozi.md` | výchozí pravidla pro firmware ESP32 |
| `test_review.py` | test kvality na chybách z benchmarku |
| `ocekavane.json` | co má review u každé chyby najít |
| `vysledky-testu.md` | naše výsledky testu pro srovnání |
