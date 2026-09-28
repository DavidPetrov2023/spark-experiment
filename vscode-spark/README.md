# Spark Chat (rozšíření VS Code)

Okno chatu ve VS Code napojené na model **gpt-oss-120b na serveru DGX Spark** (přes LiteLLM). Bez cloudu,
bez Copilotu, bez Claude. V levém panelu má vlastní ikonu **Spark**.

- **Chat:** dotazy česky, volitelně s přiloženým otevřeným souborem nebo označeným výběrem.
- **Review posledního commitu:** jedním tlačítkem pošle poslední commit otevřeného repozitáře k review. Posílá se
  stejný text jako z `review/spark_review.py`: pokyny pro reviewera, pravidla projektu
  (`REVIEW-PRAVIDLA.md`, jinak `review/pravidla-vychozi.md`), diff a plné znění změněných souborů.
- **Úroveň přemýšlení:** low / medium / high v hlavičce (výchozí medium).

## Instalace

1. Tailscale připojený a proměnné prostředí `SPARK_URL` (adresa LiteLLM na Sparku, bez `/v1`) a `LITELLM_API_KEY`
   (osobní klíč). Adresu i klíč dá správce Sparku.
2. `code --install-extension vscode-spark/spark-chat-0.1.0.vsix` a restartovat VS Code.
3. Vlevo ikona **Spark** (hvězdička).

## Bezpečnost

- Adresa a klíč se čtou jen z proměnných prostředí. Rozšíření je nikde neukládá ani nezobrazuje. Z chybových
  hlášek je odstraní (i IP adresy).
- Citlivé soubory (`.env`, `device_config.h`, `release.py`, klíče, `sdkconfig`) se nepřikládají ani neposílají
  v review. Text se před odesláním kontroluje na tajné údaje (klíče, tokeny, adresa Sparku). Při nálezu se nic
  neodešle.
- Co pošlete, vidí správce Sparku (logy LiteLLM). Nevkládejte hesla ani data zákazníků bez souhlasu.
- Model nic nemění ani nespouští, jen odpovídá. Výstup je návrh ke kontrole.

## Soubory

| Soubor | Co dělá |
|---|---|
| `extension.js` | okno chatu, příkazy |
| `spark.js` | spojení se Sparkem, streamování, příprava review (bez závislosti na VS Code) |
| `media/` | vzhled okna, ikona |
| `prompts/` | pokyny pro reviewera a výchozí pravidla |
| `build_vsix.py` | sestaví `.vsix` bez npm |
