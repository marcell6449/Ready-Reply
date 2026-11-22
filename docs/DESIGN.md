# Ready Reply — Design (v1)

Status: **DRAFT for review.** No production code is written until this document and
`docs/CRITERIA.md` are approved.

## 1. Goals and non-goals

**Goals (v1)**

- A local, single-business answer library: search → copy → paste into WhatsApp in about 2 seconds.
- Install and use in under 10 minutes on Windows, with no technical knowledge.
- Every public promise P1–P8 is backed by an automated test or a documented check.
- An architecture that a later multi-business SaaS can grow into without migrating data.

**Non-goals (YAGNI for v1)**

- No WhatsApp or Meta API integration.
- No cloud hosting, payments, subscriptions or multi-business UI.
- No automatic replies. AI never saves anything by itself.

## 2. Key decisions

| # | Decision | Why |
|---|----------|-----|
| D1 | Python 3.12+, FastAPI, SQLAlchemy 2, Alembic, SQLite with a rollback journal and `busy_timeout` | Required stack. A rollback journal (instead of WAL) keeps every commit inside `readyreply.db`, so copying the `data` folder is always a complete backup (QA-14). Writes are short, so several phones are fine. |
| D2 | Frontend: plain HTML, CSS and JS modules served by FastAPI. No CDN and no inline scripts. | Works offline. A strict CSP (`default-src 'self'`) enforces P7 and blocks XSS. |
| D3 | Search runs in memory over a per-business index. The index is rebuilt when answers or synonyms change. | 1,000 answers fit easily in memory, and the P8 target is < 200 ms. |
| D4 | Fuzzy matching runs over the **vocabulary** (unique tokens), not over every answer. Edit distance is computed by `rapidfuzz` (MIT, prebuilt Windows wheels), injected into the domain through a Protocol. | Keeps the domain pure and makes typo tolerance cheap: about 3,000 tokens instead of 30,000. |
| D5 | Template variables use stable English keys: `{name}`, `{hours}`, `{address}`, `{sinpe}`, `{phone}`, `{prices}`, plus custom `{snake_case}` keys. The UI shows localized labels and "insert variable" buttons, so users never have to type keys. | Keys don't depend on the language. Labels are translatable. |
| D6 | Server-side sessions: a random 256-bit token in an HttpOnly, SameSite=Strict cookie. Only the SHA-256 hash of the token is stored. | Expiry and logout really work, and it scales to several instances later. |
| D7 | CSRF uses a per-session synchronizer token sent in the `X-CSRF-Token` header, plus an `Origin`/`Referer` check. Login and setup use a double-submit cookie. | Covers JSON APIs and the pre-session forms. |
| D8 | Passwords are hashed with Argon2id (`argon2-cffi`). | Required. Wheels exist for Windows. |
| D9 | Copy uses `navigator.clipboard` and falls back to a hidden-textarea `execCommand('copy')`. | Phones open the app over plain `http://192.168.x.x`, which is **not** a secure context, so the Clipboard API is unavailable there. Without the fallback, copying on a phone breaks. |
| D10 | The Windows installer `start.bat` uses Python 3.12+ if present. Otherwise it installs Python with `winget` (built into Windows 10/11), or opens a short guided page if `winget` is missing. Dependencies are installed **offline** from wheels bundled in the zip. | python.org is unreachable from this build environment, so a fully embedded Python runtime can't be bundled. Bundled wheels still make the install fast and work without internet after Python is present. |
| D11 | AI providers sit behind the `SuggestionProvider` Protocol. The **default is Ollama** (free, runs on the business's computer, private) with the model `gemma3:4b`. Gemma 3 4B writes good Spanish, needs about 3.3 GB of disk and runs on an 8 GB PC without a graphics card. `RR_AI_MODEL` can switch to something lighter, such as `qwen2.5:1.5b`, on weaker PCs. Two more providers ship: **ManualPrompt** (shows the prompt to copy into any AI the owner uses; it opens no website by default) and **OpenAI-compatible HTTP** (any provider with that API and a key in `.env`). If Ollama isn't installed or running, the app falls back to ManualPrompt. | Free and private by default. A new provider is a new class plus one registry line in the composition root. |
| D12 | All visible text lives in one translations file: `readyreply/web/static/i18n/translations.json`. It ships with Spanish (`es`, the default) and English (`en`), and users can switch language from the menu. The domain raises exceptions with **codes**, the API returns those codes, and the frontend translates them. Demo data is in Spanish (Costa Rican businesses). | Adding a language means editing one file. |

## 3. Layers

```
┌───────────────────────────────────────────────────────────────┐
│ Frontend  (HTML/CSS/JS, i18n file)                            │
│   AI: "Suggest answer with AI" button, editable draft field,  │
│       "Copy prompt" panel for the manual fallback             │
└──────────────▲────────────────────────────────────────────────┘
               │ JSON over HTTP (cookie session + CSRF header)
┌──────────────┴────────────────────────────────────────────────┐
│ API  (FastAPI routers, Pydantic schemas, auth/CSRF deps,      │
│       error → HTTP code mapping)                              │
│   AI: POST /api/ai/suggest (admin only)                       │
└──────────────▲────────────────────────────────────────────────┘
               │ calls
┌──────────────┴────────────────────────────────────────────────┐
│ Application  (use cases, ports = Protocols)                   │
│   AI: BuildSuggestionPrompt, RequestSuggestion use cases      │
│       SuggestionProvider port (Protocol)                      │
└───────▲──────────────────────────────────────────▲────────────┘
        │ uses pure rules                          │ implemented by
┌───────┴──────────────┐            ┌──────────────┴─────────────┐
│ Domain               │            │ Infrastructure             │
│ entities, templates, │            │ SQLAlchemy repos + UoW,    │
│ search, permissions, │            │ Argon2, rapidfuzz, CSV,    │
│ CSV row rules, errors│            │ LAN/QR                     │
│ AI: SuggestionRequest│            │ AI: OllamaProvider         │
│     Draft,           │            │     (default, gemma3:4b),  │
│     ManualHandoff,   │            │     ManualPromptProvider,  │
│     prompt rules     │            │     OpenAICompatible,      │
│                      │            │     provider registry      │
└──────────────────────┘            └─────────────┬──────────────┘
        ▲ no imports of FastAPI, SQLAlchemy,      │ HTTP to 127.0.0.1:11434
          rapidfuzz or I/O                        ▼
                                    ┌────────────────────────────┐
                                    │ Ollama (separate free app  │
                                    │ on the same computer)      │
                                    └────────────────────────────┘
```

Dependency rule: arrows point inward. The domain imports nothing from other layers.
`readyreply/container.py` is the **composition root**. It is the only place that wires concrete
classes to ports. For AI, it reads `RR_AI_PROVIDER` and picks the provider from the registry.

### 3.1 Where the AI lives (one suggestion, end to end)

| Step | Layer | Module | What happens |
|---|---|---|---|
| 1 | Frontend | `web/static/js/ai.js` | The admin clicks "Suggest answer with AI" on an unanswered question. |
| 2 | API | `api/routers/ai.py` | Checks the session, the admin role and the CSRF token, then calls the use case. |
| 3 | Application | `application/ai.py` | `BuildSuggestionPrompt` gathers the business variables, existing answer titles and the question. `RequestSuggestion` calls the `SuggestionProvider` port. |
| 4 | Domain | `domain/ai.py` | Pure rules: what the prompt may contain (never user names, passwords or stats), maximum length, reply language. Defines the result types `Draft` and `ManualHandoff`. |
| 5 | Infrastructure | `infrastructure/ai/ollama.py` | Sends the prompt to Ollama on `127.0.0.1:11434`. If Ollama doesn't answer, the use case falls back to `ManualPromptProvider`. |
| 6 | Frontend | `web/static/js/ai.js` | Shows the draft in an **editable** field. Nothing is saved. |
| 7 | Application | `application/answers.py` | Only when the admin clicks **Save**, the normal `CreateAnswer` use case stores it and the question is marked resolved. |

The AI has **no access** to the repositories that write data. It can only return text, so it
can never save anything by itself (promise P5).

## 4. Modules

```
readyreply/
  domain/
    errors.py          DomainError(code) + subclasses
    entities.py        Business, Variable, Answer, SynonymGroup, UnansweredQuestion,
                       CopyEvent, User, Role
    templates.py       parse/render "{key}" templates, "{{" escapes, missing keys
    permissions.py     Action enum + Policy (role → allowed actions)
    text.py            normalize(): casefold, strip accents, drop emoji/punctuation
    search/
      tokens.py        tokenize + stop words (per-locale list injected)
      index.py         SearchIndex: vocabulary + postings per field
      scorers.py       Scorer Protocol; Exact, Prefix, Synonym, Fuzzy scorers
      engine.py        SearchEngine: combines scorers, field weights, threshold
    csv_rules.py       row validation for import (pure; no file I/O)
    unanswered.py      question key + "should record" rule (min length, stability)
    ai.py              SuggestionRequest, Draft, ManualHandoff, prompt content rules
  application/
    ports.py           Protocols: repositories, UnitOfWork, PasswordHasher, Clock,
                       TokenGenerator, EditDistance, SuggestionProvider, BusinessResolver
    variables.py       get/update business variables
    answers.py         create / edit / delete / duplicate / list
    search.py          SearchAnswers (uses a cached index per business)
    copy.py            RenderForCopy + RecordCopy (dedupe on double click)
    unanswered.py      RecordUnanswered, ListUnanswered, ResolveWithAnswer
    auth.py            SetupFirstAdmin, Login, Logout, ResolveSession, ManageUsers
    stats.py           TopCopied, TopUnanswered
    csv_io.py          ExportAnswers, ImportAnswers (report of rejected rows)
    demo.py            LoadDemoBusiness(soda | salon | hardware)
    ai.py              BuildSuggestionPrompt, RequestSuggestion
  infrastructure/
    db/                models.py, repositories.py, unit_of_work.py, engine.py
    security/          argon2_hasher.py, tokens.py
    search/            rapidfuzz_distance.py
    csv/               codec.py (encoding/BOM, delimiter sniffing, size limit)
    ai/                ollama.py, manual_prompt.py, openai_compatible.py, registry.py
    network/           lan_address.py, qr_svg.py (segno, generated locally)
    demo/              soda.json, salon.json, hardware.json
  api/
    deps.py            current_user, require(Action), csrf, unit of work per request
    errors.py          DomainError → HTTP status + {"code": ...}
    routers/           setup, auth, variables, answers, search, copy, unanswered,
                       users, stats, csv, demo, ai, system (LAN address + QR)
    schemas.py
  web/static/          index.html, app.css, js/*.js, i18n/translations.json
  config.py            Settings (pydantic-settings, RR_* env vars)
  main.py              composition root + app factory
migrations/            Alembic
tests/                 unit/ integration/ api/ e2e/ qa/ perf/
scripts/build_dist.py  builds dist/ready-reply-v1.0.0.zip
start.bat, start.sh
```

## 5. Entities (domain)

Every persisted entity carries `business_id`.

| Entity | Fields | Rules |
|---|---|---|
| Business | id, name, locale | v1 always has exactly one (id = 1). |
| Variable | business_id, key, label, value, is_builtin | Key matches `^[a-z][a-z0-9_]{0,39}$`. Built-in variables can't be deleted. Value ≤ 2,000 chars. |
| Answer | id, business_id, title, category, body, tags[], created_at, updated_at | Title 1–120 chars, body 1–4,000 chars after trimming. Tags are normalized and unique. Titles are unique per business, case- and accent-insensitive. |
| SynonymGroup | id, business_id, terms[] | At least 2 terms. Terms are stored normalized. A term belongs to only one group. |
| UnansweredQuestion | id, business_id, key, sample_text, times_searched, first_seen, last_seen, resolved_answer_id | The key is the normalized query with sorted tokens. |
| CopyEvent | id, business_id, answer_id, user_id, copied_at | Deleted together with its answer (cascade). |
| User | id, business_id, username, password_hash, role, is_active | Roles: `admin` (everything) and `staff` (search, copy, view unanswered). The last active admin can't be removed or demoted. |
| Session | token_hash, user_id, business_id, csrf_token, expires_at | 12-hour sliding expiry, set by `RR_SESSION_HOURS`. |

**Template rendering** (`templates.py`): `render(body, variables) -> RenderResult(text, missing_keys)`.

- A key is *missing* if it is undefined, or defined with an empty or whitespace-only value.
- If any key is missing, `text` is `None`, so the frontend can't copy a literal `{sinpe}`.
- `{{` and `}}` render as literal braces.
- An unclosed `{` is kept as literal text.

**Search** (`search/engine.py`):

1. `normalize` the query, then tokenize it. Stop words are removed, unless *every* token is a stop word.
2. For each query token, every scorer proposes matching vocabulary terms with a strength:
   - exact: 1.0
   - synonym: 0.9
   - prefix (≥ 3 chars): 0.75
   - fuzzy: 0.6
3. Fuzzy uses OSA (optimal string alignment, the restricted Damerau–Levenshtein distance). The allowed distance grows with token length: 0 edits for ≤ 3 chars, 1 edit for 4–7 chars, 2 edits for ≥ 8 chars.
4. Field weights are title 3.0, tags 2.5, category 1.5 and body 1.0. Each answer's score is the sum over query tokens of the best field-weighted match.
5. A coverage bonus rewards answers that match more of the query tokens.
6. Results scoring below `MIN_SCORE` are dropped. Ties are sorted by copy count, then by title.
7. An empty query, or one made only of stop words ("hola buenas"), lists the 50 most copied answers, then by title. The list is capped at 50 so phones stay fast; search finds the rest.
8. New strategies are added by implementing `Scorer` and registering them. The engine itself never changes (Open/Closed).

All numeric thresholds are named constants in `search/scoring_config.py`. They are tuned
through tests, not hard-coded inline.

**Unanswered questions**:

- The frontend calls `POST /api/unanswered` only when the result list is empty **and** the query has been stable for 1.5 seconds (or the user pressed Enter), and it has at least 3 normalized characters. Partial keystrokes like "h", "ho", "hor" are never recorded.
- The server ignores a repeat from the same user with the same key within 30 seconds. This handles double submits.
- Counting uses an atomic upsert.

**Copy dedupe**: a CopyEvent from the same user for the same answer within 3 seconds is
ignored (double click).

## 6. Ports (application/ports.py)

```python
class AnswerRepository(Protocol):
    def get(self, business_id: int, answer_id: int) -> Answer: ...
    def list_all(self, business_id: int) -> list[Answer]: ...
    def add(self, answer: Answer) -> Answer: ...
    def update(self, answer: Answer) -> None: ...
    def delete(self, business_id: int, answer_id: int) -> None: ...
    def title_exists(self, business_id: int, title_key: str, exclude_id: int | None) -> bool: ...
# Same shape for: VariableRepository, SynonymRepository, UnansweredRepository,
# CopyEventRepository, UserRepository, SessionRepository, BusinessRepository

class UnitOfWork(Protocol):          # transaction boundary, exposes the repositories
    answers: AnswerRepository; ...
    def commit(self) -> None: ...
    def __enter__(self) -> Self: ...; def __exit__(...) -> None: ...

class PasswordHasher(Protocol):      # hash(), verify()
class Clock(Protocol):               # now() -> datetime (UTC)
class TokenGenerator(Protocol):      # new_token() -> str
class EditDistance(Protocol):        # distance(a, b, limit) -> int | None
class BusinessResolver(Protocol):    # current() -> int   (v1: always 1)
class SuggestionProvider(Protocol):  # suggest(SuggestionRequest) -> SuggestionResult
```

`SuggestionResult` is one of two cases:

- `Draft(text)`: an API or local model answered.
- `ManualHandoff(prompt, open_url | None)`: the user copies the prompt into any AI and pastes the answer back.

Either way, the result is only shown in an editable field. Saving goes through the normal
`CreateAnswer` use case, which needs an admin click.

## 7. API (summary)

| Method & path | Role | Notes |
|---|---|---|
| `GET /api/setup/status`, `POST /api/setup` | none | Only works while there are no users. |
| `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me` | none / any | Login is rate-limited: 5 failures per 5 minutes per username and IP. |
| `GET/PUT /api/variables` | any / admin | |
| `GET/POST /api/answers`, `PUT/DELETE /api/answers/{id}`, `POST /api/answers/{id}/duplicate` | any / admin | |
| `GET /api/search?q=` | staff+ | No side effects. |
| `POST /api/answers/{id}/copy` | staff+ | Returns rendered text or `missing_keys`, and records the copy. |
| `GET/POST /api/unanswered`, `POST /api/unanswered/{id}/resolve` | staff+ / admin | |
| `GET/POST/PUT/DELETE /api/users` | admin | |
| `GET/PUT /api/synonyms` | any / admin | |
| `GET /api/stats` | admin | |
| `GET /api/csv/export`, `POST /api/csv/import` | admin | Import limit: 1 MB and 5,000 rows. |
| `POST /api/demo/{kind}` | admin | Asks for confirmation if answers already exist. |
| `POST /api/ai/suggest` | admin | |
| `GET /api/system/lan` | admin | Local URL and QR code as SVG. |

Errors always look like `{"code": "answer.title_taken", "details": {...}}`.

## 8. Frontend

- **Mobile-first at 360 px.** The search box is sticky at the top and always visible. Results are cards with a 48 px "Copy" button. Admin sections are in a bottom navigation bar on phones and a side bar on desktop.
- **Large screens** (≥ 1280 px and projector): a "Large text" toggle increases the base font size.
- **XSS:** user data is rendered only through `textContent`, `createElement` and `setAttribute`. A lint test fails the build if `innerHTML`, `outerHTML`, `insertAdjacentHTML` or `document.write` appear in `web/static/js`.
- **Copy feedback:** a visible "Copied ✓" toast. When variables are missing, a warning lists their labels. Admins get a link to fill them in.
- **Phone access:** the "Open on your phone" panel shows the LAN URL and a QR code generated locally.

## 9. Configuration (12-factor, `.env` + `.env.example`)

| Variable | Default |
|---|---|
| `RR_DATABASE_URL` | `sqlite:///./data/readyreply.db` |
| `RR_HOST`, `RR_PORT` | `0.0.0.0`, `8000` (tries the next free port up to 8010) |
| `RR_LOCALE` | `es` (`es` \| `en`) |
| `RR_SESSION_HOURS` | `12` |
| `RR_MAX_CSV_BYTES` | `1048576` |
| `RR_AI_PROVIDER` | `ollama` (`ollama` \| `manual` \| `openai_compatible`) |
| `RR_AI_MODEL` | `gemma3:4b` |
| `RR_AI_BASE_URL` | `http://127.0.0.1:11434` for Ollama |
| `RR_AI_CHAT_URL` | empty. Optional website opened by the manual provider. |
| `RR_AI_API_KEY` | Only for `openai_compatible`. The key is a secret and lives only in `.env`. |
| `RR_AI_TIMEOUT_SECONDS` | `60` (a 4B model on a CPU can take 10–40 seconds) |
| `RR_COOKIE_SECURE` | `false` (set `true` behind HTTPS) |

## 10. Security and privacy

- **Request guard (ASGI, before the app reads anything):** rejects Host headers that are not an IP address, `localhost`, a single-label computer name, `*.local` or `RR_ALLOWED_HOSTS` (blocks DNS rebinding), and reads at most `RR_MAX_REQUEST_BYTES` of any body (2 × `RR_MAX_CSV_BYTES` for CSV import).
- **Login:** exactly one Argon2 check for every outcome (unknown, inactive, wrong or right password), so timing does not reveal accounts. Locked after 5 failures per username or 20 per address in 5 minutes.
- **Accepted risks (documented in the README FAQ):** the local Wi-Fi connection is plain HTTP, and the first person to open a fresh install creates the administrator. The browser opens on the computer immediately after the first start.

- **SQL:** all queries go through the SQLAlchemy ORM or Core with bound parameters. No string-built SQL.
- **Headers:** `Content-Security-Policy: default-src 'self'; frame-ancestors 'none'`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`.
- **Logs:** method, path (without query string), status and duration only. Never bodies, cookies, passwords, search text or API keys. A test checks this.
- **CSV export:** cells starting with `= + - @`, tab or carriage return are prefixed with `'` to prevent formula injection.
- **CSV import:** size is checked before parsing. Accepts UTF-8 with or without BOM, and `,` or `;` delimiters (Spanish-locale Excel uses `;`).
- **P7, data stays local:**
  - All assets are local and the QR code is generated on the machine.
  - Finding the LAN IP uses a UDP `connect()` call, which sends no packets.
  - A test blocks every non-loopback socket and runs the full API suite.
  - The default AI provider, Ollama, runs on the same computer (`127.0.0.1`). The only call that leaves the computer is to an `openai_compatible` provider, and only when the owner configures one.

## 11. Path to SaaS (not built in v1)

1. **Tenancy:** `business_id` is already on every table and every repository method takes it. The `BusinessResolver` port is implemented by `infrastructure/tenancy.py::SingleBusinessResolver`; replace it with one that reads the tenant from the subdomain or session. `tests/integration/test_repositories.py` checks that no repository returns another business's rows. Tests already check that one business can't read another's rows.
2. **Database:** set `RR_DATABASE_URL=postgresql+psycopg://...`. The upsert is wrapped inside the repository implementation, so it's the only place that changes. Alembic migrations stay dialect-neutral.
3. **Search:** the in-memory index sits behind `SearchIndexProvider`. For SaaS, add a PostgreSQL `pg_trgm` or a cached implementation. Use cases don't change.
4. **Sessions:** they're already in the database, so several app instances work.
5. **Billing, signup, subscriptions:** new modules on top. No existing table changes.

## 12. Testing strategy

| Level | Scope | Tool |
|---|---|---|
| Unit | Domain, 100% line and branch coverage | pytest |
| Integration | SQLAlchemy repositories on a temporary SQLite database. Alembic upgrade from empty. | pytest |
| API | Every endpoint, roles, CSRF, expired sessions, errors | FastAPI TestClient |
| Performance | 1,000 answers: p95 of 50 searches < 200 ms (P8) | pytest |
| E2E | Main flows at 1280 px and 360 px, clipboard contents, screenshots for the README | Playwright (Python) |
| QA | Hostile inputs: SQL/HTML injection, emojis, large files, permissions, concurrent upserts | pytest + Playwright, written by an independent agent |
| Install | `start.sh` in a clean folder from the zip. `start.bat` is tested by the owner on Windows. | script + documented manual steps |
| AI | Providers are tested against fake HTTP servers. A real Ollama run is a manual check by the owner, because Ollama and its models can't be downloaded in this build environment. | pytest + manual checklist |

Quality gates: `ruff check`, `ruff format --check`, `mypy --strict`, total coverage ≥ 90%,
domain coverage 100%, and pytest passing three times in a row.

## 13. Known constraints

- `start.bat` can't be executed in this Linux build environment. Windows install is verified with a documented manual checklist by the owner before publishing.
- The Windows wheels in the zip are built for 64-bit Windows 10/11 and Python 3.12–3.13.
- Ollama is a separate free install (ollama.com) plus a one-time `ollama pull gemma3:4b` (about 3.3 GB). The README explains it, and the app works fully without it.
