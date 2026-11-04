# SCIO CODE — instalace a ovládání (Windows x64)

## Doporučená instalace: jeden DIST ZIP

1. Stáhni **[SCIO-CODE-windows-x64.zip](https://github.com/vakatorsss/scio-opencode/releases/latest/download/SCIO-CODE-windows-x64.zip)** z posledního vydání.
2. Použij **Extrahovat vše**. Nespouštěj program přímo uvnitř ZIPu. Zachovej celou složku `SCIO CODE`, včetně `runtime`, `app` a `bin`.
3. Spusť **SCIO CODE.cmd**. Menu nabídne terminálové UI, konzoli, nastavení, projekt a přihlášení.
4. Zvol `p` a napiš cestu ke svému projektu, např. `C:\Projects\moje-aplikace`. Projekt nemusíš vybírat při každém spuštění.
5. Zvol `t` a vlož **vlastní** bearer token. Vstup je skrytý a token se uloží šifrovaně pomocí Windows DPAPI.
6. Enter otevře terminálové UI; `c` otevře konzoli se souběžnými relacemi. Začni třeba: „Prohlédni projekt a vysvětli, jak se spouští.“

ZIP obsahuje Python, závislosti, značkové terminálové UI a cloudflared. Není potřeba samostatně instalovat Python, OpenCode, Bun ani Node pro spuštění SCIO CODE. Git a nástroje konkrétního projektu (např. Node, kompilátor) si nainstaluj podle potřeb svého projektu. Model i objevování nástrojů potřebují internet a platný Scio účet. ZIP je přenosná složka, nikoli jediný samorozbalovací EXE.

## Kde získat token

Přihlas se na [chat.scio.cz](https://chat.scio.cz). V nástrojích pro vývojáře otevři Network, pošli vlastní zprávu a vyber požadavek `ai-chat`. V Request Headers zkopíruj hodnotu `Authorization: Bearer …`. Prefix `Bearer` můžeš ponechat. Token nesdílej; nevkládej ho do promptu, GitHubu ani argumentů příkazové řádky. Po vypršení použij v menu `t` nebo v konzoli `/token`. SCIO CODE neobchází přihlášení ani limity účtu.

## Nové ovladače podle testů endpointu

V menu zvol `s`. Zadej jeden řádek, například `locale cs`. Prázdný řádek tě vrátí zpět.

| Nastavení | Hodnoty | Význam |
| --- | --- | --- |
| `locale` | `en`, `cs` | Jazyková preference; posílá se při vytvoření chatu i v dalších zprávách. |
| `instructions` | vlastní text | Přidá instrukce do systémového promptu soukromého agenta; nenahrazuje nástroje ani jejich oprávnění. |
| `web_search` | `off`, `auto`, `on` | Konfigurace skilly `web-search`: zakázaná, dostupná nebo vždy zapnutá. Výchozí `off`. |
| `tone` | `balanced`, `direct` | Experimentální uložená preference; samostatný účinek nebyl prokázán. |
| `conciseness` | `balanced`, `short`, `detailed` | Experimentální uložená preference; není to limit délky. |
| `thinking` | `default`, `low`, `high` | Stávající preference přes serverový nástroj; potvrzení závisí na modelu. |
| `auto_allow` | `on`, `off` | Lokální oprávnění. `on` dovolí i zápisy, shell a síť bez dotazů. Výchozí `off`. |

Pro stručné odpovědi fungovaly při testech explicitní instrukce lépe než samotné `conciseness short`, například: `instructions Odpovídej česky. Shrnutí omez na 80 slov, pokud nepožádám o podrobnosti.` Jde o instrukci pro model, ne tvrdý limit.

Víceřádkové instrukce ulož jako UTF-8 text a použij `instructions-file C:\Projects\pravidla.txt`. `clear-instructions` je odstraní. Následující tabulka není úplný seznam backendových možností: nabízíme jen testované hodnoty. Přímé token caps, stop řetězce a JSON schema nebyly v testovaných požadavcích vynuceny; slider pro temperature, speed nebo service tier proto nepřidáváme.

Vyhledávání běží **na Scio serveru**, bez lokálních dotazů na oprávnění. Konfigurace skilly není bezpečnostní bariéra. `webSearch=false` samotné vyhledávání v testech nezastavilo, proto ho nepoužíváme jako blokaci. `auto` je mapování na pole `available`; živé behaviorální testy zprávy ověřily `off` a `on`, nikoli záruku chování `auto`. Ostatní vzdálené nástroje se nepředávají lokálnímu executorovi. Lokální file/shell/network oprávnění zůstávají oddělená.

Změny se použijí při **příštím spuštění UI** nebo pro **nové konzolové relace**. Běžící a uložené konzolové relace si ponechají svoje preference. Jejich subagenti je dědí; `/refresh` obnoví spojení, nepřepisuje nastavení a neopakuje úlohu. `/settings` ukáže výchozí i vybrané nastavení.

## Příkazy z PowerShellu

Ve složce rozbalené distribuce:

```powershell
& '.\SCIO CODE.cmd' settings set locale cs
& '.\SCIO CODE.cmd' settings set web_search off
& '.\SCIO CODE.cmd' settings set conciseness short
& '.\SCIO CODE.cmd' settings instructions-file 'C:\Projects\pravidla.txt'
& '.\SCIO CODE.cmd' project 'C:\Projects\moje-aplikace'
& '.\SCIO CODE.cmd' ui --model anthropic-strong
& '.\SCIO CODE.cmd' ui --locale en --web-search on --instructions 'Use English.'
& '.\SCIO CODE.cmd' console
& '.\SCIO CODE.cmd' doctor
```

Parametry `ui` a `console` platí pro jedno spuštění; `settings set` ukládá výchozí hodnoty. Modely: `auto`, `google-weak`, `google-strong`, `anthropic-strong`, `openai-weak`. Konkrétní model za aliasem určuje Scio. `doctor` zkontroluje lokální závislosti a verze bez volání účtu.

## Konzole, relace a subagenti

```text
/project C:\Projects\moje-aplikace
/locale cs
/search off
/instructions Odpovídej stručně a uváděj skutečné výsledky testů.
/set tone direct
/set conciseness short
/thinking high
/new Oprava testů
Zjisti, proč padají testy, a oprav příčinu.
/new Dokumentace
Prohlédni README a navrhni zlepšení. Neměň soubory, které upravuje jiný agent.
/sessions
/switch 1
/refresh
/agents
```

Více úloh může běžet současně. `/approve ID` a `/deny ID` vyřizují čekající lokální operace; `/auto on` schválí i již čekající dotazy. Agentům přiřazuj různé soubory. Limity `/set max_agents 8`, `/set max_depth 3`, `/set max_children 32` jsou lokální konzolové limity; UI má vlastní mechanismus task/subagent a používá hloubku a max_steps, nikoli všechny konzolové limity.

## Aktualizace a data

Zavři program, stáhni nejnovější ZIP a rozbal jej do **nové složky**. Uložený token, preference a relace distribuce zůstávají v `%LOCALAPPDATA%\SCIO CODE`. Nepřepisuj běžící EXE. Zástupce přesměruj na nový `SCIO CODE.cmd`. Proměnná `SCIO_DATA_DIR` umožňuje vlastní umístění dat.

Při přechodu ze starého zdrojového projektu můžeš na stejném Windows účtu zkopírovat jeho složku `scio_data` do `%LOCALAPPDATA%\SCIO CODE` před prvním spuštěním nové verze. Nepřepisuj existující novější data. DPAPI token z jiného Windows účtu nebude fungovat — přihlas se znovu. Zdrojové launchery stále používají vlastní `scio_data`, pokud nenastavíš `SCIO_DATA_DIR`.

## Potíže

- **401 / vypršel token:** v menu `t` ulož nový token. V konzoli pak `/refresh` pro neaktivní relaci.
- **403 / account_deleted_block_chat_personas:** server odmítá vytváření agentů pro daný účet. Přihlas se ke svému aktivnímu účtu nebo kontaktuj podporu Scio. Lokální přepínače tuto politiku nemohou změnit.
- **Tunnel timeout / MCP unavailable:** zkontroluj síť; veřejný dočasný tunnel může být nedostupný. Konzole uchová historii a `/refresh` zkusí nové spojení. Rozhraní poté spusť znovu. Úlohy se automaticky neopakují.
- **Chybí DLL nebo runtime:** rozbal celý ZIP, ne jen launcher. Spusť `doctor`.
- **Chybí Git / Node / nástroje projektu:** jejich instalace je oddělená od běhu SCIO CODE.
- **Nevidím nové nastavení v UI:** zavři UI i jeho adapter a spusť znovu. `/credits` uvádí OpenCode a licenci MIT.

## Sestavení ze zdrojů

Vývojářský postup: Python 3.10+, `python -m venv .venv`, `.venv\Scripts\python -m pip install -r requirements.txt`, pak `.venv\Scripts\python scio_app.py`. UI se ověřeně stáhne při prvním spuštění.

`python build_dist.py` vytvoří `dist/SCIO-CODE-windows-x64.zip` a SHA256 soubor. Používá připnuté oficiální runtime/tunnel balíčky, uzamčené wheel závislosti v `requirements-dist.lock` a explicitní seznam aplikačních souborů. Uživatelské tokeny, nastavení, chaty, výzkumné logy ani `.venv` do ZIPu nepatří. Python runtime je balen dle [oficiální dokumentace embeddable package](https://docs.python.org/3.14/using/windows.html#the-embeddable-package).

Ověření: `python -m unittest discover -s tests`, následně `python verify_dist.py`. Druhý příkaz rozbalí ZIP do dočasné složky a otestuje jeho vlastní runtime, konfiguraci a MCP soubory/Python bez Scio tokenu a bez systémového Pythonu na PATH. Živý test modelu je oddělený; v době přípravy 0.4.0 jej blokoval tunnel timeout a serverová politika účtu při vytváření persony. To neznamená nové živé potvrzení všech funkcí.
