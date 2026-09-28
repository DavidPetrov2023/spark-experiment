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
