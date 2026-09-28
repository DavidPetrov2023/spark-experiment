# Spark Chat (rozšíření VS Code)

Okno chatu ve VS Code napojené na model **gpt-oss-120b na serveru DGX Spark** (přes LiteLLM). Bez cloudu,
bez Copilotu, bez Claude. V levém panelu má vlastní ikonu **Spark**.

- **Chat:** dotazy česky, volitelně s přiloženým otevřeným souborem nebo označeným výběrem.
- **Review posledního commitu:** jedním tlačítkem pošle poslední commit otevřeného repozitáře k review. Posílá se
  stejný text jako z `review/spark_review.py`: pokyny pro reviewera, pravidla projektu
  (`REVIEW-PRAVIDLA.md`, jinak `review/pravidla-vychozi.md`), diff a plné znění změněných souborů.
- **Úroveň přemýšlení:** low / medium / high v hlavičce (výchozí medium).

## Instalace (Windows)

1. **Tailscale** nainstalovaný a připojený (pozvánku dá správce Sparku).
2. **Adresa a klíč** od správce Sparku jako uživatelské proměnné prostředí. V PowerShellu (hodnoty doplnit):
   ```
   setx SPARK_URL "https://…"          # adresa LiteLLM na Sparku, bez /v1
   setx LITELLM_API_KEY "sk-…"         # váš osobní klíč
   ```
   Klíč nikdy nedávejte do souborů, do gitu ani do chatu.
3. **Instalace rozšíření** ve složce, kde je tento soubor:
   ```
   code --install-extension spark-chat-0.1.1.vsix
   ```
   Nebo ve VS Code: Extensions (Ctrl+Shift+X) → `…` → **Install from VSIX…**
4. **Zavřít a znovu otevřít VS Code** (kvůli proměnným). Vlevo v liště je ikona **Spark** (hvězdička).

## Použití

- Chat: napsat dotaz a Enter. Zaškrtnutím „přiložit otevřený soubor“ se pošle otevřený soubor nebo označený výběr.
- Review: otevřít složku s git repozitářem, kliknout **🔍 Review posledního commitu** a vybrat větev.
  Zkušební úloha: experiment `github.com/DavidPetrov2023/spark-experiment`, větev `origin/uloha/X3`.
- Úroveň přemýšlení: medium na běžné dotazy, high na těžké (pomalejší).
- Spark nic nemění ani nespouští, jen odpovídá.

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
