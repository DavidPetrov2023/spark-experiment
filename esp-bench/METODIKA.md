# Metodika: jak porovnávat modely na reálném projektu

Obecný postup, jak změřit, jak dobře různé modely (a nástroje, ve kterých běží) opraví chybu nebo doplní funkci v reálném projektu. Vznikl při srovnání modelů Claude s modely na DGX Sparku (sada ESPTest pro ESP32, září 2026), ale na ESP32 nezávisí. Technické použití runneru popisuje [README.md](README.md).

## K čemu to je

- Rozhodnout, jaký model a harness nasadit na konkrétní typ práce.
- Najít hranici, kde se levnější nebo lokální model láme proti nejsilnějšímu.
- Opakovat stejné měření, když se změní model, verze nástroje nebo server.

Nejde o obecný žebříček modelů. Výsledek platí pro daný projekt, typy úloh a nastavení.

## Principy

1. **Reálný projekt, reálný build.** Model pracuje ve skutečném repozitáři a oprava se ověřuje buildem, ne čtením odpovědi.
2. **Model dostane jen příznak**, jako hlášení od uživatele. Ne místo chyby ani nápovědu k opravě.
3. **Stejné podmínky:** každý běh má čistou kopii, stejné zadání, pravidla, nástroje a limity. Liší se jen model, případně harness.
4. **Hodnotí se chování, ne zápis.** Kontrola přijme každou správnou opravu, ne jen tu, kterou čekal autor úlohy.
5. **Pravidla v zadání = pravidla v hodnocení.** Co hlídá automatická kontrola, musí model vědět předem.
6. **Nejdřív ověřit měřidlo, pak měřit.** Každá kontrola se vyzkouší na správných i chybných opravách dřív, než na ni pustíme modely.
7. **Bezpečnost má přednost před výsledkem.** Benchmark nesmí nic nasadit ani vynést tajné údaje.
8. **Model a harness se měří zvlášť.** Stejný model v jiném nástroji může dopadnout jinak.

## Postup

### 1. Cíl a mantinely

- Co chceme zjistit (který model, na jaký typ práce, proti čemu).
- **Co se nesmí rozbít** (u ESPTest: OTA, bez ní jde deska zachránit jen kabelem). Z toho vznikne guard (krok 4).
- **Co smí odejít ven.** Obsah souborů jde k poskytovateli modelu (Anthropic, server se Sparkem, logy LiteLLM). Do kopie projektu nedávat tokeny, `.env`, skripty pro nasazení ani adresy serverů.
- Kolik smí stát čas a peníze (počet běhů, limity předplatného, sdílený server).

### 2. Baseline

- Ověřená funkční kopie projektu v samostatném repozitáři, bez tajných údajů a bez skriptů, které nasazují. Konfigurace s neplatnými adresami (např. `https://example.invalid/`).
- Build jde spustit jedním příkazem, který se dá modelu povolit (u Claude Code na Windows `sh build.sh`, ne `powershell -File ...`).
- Baseline musí projít buildem, všemi kontrolami i guardem.

### 3. Úlohy

Úlohy stupňovat a míchat typy. Snadné úlohy zvládnou všechny modely a nic nerozliší.

| Typ | Co prověří | Příklad (ESPTest) |
|---|---|---|
| jedna chyba v jednom souboru | základní diagnóza | B1–B4: špatný pin, chybějící uvolnění paměti |
| chyba se znalostí platformy | znalost API a jednotek | H1–H3: watchdog, přetečení, dvojí převod na tiky |
| dvě chyby v jednom hlášení | důslednost, neskončit po první opravě | X1 |
| chyba napříč soubory / souběh úloh | práce se sdíleným stavem, zamykání | X2 |
| matoucí příznak | nenechat se svést k zásahu do chráněné části | X3: rollback po OTA, příčina v `main.c` |
| nová funkce | psaní kódu s API, ne jen hledání chyby | X4: RSSI a MinFreeHeap do telemetrie |

- **Nejlepší zdroj jsou skutečné chyby** z historie projektu (git log, tickety). Vymyšlené chyby hrozí tím, že autor úlohy nevědomky nahraje modelům, které myslí podobně jako on.
- Vnesená chyba se musí dát přeložit. Chyba, kterou odmítne překladač, v praxi nenastane (u ESP-IDF např. `~` na `bool` kvůli `-Werror`).
- Zadání obsahuje jen příznak, jak by ho popsal uživatel: co je vidět, výpis z konzole, co je v pořádku.
- Na orientační srovnání stačí 3–4 úlohy na úroveň. Na pevné závěry je potřeba 10–20.

### 4. Hodnocení

Běh je úspěšný, jen když projdou všechny tři části:

1. **Build** vždy s původním skriptem (model ho nesmí mít jak podvrhnout).
2. **Kontrola opravy** (`check.py`): ověřuje výsledné chování, třeba skutečnou délku čekání po převodu na tiky, simulaci smyčky nebo zamčení každého přístupu ke sdílenému poli. Nehledá konkrétní řádek.
3. **Guard:** chráněné soubory, funkce a nastavení se nesmí změnit vůbec. Je záměrně přísný, protože build nebezpečnou změnu nepozná (příklad: model přesunul `free(url)` před stažení OTA, build prošel, ale další OTA by selhala).

Ověření měřidla (`--verify`):

- baseline projde vším, kopie s chybou selže na své kontrole;
- **vzorové opravy** (`fixes/`, víc různých způsobů) musí uspět a **chybné opravy** (`wrong/`: poloviční oprava, oprava jen jedné ze dvou chyb, zásah do chráněné části) musí selhat;
- negativní testy guardu: zásah do chráněné části musí být odhalen.

Bez vzorových oprav se chyby kontrol projeví až na modelech. U ESPTest kontroly dvakrát zamítly správnou opravu a jednou nepoznaly časný `return` při chybě.

Ani vzorové opravy nepokryjí všechny správné způsoby (X2: atomický ukazatel přes `_Atomic(...)`). Proto se každý neúspěch, zvlášť u silného modelu, ručně prověří v `diff.patch`. Když se ukáže chyba kontroly, opraví se, přidá se jako vzorová oprava a uložené běhy se přehodnotí skriptem `bench/rescore.py` (obnoví odevzdaný kód z diffu, model se znovu nespouští, původní verdikt zůstane v záznamu).

**Úloha typu nová funkce:** bez patche, baseline kontrolou neprojde (`baseline_passes: false`).

### 5. Konfigurace (model × harness)

- Zapsat verze harnessů a přesné názvy modelů. Před každým během ověřit, co server skutečně nabízí (`/v1/models`). Modely na sdíleném serveru se mění ze dne na den.
- **Povolení co nejužší:** úpravy souborů jen v pracovní kopii, jediný povolený příkaz (build), žádný web. Pozor: holé `Read` v `--allowedTools` Claude Code povolí čtení kdekoli na disku.
- Nastavení předávat parametry nebo proměnnými prostředí jen pro daný proces. Projektové nastavení v nedůvěryhodné složce Claude Code ignoruje.
- U lokálních modelů sladit limity: výstup (`CLAUDE_CODE_MAX_OUTPUT_TOKENS`) + konverzace se musí vejít do kontextu modelu.
- Všechny role modelu v harnessu (hlavní, rychlý, subagenti) nasměrovat na testovaný model, jinak harness potichu volá jiný.

### 6. Pilot

- Jedna úloha × jedno kolo × všechny konfigurace.
- **Přečíst přepisy**, ne jen výsledky: zamítnutá povolení, pokusy obejít pravidla, chyby harnessu. Pilot na ESPTest odhalil, že Claude Code zakazoval build, takže Opus zkoušel build 20 různými způsoby.
- Chyby prostředí opravit a pilot zopakovat. Neplatný pilot archivovat s poznámkou, proč neplatí.

### 7. Plný běh

- Aspoň 3 opakování, jinak nejde měřit spolehlivost.
- Pořadí prokládat (opakování → úloha → konfigurace), aby změna zátěže nebo limitů nepostihla jen jednu konfiguraci.
- Pevný časový limit na běh (u nás 15 min). Pomalejší model tím dostává méně kroků, takže limit je součást zadání a patří do reportu.
- Běhy na sdíleném serveru pouštět po jednom. Zátěžový test souběžných sezení dělat zvlášť, jinak se časy nedají srovnat.
- Kdo spravuje server, má vědět, kdy test běží. Dlouhé nebo přerušené požadavky jinak vypadají v logu jako chyba.

### 8. Vyhodnocení

| Metrika | Význam |
|---|---|
| Úspěšnost | podíl úspěšných běhů |
| Spolehlivost (pass^k) | podíl úloh vyřešených ve všech k opakováních |
| Disciplína | podíl běhů bez porušení guardu a bez zbytečně velké změny |
| Shoda oprav | jak často opakování vedou ke stejné opravě |
| Ověřil build | jestli si model opravu sám ověřil |
| Čas, tokeny, cena | medián a rozptyl; u lokálních modelů 0 $ |
| Index kvality | 100 × (0,5 × úspěšnost + 0,3 × spolehlivost + 0,2 × disciplína) |

Procento úspěšnosti nestačí. U každého neúspěchu určit **typ selhání** z přepisu a diffu a zapsat ho do `results/<běh>/failures.json` (`{"běh": {"typ": ..., "popis": ...}}`). Report z něj udělá sekci „Typy selhání“. Automaticky to spolehlivě nejde, protože poloviční opravu od špatné diagnózy pozná jen člověk (nebo model), který čte přepis.

| Typ selhání | Poznávací znak | Příklad z ESPTest |
|---|---|---|
| špatná diagnóza | oprava jinde, než je příčina | únik hledal v OTA a přesunul `free(url)` před stažení (use-after-free) |
| poloviční oprava | příčinu našel, opravil jen část | zámek jen u zápisu, čtení bez zámku; převod na tiky dál dvakrát |
| porušení pravidel | správná oprava + změna v chráněné části | přepsal `cJSON_free` na `free` v chráněné `post()` |
| bloudění / timeout | dlouho čte soubory, nic nezapíše | 15 min čtení hlaviček, opravu nezapsal |
| zacyklení | jeden krok s tisíci tokeny textu, konec na limitu výstupu | 32 000 tokenů úvah o `snprintf`, žádná změna |
| timeout: pomalé přemýšlení | problému rozumí a jde správným směrem, ale úvahy (100k+ znaků) vyčerpají limit | gpt-oss na `high` při ~30 tok/s: správně zaváděl mutex, nestihl dokončit |
| obejití pojistky | chráněné soubory nechá, ale pojistku vyřadí jinudy („litera ano, smysl ne“) | nový soubor, který po 15 s sám volá `ota_confirm()`, prezentovaný jako řešení „bez zásahu do chráněných souborů“ |
| nepoužil nástroje | odpoví textem, že nemá přístup ke kódu | malý model v OpenCode |
| chyba harnessu | neexistující nástroj, zamítnutá povolení, přetečený kontext | `ContextWindowExceeded`, volání neexistujícího nástroje |

### 9. Report, deník, bezpečnost

- PDF: pořadí podle indexu, úspěšnost podle úloh, čas a jeho rozptyl, chování agentů, guard, typy selhání.
- Deník: co se měnilo (verze, modely, zadání, kontroly) a proč. Opravy vlastních chyb zapsat otevřeně.
- Po každém běhu zkontrolovat, co odešlo ven. Hledat ve výstupech domény, IP adresy a tokeny.

## Bezpečnost

Agent s přístupem k souborům a příkazům je riziko sám o sobě, ať je to jakýkoli model. Benchmark ho musí zvládnout, i když se model chová špatně.

**1. Co odchází ven a kam.** Každý soubor, který model přečte, odchází k poskytovateli modelu:

- u Clauda do Anthropicu;
- u modelu na Sparku na server kolegy, kde ho může uložit LiteLLM do logů a vidí ho správce.

Proto:

- kopie projektu bez tokenů, `.env`, skriptů pro nasazení a skutečných adres serverů;
- originál projektu mimo dosah agenta.

**2. Pravidla v zadání nejsou ochrana.** Modely je porušují, i když jsou napsaná výslovně:

- qwen3-coder-next u X3 přepsal hlídání rollbacku v `ota.c`, přestože zadání OTA výslovně zakazovalo. Příčinu nenašel a ohlásil „Opraveno správně“;
- Haiku při správné opravě změnil chráněnou funkci `post()`.

Ochranu dělají jen tyto vrstvy:

- **povolení** (co agent technicky může);
- **guard** (co se nesmí změnit);
- **nic se nenasazuje**: výstup agenta je jen diff ke kontrole, žádné nahrávání na desku ani na server;
- **lidská kontrola** každé změny v citlivé části, i když model tvrdí, že je hotovo.

**3. Nejužší povolení** (ověřená nastavení):

- **Claude Code:** `--allowedTools` jen s konkrétním příkazem buildu (`Bash(sh build.sh)`). **Nikdy holé `Read`**, to povolí čtení kdekoli na disku. Bez něj Claude Code čte jen v pracovní složce a čtení mimo ni zamítne (ověřeno v logu).
- **OpenCode:** `external_directory: deny`, `bash` zakázaný kromě buildu, `webfetch` a `websearch` zakázané. Složené příkazy OpenCode rozdělí a zkontroluje každou část (`sh build.sh | head` zamítl). Ve všech 43 bězích OpenCode (25.–27. 9.) je v logu 0 přístupů mimo pracovní kopii.
- Vzory příkazů co nejpřesnější. Hvězdička za příkazem (`sh build.sh*`) je pohodlná, ale širší, než je nutné.

**4. Tajné údaje.**

- API klíče jen v proměnných prostředí a jen pro proces, který je potřebuje. Nikdy v deníku, zadání, konfiguraci v repozitáři ani v konverzaci.
- Při kontrole citlivých souborů vypisovat jen délky a shody, ne hodnoty.
- Pokud agent smí spouštět libovolné příkazy, může vypsat proměnné prostředí a klíč pošle modelu. I proto jen build.

**5. Sdílený server.** Správce má vědět, kdy test běží a co se tam posílá. Dlouhé a přerušené požadavky jinak vypadají v logu jako chyba.

**6. Kontrola po běhu:**

- prohledat výstupy a přepisy na domény, IP adresy, `root@` a tokeny;
- projít volání nástrojů s cestami mimo pracovní kopii (povolené i zamítnuté);
- po přerušení běhu ověřit, že nezůstal viset žádný proces agenta.

**7. Incident a jeho řešení.** Při testu povolení dostal Haiku omylem holé `Read` a přečetl `release.py` z originálního projektu. Doména, API cesty a `root@<IP>` serveru tak odešly do Anthropicu, tokeny ani `.env` ne.

- Oprava: holé `Read` pryč, čtení jen v pracovní kopii.
- Doporučení: SSH na server jen klíčem.
- Když data odejdou ven, říct to hned a konkrétně (co, kam), i když jde o vlastní chybu.

## Poučení z testů a z vlastních chyb

**Technická úskalí**

- **Instrukce navíc v kontextu (kontaminace):** Claude Code načítá `CLAUDE.md` ze všech nadřazených složek pracovní kopie a z `~/.claude`, OpenCode `AGENTS.md` / `CLAUDE.md` po kořen git repozitáře a globální pravidla. Pracovní kopie proto musí ležet **mimo strom projektu**, kde jsou poznámky nebo pravidla (u nás `C:\esp-bench-work`), a runner to musí před během ověřit. Poznámky k benchmarku obsahují nápovědy (u nás „chyby jen mimo OTA“).
- **Povolení a harness:**
  - Claude Code v nedůvěryhodné složce ignoruje projektové nastavení;
  - `powershell -File` nejde povolit pravidlem;
  - OpenCode mimo kořen git repozitáře zapisoval do dočasné složky;
  - malý model s 32k kontextem padal, protože si harness řekl o 32k výstupních tokenů.
- **Build:** skript mazal jen `.bin`, takže druhý build beze změn selhal. Patche s CRLF `git apply` odmítal.
- **Proměnlivý server:** během dvou dnů se vyměnily modely a rychlost stoupla z 28 na 43 tok/s. Časy mezi dny nesrovnávat.
- **Subagenti:** harness může pustit paralelní požadavky a kolo navíc po skončení hlavního agenta. Na serveru to vypadá jinak než jeden běh.
- **Úroveň přemýšlení:** harness ji nastavuje sám a jinak, než čekáte. Claude Code 2.1.220 posílá vždy `effort: high` (i Claude modelům) a `MAX_THINKING_TOKENS` ignoruje, mění ji jen `--effort`. OpenCode ji neposílá vůbec (model pak jede na výchozí úrovni), nastaví se `reasoningEffort`. Ověřovat zachycením požadavku na lokálním serveru, ne podle dokumentace. Model bez režimu úvah (qwen3-coder-next) úroveň ignoruje.
- **Rychlost hardwaru je součást výsledku:** lokální model na ~30 tok/s s vysokou úrovní přemýšlení nestihne úlohu v limitu, i když jí rozumí. Pro lokální modely měřit i nižší úroveň (u gpt-oss `medium` 5/8 proti `high` 1/8).

**Vlastní chyby autora benchmarku**

| Chyba | Následek | Poučení |
|---|---|---|
| kontroly zamítaly správné opravy (H2, H3, X4) | správná oprava by se počítala jako neúspěch | vzorové a chybné opravy v `--verify` |
| kontrola X2 nepoznala `_Atomic(const char *)` a Opusovu správnou opravu hodnotila jako neúspěch, i když vzorové opravy prošly | chybný výsledek za běhu | vzorové opravy nikdy nepokryjí vše: každý neúspěch silného modelu ručně prověřit; po opravě kontroly přehodnotit uložené diffy (`bench/rescore.py`) |
| vnesená chyba nešla přeložit (X1, `~` na `bool`) | úloha, která v praxi nenastane | `--verify` překládá i kopii s chybou |
| guard hlídal víc, než model věděl ze zadání | první běh X1–X4 přerušen po 6 bězích | pravidla v zadání = pravidla v guardu |
| pilot s nedůvěryhodnou složkou | modelům zakázaný build, neplatné výsledky | v pilotu číst přepisy, ne jen čísla |
| holé `Read` v povoleních | únik adres serveru do Anthropicu | nejužší povolení, audit po běhu |
| průběžné hlášení z neúplných dat („1/16“) | chybný mezivýsledek | závěry jen z finálních dat; sledování má hlásit úspěchy i neúspěchy |
| planý poplach o úniku (`device_config.h`) | zbytečné znepokojení | před poplachem ověřit v podkladech, hodnoty maskovat; poplach raději dřív než pozdě |
| „fail v logu“ jsem hledal v logu serveru, šlo o 1/2 v PDF | zbytečné pátrání | nejdřív se zeptat, odkud přesně hlášení je |
| založil jsem `CLAUDE.md` v kořeni projektu, zatímco pracovní kopie benchmarku ležela uvnitř | 16 běhů 2. kola v Claude Code dostalo poznámky projektu navíc k zadání, obsah odešel i ven | pracovní kopie mimo strom projektu; runner kontroluje instrukční soubory (`context_leaks`) a jinak odmítne běžet |
| guard hlídal jen chráněné soubory, nové soubory v `main/` povoloval | obejití pojistky OTA novým souborem guard nezachytil, zachránil to jen pevný seznam zdrojáků v CMake | guard hlídá i nová volání chráněných funkcí kdekoli; negativní test „nový soubor“ v `--verify`; po změně guardu `rescore.py` |

## Limity metody

- Malý vzorek úloh a opakování dává orientační výsledek, ne statistiku.
- Kontroly jsou statická analýza, ne spuštění kódu. Vzorové opravy to zmírňují. Silnější by byly testy na PC nebo v emulátoru.
- Malý projekt neprověří práci s velkým kontextem.
- Když úlohy i kontroly píše jeden z porovnávaných modelů, může mu to nahrávat. Lepší jsou reálné chyby nebo úlohy od člověka.
- Harness je stavěný pro určitý model. Claude Code je laděný na Claude, proto se lokální model měří i v jiném harnessu.

## Jak metoda obstála (ESPTest, 25.–27. 9. 2026)

| Úroveň | Co ukázala |
|---|---|
| B1–B4 (jedna chyba) | Claude modely 100 %, qwen3-coder-next 84. Na rozlišení silných modelů moc snadné, ale odhalily nebezpečnou „opravu“ OTA (use-after-free), kterou chytil jen guard. |
| H1–H3 (znalost platformy) | Všechny Claude modely 3/3. Stále nerozlišují. |
| X1–X4 (víc chyb, souběh, matoucí příznak, nová funkce) | **Rozlišily** (jen čisté běhy): Opus a Sonnet 8/8, Haiku 7/8, gpt-oss `medium` 3/4 a 2/4, qwen 2/4 a 2/8, gpt-oss `high` 1/4 a 0/4 (limit 15 min). Matoucí příznak u OTA (X3) žádný lokální model nevyřešil, čtyřikrát zasáhly do OTA nebo ji obešly. |

Závěry pro použití metody:

- Rozdíly se ukážou až u úloh, kde se musí propojit víc míst (souběh, příčina jinde než příznak). Snadné úlohy slouží jen jako kontrola, že vše funguje.
- Typy selhání říkají víc než skóre. U slabšího modelu převažovalo bloudění, zacyklení a porušování pravidel, ne špatný kód.
- Za tři dny se našly chyby v kontrolách pětkrát (H2, H3, X4, X2 a nepřeložitelná chyba X1). Ověřování kontrol vzorovými opravami a ruční prověření neúspěchů silných modelů jsou nutné, ne volitelné.
- Guard a nejužší povolení se vyplatily: všech 24 pokusů o čtení mimo pracovní kopii bylo zamítnuto a zásahy do OTA byly zachyceny. Guard ale měl díru (obejití OTA novým souborem), kterou odhalilo až ruční čtení diffů. Proto se diffy neúspěchů čtou, i když guard hlásí „OK“.

Podrobnosti a čísla jsou v deníku `denik/testovani benchmarku.md` a v PDF jednotlivých běhů.

## Kontrolní seznam před během

- [ ] Baseline bez tajných údajů, nasazovacích skriptů a skutečných adres; originál mimo dosah agenta
- [ ] Pracovní kopie mimo strom s `CLAUDE.md` / `AGENTS.md`; žádný globální `~/.claude/CLAUDE.md` (runner to kontroluje)
- [ ] Každá úloha: patch (kromě nové funkce), příznak, kontrola chování, vzorové a chybné opravy
- [ ] Zadání vyjmenovává vše, co hlídá guard
- [ ] `--verify` prošlo celé
- [ ] Ověřené modely na serveru, zapnuté správné konfigurace
- [ ] Nejužší povolení: jen build, žádné holé `Read`, OpenCode s `external_directory: deny`, bez webu
- [ ] Klíče jen v proměnných prostředí konkrétního procesu
- [ ] Pilot proběhl a přepisy jsou přečtené
- [ ] Správce serveru ví, kdy test běží
- [ ] Po běhu: ruční prověření neúspěchů (hlavně silných modelů), `failures.json`, případně `rescore.py` po opravě kontroly
- [ ] Po běhu: audit úniků (domény, IP, tokeny), přístupů mimo pracovní kopii a visících procesů; zápis do deníku
- [ ] Nic z výstupu agentů se nenasazuje bez lidské kontroly
