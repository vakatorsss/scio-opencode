# SCIO CODE

SCIO CODE je lokální konzolový coding agent pro Scio s nativními nástroji, uloženými relacemi a souběžnými subagenty. Spusť **`SCIO CODE UI.cmd`** pro značkové terminálové rozhraní, nebo **`SCIO CODE.cmd`** pro naši příkazovou konzoli. Původní launchery zůstávají funkční.

## Auto-allow, model a subagenti

```text
/project C:\Projects\my-app
/auto on
/thinking high
/model anthropic-strong
/set max_agents 8
/set max_depth 3
/set max_children 32
/set max_steps 30
/new Implementace
Rozděl práci mezi dva subagenty, přiděl jim různé soubory a zkontroluj jejich výsledky.
/agents
/settings
```

`/auto on` automaticky schválí nástroje včetně zápisů, síťových požadavků a shellu; zapnutí schválí i aktuálně čekající žádosti. `/auto off` obnoví dotazy pro další operace (již běžící příkaz nezastaví). Nastavení se ukládá lokálně a platí i pro subagenty. Nástroje stále kontrolují vybrané cesty, ale shell běží s právy tvého účtu, nikoli v OS sandboxu. Pro jediné spuštění použij `--auto-allow` nebo `--no-auto-allow`; přepínač sám trvalé nastavení nemění.

| Nastavení | Ověřený význam |
| --- | --- |
| `/model auto` | Výběr modelu nechá na Scio. |
| `/model google-weak` | Varianta Flash; frontend ji popisuje jako rychlou výchozí volbu. |
| `/model google-strong` | Varianta Pro. |
| `/model anthropic-strong` | Alias pro model Anthropic; konkrétní nasazení určuje Scio. |
| `/model openai-weak` | Alias pro model OpenAI. |
| `/thinking low`, `/thinking high` | Požádá skutečný serverový nástroj `set_thinking_level` o nastavení pro každý tah. Jde o modelově zprostředkovaný nástroj, ne přímý parametr sampling API. Pokud model nastavení nepotvrdí, klient vypíše upozornění a pokračuje se serverovým nastavením. |
| `/thinking default` | Nevnucuje úroveň přemýšlení. |
| `/set max_steps N` | Lokální limit kol nástrojů: 1–100. |
| `/set max_agents N` | 1–32 současně běžících relací v nativní konzoli, včetně rodičů čekajících na děti. Výchozí 8. |
| `/set max_depth N` | 0–8 úrovní vnořených subagentů. Výchozí 3; 0 zakáže děti. |
| `/set max_children N` | Celkový počet vytvořených potomků jednoho kořenového úkolu: 0–128, výchozí 32. |

Model a thinking se nastavují pro **nové** relace; existující relace a jejich potomci mají vlastní uloženou hodnotu. Auto-allow a limity lze měnit během práce. Snížení limitu nezruší už běžící úkoly. `/settings` ukáže aktuální konfiguraci i nepodporované parametry.

Při kontrole 4. 11. 2026 nebyly v cestě frontend → chat API nalezeny ovladače `temperature`, `top_p`, inference token budget, service tier ani samostatná rychlost. Nejsou zde falešné přepínače pro tyto parametry. Čísla kontextu a maximálního výstupu v katalogu modelů jsou metadata, ne ověřené editovatelné parametry. Podrobnosti a zdroje: [MODEL-SETTINGS.md](MODEL-SETTINGS.md).

Nativní agent má 99 workspace nástrojů plus `agent_spawn`, `agent_status`, `agent_wait`, `agent_list`, `agent_followup`. Dítě smí vytvořit další děti, pouze v rámci limitů, se stejným projektem a stejnou permission policy. Spawn vrací ID okamžitě; `agent_wait` čeká nejvýše 30 sekund a vrací skutečný stav/výsledek. Agent smí ovládat jen své potomky. Identický spawn stejného rodiče se deduplikuje, aby opakovaná odpověď modelu nespustila duplicitní práci. Pro nový nezávislý úkol použij jiný název nebo prompt; pro pokračování `agent_followup`. Agenti sdílejí soubory, proto jim přiděluj různé soubory. Výstupy se ukládají do lokálního seznamu relací (max. 30 000 znaků na výsledek).

Jednorázová automatická práce se stejnými subagenty:

```powershell
.\.venv\Scripts\python.exe scio_code.py --workspace "C:\Projects\my-app" --auto-allow --thinking low --max-agents 8 --prompt "Rozděl analýzu mezi dva subagenty a shrň výsledky."
```

### Terminálové rozhraní SCIO CODE

`start_scio_opencode.cmd --auto-allow --thinking high` spustí rozhraní **SCIO CODE** s vlastním logem, názvem okna a výchozím agentem. Totéž dělá `SCIO CODE UI.cmd`. Při prvním spuštění stáhne ověřený Windows x64 build z GitHub Releases tohoto projektu. Launcher zapíná ověřený přepínač `OPENCODE_EXPERIMENTAL_BACKGROUND_SUBAGENTS=true`, worker `scio-worker` má povolený `task` pro další delegování a `subagent_depth` přebírá nastavenou hloubku. Agenti mohou použít `task(background=true)` pro nezávislé souběžné úkoly. `max_agents` a `max_children` jsou limity naší nativní konzole, nikoli limity upstream OpenCode. Nastavení načte launcher při startu; po změně jej restartuj.

Rozhraní je sestavené z veřejného MIT-licencovaného OpenCode v1.19.3 s naším branding patchem; nepoužívá uniklý kód. Logo, titulky, CLI nápověda, provider a hlavní agent používají SCIO CODE. Copyright a licence upstream projektu zůstávají v `branding/OPENCODE-LICENSE.txt` a distribučním ZIPu. Interní API, provider ID `scio-native`, názvy konfiguračních souborů a názvy externích služeb zůstávají kompatibilní. Automatický upstream updater a příkazy upgrade/uninstall byly v našem UI odpojeny, aby nepřepsaly build nebo neodstranily samostatnou instalaci OpenCode. Aktualizace: `git pull`; pro přestavbu viz níže.

Build ze zdroje (Git + Python, Windows x64):

```powershell
.\.venv\Scripts\python.exe build_scio_ui.py
```

Builder ověří konkrétní upstream commit, stáhne ověřený Bun, aplikuje `branding/scio-code.patch`, nainstaluje zamčené závislosti a vytvoří `scio_data/bin/scio-code/scio-code.exe`. První sestavení stahuje několik tisíc balíčků a trvá déle než instalace hotového ZIPu. Webové rozhraní se do tohoto terminálového buildu nevkládá. Pro vlastní kompatibilní binárku lze stále použít `--opencode PATH`.


## Souběžné relace a nastavení projektu v konzoli

`start_scio_code.cmd` otevře konzoli bez úvodního dotazu na složku a bez čekání na připojení ke Scio. Připojení se vytvoří až při první zprávě. Při prvním použití zadejte vlastní bearer token pomocí `/token` (nebo při první zprávě).

```text
/project C:\Projects\my-app
/new Oprava aplikace
Prohlédni projekt a vysvětli jeho strukturu.
/new Druhý úkol
Přečti README a navrhni doplnění.
/sessions
/switch 1
/refresh
```

- `/project PATH` uloží výchozí složku pro nové relace. Běžící relace si ponechají původní projekt. Cesta může obsahovat mezery, uvozovky jsou volitelné.
- `/new [název]` vytvoří a vybere novou relaci; zprávy se zpracovávají na pozadí. Do stejné relace nelze poslat další úkol, dokud předchozí neskončí.
- `/sessions` zobrazí uložené relace a stav běhu. `/switch N` nebo `/resume N` vybere relaci podle čísla. Relace vytvořené touto konzolí zůstávají dostupné po restartu.
- `/refresh` znovu připojí vybranou nečinnou relaci: obnoví HTTPS tunel, znovu zaregistruje nástroje a načte uložený token. Zachová ID chatu a záznamy provedených nástrojů. `/refresh all` obnoví nečinné relace souběžně; běžící přeskočí. Refresh neopakuje přerušený úkol ani provedené zápisy.
- `/token` bezpečně nahradí uložený bearer token. Poté použijte `/refresh`. Samotný bearer token neumožňuje automatické obnovení přihlášení po expiraci. Proměnná `SCIO_TOKEN`, pokud je nastavena, má přednost před uloženým tokenem.
- `/model ID` vybere model pro nové relace.
- `/permissions` vypíše čekající žádosti. `/approve ID` nebo `/deny ID` rozhodne o konkrétní operaci. Každá žádost obsahuje ID relace a argumenty; běžící úkoly nikdy samy nečtou vstup konzole.
- `/quit` zamítne čekající žádosti a počká na bezpečné dokončení rozpracovaných požadavků. Násilné ukončení procesu může zanechat nejistý stav operace; ochrana proti opakovanému spuštění zůstává aktivní.

`start_scio_opencode.cmd` také nevyžaduje úvodní zadávání složky: použije projekt uložený pomocí `/project`, případně aktuální složku. Explicitní `--workspace "C:\Projects\other"` má přednost. Každé spuštění launcheru dostane vlastní volný port a konfigurační soubor. V OpenCode lze používat více chatů; nezávislé konverzace již nejsou blokované jedním globálním zámkem adaptéru. Konverzace se stejným modelem, katalogem, instrukcemi a první uživatelskou zprávou sdílejí zámek; pro dva nezávislé úkoly použijte odlišnou první zprávu.

Interaktivní Scio konzole vytváří pro každou připojenou relaci samostatný tunel a soukromého agenta. Pevný `--public-url`/`--discovery-port` používejte s jednorázovým `--prompt`, nikoli se souběžnou konzolí. Starší historie `native-cli` se automaticky nepřevádí do nového seznamu relací; zůstává uložená na disku a chaty jsou dostupné ve Scio.


**Nové: nativní Scio coding klient s 99 skutečnými lokálními nástroji a automatickým spuštěním OpenCode.**

Používá strukturované MCP tool calls ze Scio. Starší JSON-emulovaný adaptér zůstává dostupný níže.

## Nejrychlejší instalace — nativní klient

Na Windows x64 nainstaluj [Python 3.10+](https://www.python.org/downloads/windows/) s Python launcherem `py`. Stáhni tento repozitář přes **Code → Download ZIP**, rozbal ho a spusť:

- **`start_scio_opencode.cmd`** — otevře značkové SCIO CODE UI založené na OpenCode 1.19.3 s nativním Scio providerem a 99 workspace nástroji.
- **`start_scio_code.cmd`** — jednodušší terminálový coding klient bez OpenCode.

V konzoli nastav složku příkazem `/project PATH`. Při prvním použití zadej vlastní **Scio bearer token**. Zadávání tokenu je skryté. Na Windows se ukládá šifrovaně pomocí DPAPI pro tvého Windows uživatele. Další spuštění jej načtou. Po expiraci je nutné zadat nový token; nejde o automatické obnovení přihlášení.

Launchery vytvoří lokální `.venv`, nainstalují Python závislosti a stáhnou chybějící `cloudflared`. UI launcher navíc stáhne značkový SCIO CODE build, pokud není lokálně sestavený. Stažené archivy/binary ověřuje proti SHA-256 v GitHub release příslušného vydavatele. OpenCode 2.x není tímto launcherem podporován; lze zadat konkrétní v1 executable přes `--opencode`.

**Nejde o fork ani uniklý zdrojový kód Claude Code.** Používá se veřejný open-source OpenCode s naším branding patchem a náš vlastní provider/klient. Není potřeba Anthropic API klíč.

### Ruční spuštění

```powershell
git clone https://github.com/vakatorsss/scio-opencode.git
cd scio-opencode
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# OpenCode s nativním Scio modelem a nástroji:
.\.venv\Scripts\python.exe launch_opencode.py --workspace "C:\Projects\MojeAplikace"

# Samostatný terminálový klient:
.\.venv\Scripts\python.exe scio_code.py --workspace "C:\Projects\MojeAplikace"
```

První zpráva v relaci zkontroluje dostupnost nativních nástrojů skutečným, neškodným tool callem. Zřízení tunelu a kontrola mohou chvíli trvat. V terminálovém klientu jsou příkazy `/new`, `/chats`, `/resume NUMBER`, `/model ID`, `/tools`, `/quit`. Chaty a výsledky nástrojů se ukládají do `scio_data/`; tento adresář nepublikuj.

Příklad úkolu: „Přečti projekt, oprav chybu v parseru, přidej vhodný test a spusť jej.“

Model lze zvolit přes `--model anthropic-strong`, `openai-weak`, `google-strong`, `google-weak` nebo `auto`. Přesné verze a dostupnost modelů určuje Scio.

### Co dělá těch 99 nástrojů

Katalog obsahuje skutečné implementace pro soubory a editace, Git, Python, spouštění testů a příkazů, HTTP GET/HEAD, ZIP/GZIP, CSV/JSON, textové transformace a informace o projektu/systému. Kompletní názvy, vstupní schémata a druh oprávnění jsou v [`tool-catalog.json`](tool-catalog.json). Výpis bez tokenu a sítě:

```powershell
.\.venv\Scripts\python.exe scio_code.py --workspace "C:\Projects\MojeAplikace" --list-tools
```

Nejde o neomezený přístup ke všem aplikacím. Není zde GUI automatizace, přihlášení do služeb, ovládání prohlížeče ani administrátorská oprávnění. Obecné příkazy umožňují použít další nainstalované vývojářské nástroje.

### Oprávnění

- Souborové nástroje pracují uvnitř zvolené složky. Blokují únik přes `..`/symlinky a vybrané cesty s přihlašovacími údaji (`.env*`, `.ssh`, `scio_data` atd.). Nejde o OS sandbox.
- Terminálový klient automaticky dovoluje čtení; před zápisem, příkazem nebo HTTP požadavkem se ptá. V neinteraktivním režimu neodsouhlasenou operaci odmítne.
- `--allow-write`, `--allow-exec`, `--allow-network` výslovně předem schválí příslušnou kategorii pro daný běh. **Příkazy a Python kód mají oprávnění tvého OS účtu a mohou přistupovat mimo workspace.**
- OpenCode používá vlastní schvalování. Vygenerovaná konfigurace povoluje čtecí MCP nástroje, ostatní MCP nástroje, shell a editace žádají souhlas. Existující globální/projektová nastavení mohou ovlivnit výsledná pravidla.
- Lokální stdio MCP server `workspace_mcp.py` spoléhá na oprávnění svého hostitele, tedy OpenCode; nepublikuj jej jako veřejný execution server.

### Jak funguje nativní propojení

1. Klient vytvoří soukromého Scio agenta a zapíše jeho `mcp_servers`.
2. Dočasný Cloudflare Quick Tunnel zpřístupní **pouze popisy a schémata nástrojů**. Veřejný endpoint nikdy nespouští příkazy, nečte soubory a nemá Scio token. Registry mají náhodné URL cesty. Cloudflare zprostředkovává tento discovery provoz.
3. Scio vrátí `tool-input-available`. Názvy používají prefix `local_`, aby nekolidovaly s vestavěnými Scio nástroji.
4. Terminálový klient nebo OpenCode nástroj lokálně vykoná až po schválení.
5. Skutečný výsledek se odešle přes `submit-tool-result`. Protože Scio po výsledku často automaticky nepokračuje, klient pošle navazující zprávu a pokračuje v původním úkolu.

Scio aktuálně při automatickém MCP execution vrací i chybu `Attempted to send a request from a closed client`. Náš klient na tomto serverovém execution nespoléhá. Vestavěné Scio workspace skills jsou na vytvořeném agentovi vypnuté, aby nepřesměrovaly práci do jiného prostředí.

Při ukončení klient vypne tunel a vymaže MCP připojení svého agenta; soukromý agent a chaty zůstanou pro historii. Po tvrdém pádu se tento úklid nemusí dokončit. Restart znovu připojí uloženého agenta. Tool ledger brání opakovanému vykonání stejného call ID; přerušený příkaz se automaticky nespouští znovu. Nové call ID ale může představovat nový požadavek na stejnou operaci, proto kontroluj schvalované změny.

### Použití s existujícím OpenCode Desktop

```powershell
.\.venv\Scripts\python.exe scio_code.py --workspace "C:\Projects\MojeAplikace" --serve-opencode
```

Provider běží na `http://127.0.0.1:8767/v1`. Skript vytvoří `scio_data/opencode.native.json` obsahující provider `scio-native` a MCP `scio_workspace`. Slouč tyto položky a pravidla oprávnění do své OpenCode **1.x** konfigurace, restartuj aplikaci a vyber `scio-native/anthropic-strong`. Existující konfigurace se automaticky nepřepisuje. CLI launcher používá vlastní `scio_data/opencode.native.<instance>.json` přes `OPENCODE_CONFIG` a automaticky zvolený port. Jeho záznamy nástrojů jsou oddělené podle spuštění v `native-provider-runs`; rozpracovaný tool roundtrip nepřenášejte mezi dvěma spuštěními launcheru.

Pro vlastní HTTPS reverse proxy lze použít `--public-url https://YOUR-HOST --discovery-port 8778`. Proxy musí směrovat na discovery port, nikoli na provider. Jinak se dočasný tunel obstará automaticky.

### Ověření a omezení

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Živě ověřeno s Anthropic: nativní čtení lokálního spec souboru, zápis Python modulu a unit testu, spuštění testu, následná odpověď s přesným náhodným kontrolním řetězcem ze souboru. Test byl nezávisle znovu spuštěn úspěšně. Lokální testy kontrolují schémata, oprávnění, cesty, ZIP traversal, edit konflikty, timeout a ochranu před opakováním stejného call ID. Test symlinků může být na Windows přeskočen bez potřebného oprávnění.

Také ověřeno přímo v oficiálním **OpenCode CLI 1.19.3**: připojení lokálního MCP katalogu, nativní `scio_workspace_read_file`, odeslání skutečného výsledku do Scio a odpověď se shodným kontrolním řetězcem. To není záruka každého nástroje a modelu; katalog nabízí 99 implementací, ale ne všechny byly jednotlivě otestovány proti živému modelu.

Provider je textový a odpověď bufferuje před vydáním OpenAI-compatible SSE; nepodporuje obrazové/audio vstupy, přesné tokenové usage ani plnou Anthropic Messages API. Zachovává konverzaci pomocí lokálního stavu; pokud stav ztratíš, začni nový chat. Scio pravidla a limity účtu nadále platí. Rozhraní Scio není stabilní veřejné API a při jeho změně může být potřeba adaptér opravit.

---

## Starší režimy a podrobnosti získání tokenu

Následující návod popisuje původního konzolového klienta, JSON-emulovaný modelový adaptér a MCP server pro volání Scio z jiného modelu. Pro nové nativní propojení použij postup výše.

Tento projekt umožňuje používat vlastní účet na [chat.scio.cz](https://chat.scio.cz) z Pythonu a připojit jej k [OpenCode](https://opencode.ai). **Není to oficiální klient Scio ani oficiální integrace OpenCode.** Vychází z chování veřejného webového klienta; při změně jeho rozhraní může přestat fungovat.

## Co program umí

| Režim | K čemu slouží | Spuštění |
|---|---|---|
| Konzole | Psaní zpráv, nové chaty, ukládání ID chatů a výběr modelu | `scio_console.py` |
| Modelový adaptér | Scio se objeví přímo ve výběru modelů OpenCode | `scio_provider.py` |
| MCP | Jiný model v OpenCode může zavolat Scio jako nástroj | `scio_console.py --mcp stdio` |

**Chceš používat Scio jako hlavní model v OpenCode? Postupuj podle kroků 1–6. MCP je volitelná alternativa a pro modelový adaptér není potřeba.**

Ověřeno na Windows s Pythonem 3.13, MCP SDK 1.30.0 a OpenCode Desktop 1.19.3: textová odpověď, formát SSE, volání nástroje a navazující zpracování jeho výsledku. V samotném OpenCode prošel test `SCIO_READY`. Nejde o záruku funkčnosti všech modelů a všech nástrojů.

## 1. Požadavky a instalace OpenCode

Potřebuješ:

- Windows 10/11 a vlastní přihlášení do Scio s přístupem k chatu.
- [Python 3.10 nebo novější](https://www.python.org/downloads/windows/). Doporučená je běžná aktuální podporovaná verze. Při instalaci zapni přidání Pythonu do PATH.
- [Git](https://git-scm.com/downloads/win), nebo stáhni tento repozitář přes **Code → Download ZIP**.
- OpenCode. Níže uvedená konfigurace je pro **OpenCode 1.x**; OpenCode 2 má jiné schéma konfigurace.

### OpenCode Desktop — nejjednodušší možnost

1. Otevři [oficiální stránku OpenCode ke stažení](https://opencode.ai/download).
2. Vyber instalátor pro Windows a nainstaluj aplikaci.
3. Spusť ji a otevři existující složku projektu, například `C:\Projects\Test`.
4. Ověř verzi aplikace. Tento návod byl prakticky ověřen s Desktop 1.19.3. Pokud instaluješ verzi 2, použij její [návod k providerům](https://opencode.ai/v2/docs/providers); v1 konfiguraci do ní nekopíruj beze změny.

### OpenCode v terminálu — alternativa

Nainstaluj [Node.js LTS](https://nodejs.org), otevři nový PowerShell a spusť:

```powershell
npm install -g opencode-ai
opencode --version
```

Tento způsob je uveden v [oficiálním návodu OpenCode 1](https://opencode.ai/docs/). Verze 1 a 2 používají stejný příkaz `opencode`; neinstaluj je současně pod výchozím názvem příkazu.

V tomto projektu používej **nativní Windows Python**, pokud chceš ukládat token přes Windows DPAPI. Token uložený ve Windows nelze automaticky načíst Pythonem ve WSL.

## 2. Stažení a instalace programu

V PowerShellu:

```powershell
git clone https://github.com/vakatorsss/scio-opencode.git
cd scio-opencode
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Pokud příkaz `py` neexistuje, použij `python -m venv .venv`. Instalaci ověř pomocí `python --version`.

Při použití ZIP jej nejdřív rozbal, otevři PowerShell v rozbalené složce a spusť poslední dva instalační příkazy. Skripty nespouštěj přímo ze ZIP archivu.

Virtuální prostředí nemusíš aktivovat. Díky úplnému názvu `.\.venv\Scripts\python.exe` není potřeba měnit PowerShell Execution Policy.

## 3. Přihlášení vlastním Scio tokenem

1. Otevři [Scio chat](https://chat.scio.cz) a přihlas se vlastním účtem.
2. Stiskni **F12**, přepni na **Network / Síť** a odešli krátkou zprávu.
3. Najdi požadavek `ai-chat` na `www.sciobot.cz/functions/v1/ai-chat`.
4. V **Request Headers / Hlavičky požadavku** zkopíruj hodnotu `Authorization: Bearer …`. Kopíruj hodnotu za názvem hlavičky; prefix `Bearer ` můžeš ponechat.
5. V PowerShellu spusť:

```powershell
.\.venv\Scripts\python.exe scio_console.py
```

6. Vlož token do skrytého vstupu a potvrď Enterem. Při psaní ani vložení se token nezobrazuje — to je správně.
7. Menu můžeš opustit volbou `Q`. Uložený token zůstane dostupný adaptéru.

Token je přístupový údaj k tvému účtu. Nevkládej ho do README, issues, screenshotů ani OpenCode promptu. Program ho ukládá jako `scio_data/token.dpapi`, zašifrovaný pro aktuální Windows účet. Veřejný aplikační klíč v Python kódu sám o sobě nepřihlašuje uživatele.

Token může vypršet. V konzoli pak použij **T** a vlož nový. Program automaticky neobnovuje přihlášení a neobchází oprávnění ani limity účtu.

### Konzolové menu

| Volba | Funkce |
|---|---|
| `N` | Vytvoří skutečný nový chat na Scio a uloží jeho ID lokálně |
| `A` | Přidá ID existujícího chatu do místního seznamu |
| číslo | Otevře chat ze seznamu |
| `M` | Zvolí výchozí model pro nové chaty |
| `T` | Nahradí uložený token |
| `F` | Smaže uložený token a ukončí program; nemaže chaty na serveru |
| `Q` | Ukončí program |
| `/model` | Uvnitř chatu změní jeho uložený model |
| `/back` | Vrátí se z chatu do menu |

Ukládání chatů zde znamená ukládání **ID, názvu a modelu**, nikoliv úplnou offline zálohu zpráv. Zprávy jsou na Scio. ID existujícího chatu je část adresy za `/chat/`.

## 4. Přidání Scio jako modelu do OpenCode

Nejprve vygeneruj konfiguraci:

```powershell
.\.venv\Scripts\python.exe configure_opencode.py
```

Vzniknou:

- `opencode.local.json` — konfigurace pro OpenCode 1 s konkrétní cestou k lokálnímu klíči.
- `scio_data/provider-key.txt` — nový náhodný klíč pouze pro lokální adaptér. **Není to Scio bearer token.**

Generátor nic nepřepisuje v existujícím nastavení OpenCode. Konfigurace odkazuje na klíč pomocí `{file:…}`; tento zápis podporuje [konfigurace OpenCode](https://opencode.ai/docs/config/).

### Pokud ještě nemáš konfiguraci OpenCode

Vytvoř složku a zkopíruj soubor:

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.config\opencode" | Out-Null
Copy-Item .\opencode.local.json "$env:USERPROFILE\.config\opencode\opencode.json"
```

**Tento postup použij pouze tehdy, pokud v cíli nemáš vlastní `opencode.json` ani `opencode.jsonc`.** Existující nastavení zachovej podle následujícího postupu.

### Pokud už konfiguraci máš

1. Zálohuj svůj `opencode.json` nebo `opencode.jsonc` v `%USERPROFILE%\.config\opencode`.
2. Otevři jej a vygenerovaný `opencode.local.json` v editoru.
3. Přidej objekt `provider.scio` do existujícího objektu `provider`. Ostatní providery ponech.
4. Volitelně nastav hlavní hodnotu `"model": "scio/openai-weak"`, pokud má být Scio výchozí model.
5. Nevytvářej druhý objekt `provider` na stejné úrovni JSON.
6. OpenCode úplně zavři a znovu spusť. Pouhé obnovení stránky aplikace nemusí načíst nový seznam providerů.

Pokud složku programu později přesuneš, spusť generátor znovu a aktualizuj cestu ke klíči v konfiguraci. Klíč nepřidávej do Gitu. Projektová konfigurace může přepsat globální nastavení; při problémech zkontroluj také konfiguraci v otevřeném projektu.

## 5. Spuštění modelového adaptéru

```powershell
.\.venv\Scripts\python.exe scio_provider.py
```

Nebo dvojklikem spusť `start_scio_provider.cmd`. Nech jeho okno otevřené.

Adaptér poslouchá pouze lokálně na:

```text
http://127.0.0.1:8766/v1
```

Ověření běhu z druhého PowerShellu:

```powershell
Invoke-RestMethod http://127.0.0.1:8766/health
```

Očekávaný výsledek obsahuje `status: ok` a `tool_mode: json-emulated`. Health endpoint ověřuje běh programu, ne platnost Scio tokenu.

Běží jen do zavření okna nebo ukončení procesu. **Není nainstalovaný jako služba a po restartu počítače se nespouští sám.** Ukončíš ho pomocí Ctrl+C. Spouštěj pouze jednu kopii na portu 8766.

## 6. Použití v OpenCode

1. Nech běžet adaptér.
2. V OpenCode otevři existující projekt. Cesta na odpojený disk zabrání spuštění chatu.
3. Klikni na výběr modelu a vyhledej **Scio**. V terminálové verzi použij `/models`.
4. Vyber například **Scio OpenAI**.
5. Odešli test:

```text
Odpověz přesně SCIO_READY. Nepoužívej nástroje a nečti soubory.
```

Po úspěšném testu zadávej úlohy běžně, například „Vysvětli tento kód“ nebo „Navrhni testy pro tuto funkci“. Oprávnění pro čtení, zápis a spouštění nástrojů dál řídí OpenCode.

### Výběr modelu

| ID posílané Scio | Název v OpenCode |
|---|---|
| `auto` | Scio Automatic |
| `google-weak` | Scio Google / Flash |
| `google-strong` | Scio Google / Pro |
| `anthropic-strong` | Scio Anthropic |
| `openai-weak` | Scio OpenAI |

Jde o aliasy z webového klienta Scio, nikoliv záruku konkrétní verze modelu. Skutečné směrování a dostupnost určuje Scio a oprávnění účtu. Lokální výběr neobchází předplatné.

## Volitelné: MCP nástroje

MCP připojení **nepřidá Scio do výběru modelů**. Zpřístupní nástroje, které může volat jiný zvolený model. Obsahuje `list_models`, `list_chats`, `create_chat` a `send_message`.

### Stdio — OpenCode server spustí samo

Do konfigurace OpenCode 1 přidej následující objekt `mcp.scio`. Cesty nahraď skutečnými absolutními cestami ke své instalaci:

```json
{
  "mcp": {
    "scio": {
      "type": "local",
      "command": [
        "C:/Projects/scio-opencode/.venv/Scripts/python.exe",
        "C:/Projects/scio-opencode/scio_console.py",
        "--mcp",
        "stdio"
      ],
      "cwd": "C:/Projects/scio-opencode",
      "enabled": true,
      "timeout": 300000
    }
  }
}
```

Token musí být uložený předem. MCP se na něj interaktivně neptá. `cwd` musí existovat; neplatná pracovní složka může zabránit spuštění procesu.

### HTTP — ruční spuštění endpointu

```powershell
.\.venv\Scripts\python.exe scio_console.py --mcp http --port 8765
```

```json
{
  "mcp": {
    "scio": {
      "type": "remote",
      "url": "http://127.0.0.1:8765/mcp",
      "enabled": true,
      "oauth": false,
      "timeout": 300000
    }
  }
}
```

MCP endpoint na portu 8765 nemá vlastní aplikační autentizaci. Používej ho jen na svém počítači; nepublikuj ho přes tunel ani reverzní proxy. V připojeném klientu umožňuje pracovat s tvým Scio účtem. Modelový endpoint na portu 8766 naopak vyžaduje samostatný lokální klíč.

Příklad promptu: „Použij Scio nástroje, vytvoř chat Test s modelem openai-weak a zeptej se, co je Python dekorátor.“

Podrobnosti: [OpenCode MCP](https://opencode.ai/docs/mcp-servers/). V2 používá jiné schéma, viz [MCP pro OpenCode 2](https://opencode.ai/v2/docs/mcp-servers/).

## Jak adaptér funguje a jaká má omezení

```text
OpenCode → lokální /v1/chat/completions → Scio chat → převod odpovědi → OpenCode
```

- Převádí textové zprávy na Scio chat. **Obsah konverzace včetně přiloženého kódu a výsledků nástrojů se odesílá Scio.** Není to lokálně běžící jazykový model.
- Pro každý požadavek vytváří nový Scio chat a posílá celý dodaný přepis. Tím nepromíchá historii různých větví OpenCode, ale vzniká více chatů a spotřebovává se kvóta účtu.
- Systémové zprávy OpenCode jsou serializované do uživatelské zprávy Scio. Vlastní systémové instrukce Scio zůstávají v platnosti; není zaručena plná shoda s nativním API modelu.
- Volání nástrojů jsou **emulovaná pomocí JSON**. Adaptér kontroluje název nástroje a argumenty podle dodaného JSON schématu. Nástroj následně vykonává OpenCode, nikoliv adaptér.
- **Scio Anthropic může odmítat práci s projektem jako úlohu mimo ScioBot.** V testech umělo požádat o nástroj v novém chatu, ale při zahrnutí předchozího odmítnutí v historii odmítalo dál. Začni nový chat v OpenCode; pro práci s nástroji byl v těchto testech spolehlivější Scio OpenAI. Změna promptu nemůže zaručit odstranění omezení na straně Scio.
- JSON emulace může selhat. Chybný nebo neznámý nástroj je odmítnut; úspěšný jednoduchý test nedokazuje spolehlivost dlouhých autonomních úloh.
- Odpověď se nejdřív celá shromáždí. Režim `stream=true` vrací kompatibilní SSE formát, ale nejde o průběžné zobrazování jednotlivých tokenů ze Scio.
- Podporovaný vstup je text. Obrazové, zvukové a souborové části API nejsou podporované.
- Limit serializovaného kontextu je 500 KB. OpenCode má nastavený konzervativní limit 32 000 tokenů, ale adaptér nevrací přesné počty spotřebovaných tokenů.
- Parametry jako teplota a maximum výstupních tokenů nejsou předávány; řídí je Scio. `n` musí být 1. Endpoint `/v1/responses` není implementovaný.
- Zrušení požadavku v klientovi nemusí zastavit práci na Scio. Při chybě před opakováním zkontroluj chat, aby nedošlo k duplicitní práci.
- Lokální soubory se sdíleným stavem nejsou určené pro současný zápis z více nezávislých instancí konzole/MCP.

## Uložené soubory a bezpečné sdílení

| Soubor | Obsah |
|---|---|
| `scio_data/token.dpapi` | Scio token zašifrovaný pro Windows účet |
| `scio_data/provider-key.txt` | Lokální klíč modelového endpointu v prostém textu |
| `scio_data/chats.json` | ID a názvy chatů z konzole/MCP |
| `scio_data/settings.json` | Výchozí model konzole |
| `scio_data/provider-sessions.jsonl` | ID Scio chatů vytvořených adaptérem |
| `opencode.local.json` | Vygenerovaný konfigurační fragment s lokální cestou |

`.gitignore` tyto soubory i `.venv` vylučuje. Do sdíleného repozitáře je nepřidávej přes `git add -f`. Šifrování tokenu nechrání před programy spuštěnými pod stejným Windows účtem. Příkaz `F` odstraní jen lokální token; pro odvolání přístupu použij možnosti účtu Scio.

Na jiných systémech lze token předat proměnnou `SCIO_TOKEN`, ale interaktivní ukládání přes DPAPI a Windows launcher tam nefungují. Tento repozitář je primárně otestovaný pro Windows.

## Řešení problémů

| Problém | Co zkontrolovat |
|---|---|
| `python` nebo `py` nebyl nalezen | Nainstaluj Python a otevři nový terminál; ověř `python --version`. |
| `No module named mcp/jsonschema` | Instaluj `requirements.txt` stejným `.venv` Pythonem, kterým program spouštíš. |
| Token není při vložení vidět | Skrytý vstup je záměrný. Vlož token a stiskni Enter. |
| HTTP 401/403 od Scio | Obnov token přes konzoli volbou `T`; ověř přístup ke zvolenému chatu/modelu. |
| HTTP 401 od lokálního portu 8766 | Ověř odkaz na `provider-key.txt`; nezaměňuj ho se Scio tokenem. |
| Connection refused / nelze se připojit | Spusť `scio_provider.py` a ověř `/health`. Pro MCP HTTP musí zvlášť běžet port 8765. |
| Port již používán / WinError 10048 | Pravděpodobně už běží jiná kopie. Nezapínej druhou. |
| Scio není v seznamu modelů | Ověř `provider.scio`, verzi OpenCode a úplně aplikaci restartuj. MCP samo model nepřidává. |
| `ENOENT`, chybí disk nebo složka | Vyber existující projekt; oprav `cwd` u MCP. |
| HTTP 502 / neplatný JSON ze Scio | Ověř stav chatu na Scio. Může jít o token, limit účtu, chybu serveru nebo nedodržení JSON formátu. |
| Dlouhé čekání bez tokenů | Adaptér čeká na celou odpověď. Při náročné úloze to může trvat. |
| Odpověď je useknutá / 500 KB limit | Zkrať konverzaci nebo proveď její kompakci v OpenCode. |

## Aktualizace a odinstalace

Aktualizace po zastavení programu:

```powershell
git pull --ff-only
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Pro odinstalaci zastav konzoli/server, odeber `provider.scio` a případně `mcp.scio` z konfigurace OpenCode a zvol jiný výchozí model. Potom můžeš odstranit složku programu. Smazání lokální složky nesmaže chaty uložené na Scio.

## Soubory projektu

- `scio_console.py` — přihlášení, DPAPI, konzole a komunikace se Scio.
- `scio_provider.py` — OpenAI-kompatibilní textový endpoint a JSON převod nástrojů.
- `scio_mcp.py` — MCP nástroje přes stdio nebo Streamable HTTP.
- `configure_opencode.py` — vytvoření přenositelného nastavení pro aktuální instalační cestu.
- `start_scio_provider.cmd` — jednoduchý Windows launcher.
- `requirements.txt` — závislosti pro modelový adaptér a MCP.

Při hlášení chyby přilož verzi Pythonu/OpenCode a anonymizovanou chybu. Nepřikládej tokeny, lokální klíč ani celý obsah svých chatů.
