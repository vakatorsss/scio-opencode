# SCIO CODE: ověřené modelové možnosti

Kontrola: 2026-11-04. Jde o zjištění z veřejného frontendového kódu a autorizovaného testu vlastního účtu, nikoli o úplnou dokumentaci interního backendu.

- [Scio frontend](https://chat.scio.cz/static/js/index.d11026b2f0.js): aliasy `auto`, `google-weak`, `google-strong`, `anthropic-strong`, `openai-weak`; metadata contextSize a maxOutputTokens. Konkrétní názvy nasazených modelů se mohou měnit.
- [Chat transport](https://chat.scio.cz/static/js/async/fu.d1fea51239.js): volba modelu a enabledFeatures. Nebyly nalezeny chat request parametry temperature, top_p, thinkingBudget, reasoningEffort ani service tier. SDK v jiném bundlu může tyto názvy obsahovat; to samo neznamená, že je chat endpoint přijímá.
- [Zobrazení nástrojů](https://chat.scio.cz/static/js/async/2a3.d0c3c000aa.js): `set_thinking_level`, hodnoty low/high.
- Živý test soukromého agenta s povoleným skillem `set-thinking-level` vrátil skutečný `tool-input-available` pro `set_thinking_level({"level":"high"})` a `tool-output-available` potvrzující HIGH pro zbytek aktuálního tahu. Poté dokončil odpověď. Nastavení se proto žádá znovu pro další uživatelský tah a pokračování po lokálních nástrojích; nepředstíráme dostupnost přímého inference-budget parametru.
- [OpenCode v1.19.3 task implementation](https://github.com/anomalyco/opencode/blob/v1.19.3/packages/opencode/src/tool/task.ts): background task vyžaduje `OPENCODE_EXPERIMENTAL_BACKGROUND_SUBAGENTS=true`; hloubku omezuje `subagent_depth`; child potřebuje výslovné povolení nástroje task.
- [OpenCode permissions](https://opencode.ai/docs/permissions/): permission allow spouští operace bez dotazu. Naše konfigurace generuje odpovídající pravidla pro explicitně zapnuté auto-allow.

SCIO CODE neposílá neověřené temperature/top-p parametry. OpenCode může mít jejich obecné ovladače, ale Scio adaptér je na backend nepřenáší. Úroveň thinking je modelově zprostředkovaná: model dostane instrukci zavolat serverový nástroj, jeho potvrzený výsledek se nepředává lokálnímu executorovi.

Když model nastavení v některém tahu přeskočí, klient nevydává preferenci za potvrzené nastavení: jednou za relaci zobrazí varování a pokračuje. Readiness test nevyžaduje thinking nástroj.
