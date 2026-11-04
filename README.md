# Scio → OpenCode

Český návod pro konzolového klienta Scio, lokální modelový adaptér a MCP server.

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
