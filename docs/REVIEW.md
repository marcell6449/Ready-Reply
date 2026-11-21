# Ready Reply — Independent code review (v1)

Scope: `readyreply/` (domain, application, infrastructure, api, web/static) and `tests/`,
checked against `docs/DESIGN.md` and `docs/CRITERIA.md`.

## Summary

The overall structure is sound. The domain is pure: it imports nothing from FastAPI,
SQLAlchemy, rapidfuzz or httpx and does no I/O. Use cases depend on `typing.Protocol` ports.
Scorers are registered in the composition root, so new search strategies need no engine
changes. Every tenant table carries `business_id`. The frontend builds the DOM only through
`createElement`/`textContent`/`setAttribute`, with no `innerHTML` sinks, and a strict CSP is
sent. All SQL goes through the ORM/Core with bound parameters. 274 non-e2e tests pass.

The main problems are in authentication and in exposure on the LAN:

- **Login timing reveals which usernames exist.** This breaks F6-06 (R-01).
- **Request bodies have no size limit.** Unauthenticated endpoints buffer the whole body (R-02).
- **The login throttle can be bypassed** (R-03).
- **First-run setup can be claimed from the LAN** (R-04).
- **Credentials travel in cleartext** over the Wi-Fi (R-05).

The project's own quality gates also fail on `tests/e2e`: ruff, ruff format and mypy (R-09).
The remaining findings are design drift (OCP for AI providers, a missing `BusinessResolver`
port, an infrastructure call made straight from a router) and low-severity smells.

Tooling results (`ruff check readyreply tests && ruff format --check readyreply tests && mypy readyreply tests`):

```
ruff check:          Found 5 errors (E501 Line too long)
  tests/e2e/conftest.py:35:101   (106 > 100)
  tests/e2e/test_flows.py:100:100 (101 > 100)
  tests/e2e/test_flows.py:101:101 (107 > 100)
  tests/e2e/test_flows.py:143:101 (125 > 100)
  tests/e2e/test_flows.py:204:101 (102 > 100)
ruff format --check: 3 files would be reformatted, 114 files already formatted
  tests/e2e/conftest.py, tests/e2e/test_flows.py, tests/e2e/test_screenshots.py
mypy:                Found 2 errors in 2 files (checked 117 source files)
  tests/e2e/conftest.py:81: error: Argument "viewport" to "new_context" of "Browser" has
    incompatible type "dict[str, int]"; expected "ViewportSize | None"  [arg-type]
  tests/e2e/test_screenshots.py:18: error: Argument "viewport" to "new_context" of "Browser"
    has incompatible type "dict[str, int]"; expected "ViewportSize | None"  [arg-type]
pytest tests -m "not e2e": 274 passed, 26 deselected
```

`readyreply/` itself is clean under all three tools. Every failure is in `tests/e2e`.

---

## Findings

### R-01 — Login response time reveals whether a username exists, and whether it is inactive
- **Severity:** high
- **Category:** security
- **Location:** `readyreply/application/auth.py:121-128`
- **What is wrong:** `Login._authenticate` takes three paths with different costs:
  - **Unknown username:** `self._hasher.verify(self._hasher.hash("timing-equalizer"), password)`, which is **two** Argon2 operations.
  - **Existing active user:** one `verify`.
  - **Existing inactive user:** `user.active and ...` short-circuits, so there are **zero** Argon2 operations.

  Measured locally with the project's `Argon2PasswordHasher`:
  - Existing user: about 73 ms.
  - Unknown user: about 149 ms.
  - Inactive user: about 0 ms.
- **Why it matters:** F6-06 requires that a failed login "does not reveal whether the username exists". From the same Wi-Fi, a 75 ms gap is trivial to measure. An attacker can list valid accounts and then focus guessing on them. Deactivated accounts are also revealed.
- **Suggested fix:** Compute one dummy hash once at construction (`self._dummy_hash = hasher.hash(secrets.token_urlsafe())`). Then always run exactly one `verify`:
  ```python
  candidate = user.password_hash if user else self._dummy_hash
  ok = self._hasher.verify(candidate, password)
  if user and user.active and ok: return user
  ```
  Add a unit test that counts `verify`/`hash` calls on a fake hasher for all three paths.

### R-02 — No request body size limit: unauthenticated clients can make the server buffer arbitrarily large bodies
- **Severity:** medium
- **Category:** security
- **Location:** `readyreply/api/security.py:72-75` (no limit installed); `readyreply/api/routers/auth.py:47-65`; all JSON routers
- **What is wrong:** Only `/api/csv/import` limits its input (`_read_limited`, `admin.py:58-68`). For every other route, FastAPI reads the whole body (`await request.body()` / `request.json()` in `fastapi/routing.py`) **before** it resolves dependencies. That means before the CSRF and session checks run. Pydantic `max_length` caps are applied only after the full body has been read and parsed. Uvicorn has no default body limit either.
- **Why it matters:** Any device on the Wi-Fi, with no account, can POST a body of hundreds of MB to `/api/auth/login` or `/api/setup`. Each request is held in memory, and several in parallel can exhaust RAM on the shop's PC.
- **Suggested fix:** Add a small ASGI middleware that does two things. First, it rejects requests whose `Content-Length` exceeds a named limit, for example `MAX_JSON_BYTES = 64 * 1024`, with `413 request.too_large`. Second, it wraps `receive` so the limit also applies to chunked bodies. Exempt `/api/csv/import`, which keeps its own `max_csv_bytes`. Add an API test that sends a 1 MB body to `/api/auth/login` and expects 413.

### R-03 — Login throttling can be bypassed (lockout wipe, race, no per-IP limit)
- **Severity:** medium
- **Category:** security
- **Location:** `readyreply/infrastructure/security/memory.py:31-36`; `readyreply/application/auth.py:110-118`
- **What is wrong:**
  1. `MemoryLoginFailureLog.record` calls `self._failures.clear()` once 10,000 keys are tracked. That wipes **every** lockout, including the one on the target account. Keys are `f"{client}:{username}"`, so an attacker can fill the table by failing logins with 10,000 made-up usernames.
  2. The check (`is_login_locked(...)`) and the record (`self._failures.record(...)`) are not atomic. The endpoint is a sync route served from a thread pool, so a burst of parallel requests all pass the check before any failure is recorded. That allows far more than 5 guesses per window.
  3. Nothing limits attempts per IP across usernames, so password spraying is unthrottled.
- **Why it matters:** F6-07 (5 failures per 5 minutes) is the main protection against online password guessing from the LAN. All three paths defeat it.
- **Suggested fix:**
  - Evict only expired entries, or the oldest key, never the whole table.
  - Under one lock, "reserve" an attempt: append a pending timestamp before verifying, and remove it on success. Check and record then become one atomic step.
  - Add a second, coarser bucket keyed by client IP alone, for example 20 failures per 5 minutes.
  - Add tests for the 10,000-key wipe and for concurrent attempts.

### R-04 — First-run setup can be claimed by any device on the Wi-Fi, or through DNS rebinding
- **Severity:** medium
- **Category:** security
- **Location:** `readyreply/api/routers/auth.py:36-52`; `readyreply/api/security.py:41-45`; `readyreply/config.py:17`
- **What is wrong:** The server binds `0.0.0.0` from the first start. `POST /api/setup` is open to anyone until an admin exists, and the only protection is a double-submit token that any client can fetch from `GET /api/setup/status`. The `Host` header is never validated. `_origin_allowed` only compares `Origin` with `Host`, and both match under DNS rebinding.
- **Why it matters:** In the window between installation and the owner creating the admin, any device on the same network can create the first administrator and lock the owner out. A web page the owner visits can do the same through DNS rebinding. That page could also drive login attempts from the owner's own browser.
- **Suggested fix:**
  - Accept `POST /api/setup` only when `request.client.host` is loopback, and say so in the setup screen.
  - Install `TrustedHostMiddleware` with `localhost`, `127.0.0.1` and the detected LAN IP (`lan_ip()`), plus a configurable `RR_ALLOWED_HOSTS`.
  - Add API tests for both.

### R-05 — Passwords and session cookies travel in cleartext over the shop's Wi-Fi
- **Severity:** medium
- **Category:** security
- **Location:** `readyreply/config.py:22` (`cookie_secure = False`); `readyreply/api/routers/auth.py:19-28`; `readyreply/__main__.py:39`
- **What is wrong:** Phones are told to open `http://<lan-ip>:<port>/`. Login sends the username and password in a plain-HTTP POST, and every later request carries the `rr_session` cookie in clear. The design accepts plain HTTP for the clipboard (D9) but does not cover this risk.
- **Why it matters:** "Anything an attacker on the same Wi-Fi could abuse." Small shops often run open or shared-PSK networks. Any client on the network can capture the admin's password or session and take full control: export all answers, create users, replace the library.
- **Suggested fix:** Two options, best done together:
  - **(a)** Allow admin sign-in only from loopback by default, with an opt-in setting. Phones are mainly used by staff to search and copy.
  - **(b)** Offer optional HTTPS with a locally generated self-signed certificate (`RR_TLS=on`), and set `secure=True` automatically when the request scheme is `https`.

  At a minimum, document the risk in the README and in the "Open on your phone" panel.

### R-06 — Adding an AI provider requires editing two existing modules (Open/Closed)
- **Severity:** medium
- **Category:** SOLID
- **Location:** `readyreply/config.py:25`; `readyreply/infrastructure/ai/registry.py:30-32`; `tests/api/test_ai.py:189-193`
- **What is wrong:** The `ai_provider` setting is a closed `Literal["ollama", "manual", "openai_compatible"]`. A new provider means editing the `Literal` in `config.py` **and** the `PROVIDERS` map in `infrastructure/ai/registry.py`. The test named for F8-08 asserts that the two lists are equal, which enforces that double edit. DESIGN D11 promises "a new class plus one registry line in the composition root". The registry is not in the composition root (`container.py`).
- **Why it matters:** F8-08 requires that "no other module was modified". Today a new provider touches configuration, infrastructure and the test.
- **Suggested fix:**
  - Make `ai_provider: str`.
  - Validate it against the registry when the container is built, raising a clear startup error for unknown names.
  - Keep the provider factories registered in `container.py`, or let the registry be the single list that config validation reads.
  - Change the F8-08 test to register a fake provider at runtime and check it is used without touching `config.py`.

### R-07 — `BusinessResolver` port is missing; the tenant id is hard-coded inside use cases
- **Severity:** medium
- **Category:** architecture
- **Location:** `readyreply/application/auth.py:21, 89, 122`; `readyreply/application/bootstrap.py:3, 15-16`
- **What is wrong:** DESIGN §6 defines `BusinessResolver.current() -> int`, and §11 says the SaaS path is to "replace `SingleBusinessResolver`". Neither exists. The application layer hard-codes `BUSINESS_ID = 1` in `auth.py`, and `bootstrap.py` imports that constant from another use-case module.
- **Why it matters:** The multi-business path described in the design cannot happen without editing the login, setup and bootstrap use cases. The tenancy decision belongs behind a port injected by the composition root.
- **Suggested fix:**
  - Add `class BusinessResolver(Protocol): def current(self) -> int: ...` to `application/ports.py`.
  - Implement `SingleBusinessResolver` in infrastructure.
  - Inject it into `SetupFirstAdmin`, `Login` and `EnsureBusiness`, and remove `BUSINESS_ID` from `auth.py`.

### R-08 — Phone-access endpoints skip the application layer; authorization happens only in the router
- **Severity:** medium
- **Category:** architecture
- **Location:** `readyreply/api/routers/admin.py:19, 89-103`
- **What is wrong:** The router imports `lan_ip` and `qr_svg` straight from `readyreply.infrastructure.network.lan` and calls `actor.require(Action.VIEW_SYSTEM)` itself. No use case or port sits in between. This is the only feature where the authorization check exists only in the API layer. (`import_csv` also calls `actor.require` in the router, but the use case checks again, so that one is only redundant.)
- **Why it matters:**
  - It breaks the layer rule (api → application → ports ← infrastructure).
  - It breaks the review rule "authorization checks enforced in use cases".
  - The LAN lookup and QR code cannot be swapped or faked without patching modules.
- **Suggested fix:**
  - Add a `NetworkInfo` port (`lan_address() -> str`, `qr_svg(text) -> bytes`) and a `ShowPhoneAccess` use case that calls `actor.require(Action.VIEW_SYSTEM)`.
  - Wire it in `container.py`.
  - Remove the duplicate `actor.require` from `import_csv` in the router.

### R-09 — Quality gates fail: ruff, ruff format and mypy report errors in `tests/e2e`
- **Severity:** medium
- **Category:** typing
- **Location:** `tests/e2e/conftest.py:33-35, 81, 86-87`; `tests/e2e/test_flows.py:31-32, 100-101, 143, 172-173, 204`; `tests/e2e/test_screenshots.py:17-18`
- **What is wrong:** See the tooling output in the summary: 5 E501 errors, 3 files not formatted, and 2 mypy `arg-type` errors. Both mypy errors pass `VIEWPORTS[device]` (`dict[str, int]`) where Playwright expects `ViewportSize`.
- **Why it matters:** DESIGN §12 makes `ruff check`, `ruff format --check` and `mypy --strict` release gates. The required command fails as written.
- **Suggested fix:**
  - Run `ruff format tests/e2e`.
  - Wrap the long lines.
  - Type `VIEWPORTS` as `dict[str, ViewportSize]`, using `from playwright.sync_api import ViewportSize`, with values like `ViewportSize(width=360, height=740)`.
  - Add the three commands to a single `make check` / CI step so this cannot regress.

### R-10 — Use cases depend on concrete classes instead of ports
- **Severity:** low
- **Category:** SOLID
- **Location:** `readyreply/application/answers.py:88-92`; `csv_transfer.py:47-58`; `demo.py:30-36`; `unanswered.py:60-65`; `search.py:60-66`
- **What is wrong:**
  - `DuplicateAnswer`, `ImportAnswers`, `LoadDemo` and `AnswerQuestion` each take the concrete `CreateAnswer` and call its extra public method `add_within(uow, ...)`.
  - `SearchAnswers` takes the concrete `SearchIndexCache`, while DESIGN §11 names a `SearchIndexProvider` port.
- **Why it matters:** These classes are coupled to one implementation, and a cached or PostgreSQL-backed index cannot be swapped in "without use cases changing", as §11 promises.
- **Suggested fix:**
  - Define `class AnswerWriter(Protocol): def add_within(self, uow, actor, draft) -> Answer`, and `class SearchIndexProvider(Protocol): def get(self, uow, business_id) -> tuple[SearchIndex, dict[int, Answer]]`, in `ports.py`.
  - Type the constructor parameters with them.

### R-11 — CSRF tokens are generated with `secrets` directly instead of the `TokenService` port
- **Severity:** low
- **Category:** SOLID
- **Location:** `readyreply/application/auth.py:3, 52`; `readyreply/api/routers/auth.py:3, 38`
- **What is wrong:** `SessionStarter` injects `TokenService` for the session token but calls `secrets.token_urlsafe(32)` for the CSRF token. The router does the same for the pre-session token. The literal `32` is repeated, and the token is not deterministic in unit tests.
- **Why it matters:** This is an inconsistent use of dependency inversion. It also leaves a magic number.
- **Suggested fix:** Use `self._tokens.new_token()` in both places, or add `new_csrf_token()` to `TokenService`.

### R-12 — The session cookie's `max_age` is never extended, so sliding expiry does not work in the browser
- **Severity:** low
- **Category:** security
- **Location:** `readyreply/api/routers/auth.py:19-28`; `readyreply/application/auth.py:167-171`
- **What is wrong:** `ResolveSession._refresh` extends `expires_at` on the server. The cookie, however, is written only once, at login, with `max_age = session_hours * 3600`. After 12 hours the browser drops the cookie even if the user was active the whole time. DESIGN §5 says "12-hour sliding expiry".
- **Why it matters:** Staff get logged out in the middle of a shift. The server-side sliding logic has no effect.
- **Suggested fix:** Use a session cookie (no `max_age`). Alternatively, re-set the cookie when `ResolveSession` refreshes the session, for example by returning a `refreshed` flag that a response dependency acts on. Replace `3600` with a named constant.

### R-13 — Expired sessions are never purged
- **Severity:** low
- **Category:** security
- **Location:** `readyreply/application/auth.py:151-160`; `readyreply/infrastructure/db/repositories/accounts.py:75-105`
- **What is wrong:** A session row is deleted only when someone presents its token after expiry, or on logout. Sessions abandoned by closing the browser stay in the table forever.
- **Why it matters:** The table grows without bound, and stale token hashes linger longer than needed.
- **Suggested fix:** Add `SessionRepository.delete_expired(now)` and call it from `EnsureBusiness` at startup and on each login.

### R-14 — CSV import reports wrong row numbers after blank or multi-line rows
- **Severity:** low
- **Category:** smell
- **Location:** `readyreply/infrastructure/csv/codec.py:41`; `readyreply/application/csv_transfer.py:19, 78`
- **What is wrong:** The codec drops blank rows before the use case numbers rows with `enumerate(rows, start=FIRST_DATA_LINE)`. Quoted cells with line breaks also span several physical lines. In both cases the reported numbers stop matching the file's line numbers.
- **Why it matters:** F10-05 promises a report with the row numbers, which the owner uses to fix the file in Excel. Wrong numbers send them to the wrong row.
- **Suggested fix:** Have the codec return `(reader.line_num, row)` pairs (or a `CsvRow(line, cells)` value) and use that number in `RejectedRow`.

### R-15 — An empty query lists at most 50 answers, but F3-08 asks for all answers
- **Severity:** low
- **Category:** smell
- **Location:** `readyreply/application/search.py:15, 74`
- **What is wrong:** `RESULT_LIMIT = 50` is applied to every search, including the empty-query listing. F3-08 says an empty query returns "all answers, ordered by copy count then title".
- **Why it matters:** With more than 50 answers, the browse view silently hides the rest. The current tests use the 12-answer demo, so they do not catch it.
- **Suggested fix:** Either skip the limit for empty queries, or add paging and update F3-08 to match. Add a test with more than 50 answers.

### R-16 — Duplicated error handling in the HTTP AI providers
- **Severity:** low
- **Category:** smell
- **Location:** `readyreply/infrastructure/ai/ollama.py:17-25`; `readyreply/infrastructure/ai/openai_compatible.py:18-26`
- **What is wrong:** Both providers repeat the same `try/raise_for_status/json/except (...)` block and the same empty-reply check. Only the payload and the JSON path differ.
- **Why it matters:** A fix in one copy, such as also catching `httpx.InvalidURL` or handling a non-dict JSON body, has to be repeated in the other. Every future HTTP provider copies the block again.
- **Suggested fix:** Extract `post_json(client, url, payload, headers) -> object` and `require_text(value) -> str` helpers into `infrastructure/ai/_http.py` and use them from both providers.

### R-17 — Magic numbers and strings
- **Severity:** low
- **Category:** smell
- **Location:**
  - `readyreply/application/ai.py:72` (`"name"`)
  - `readyreply/api/routers/auth.py:23` (`3600`)
  - `readyreply/api/schemas.py:52, 55` (`SHORT * 2`, `max_length=100`)
  - `readyreply/domain/search/scorers.py:25-30` (returns `2` / `1` / `0`)
  - `readyreply/application/auth.py:52` and `readyreply/api/routers/auth.py:38` (`32`)
- **What is wrong:** These literals carry meaning but have no name.
- **Why it matters:** They hide intent and drift easily. For example, the tag-count cap of 100 in the schema has no link to `TAGS_MAX_COUNT = 20` in the domain.
- **Suggested fix:**
  - Use `"name"` from a named constant, for example `BUSINESS_NAME_KEY` in `domain/variables.py`.
  - Use `SECONDS_PER_HOUR` or `timedelta(hours=...).total_seconds()` instead of `3600`.
  - Add `MAX_TAG_INPUTS` and `TITLE_INPUT_MAX`.
  - Add `FUZZY_MAX_EDITS_SHORT/LONG` to `scoring_config.py`.
  - Add `CSRF_TOKEN_BYTES`.

### R-18 — Dead code
- **Severity:** low
- **Category:** smell
- **Location:** `readyreply/application/demo.py:24`; `readyreply/infrastructure/demo/catalog.py:34-35`; `readyreply/application/ports.py:149-152`
- **What is wrong:**
  - `DemoCatalog.kinds()` / `JsonDemoCatalog.kinds()` are never called.
  - The `Texts` Protocol is never used as a type. `container.py` types the field as the concrete `TranslationTexts`.
- **Why it matters:** Unused interfaces mislead readers about how the code is wired.
- **Suggested fix:** Either use them (type `_Shared.texts: Texts`; expose `kinds()` to the frontend through an endpoint instead of the hard-coded list in R-19) or delete them.

### R-19 — Server rules duplicated in the frontend
- **Severity:** low
- **Category:** smell
- **Location:** `readyreply/web/static/js/views/answers.js:6`; `readyreply/web/static/js/views/data.js:5`
- **What is wrong:**
  - `PLACEHOLDER = /\{\{|\}\}|\{([a-z][a-z0-9_]{0,39})\}/g` copies `KEY_PATTERN`/`_TOKEN` from `domain/templates.py`.
  - `DEMOS = ["soda", "salon", "hardware"]` copies `KINDS` from `infrastructure/demo/catalog.py`.
- **Why it matters:** Changing the key rule or adding a demo business means editing the JS too. Otherwise the editor hints, or the demo buttons, go silently wrong.
- **Suggested fix:**
  - Have `GET /api/setup/status`, or a new `/api/meta`, return `demo_kinds` and the key pattern.
  - Or return the parsed `placeholders` from the server, for example in `AnswerOut`.

### R-20 — Silent fallbacks hide broken invariants
- **Severity:** low
- **Category:** smell
- **Location:** `readyreply/api/schemas.py:72, 151`; `readyreply/application/unanswered.py:72-73`
- **What is wrong:**
  - `id=answer.id or 0` and `id=user.id or 0` turn a missing id into `0`.
  - `AnswerQuestion` skips `resolve` when `answer.id is None`, so the answer is saved but the question stays open, with no error.
- **Why it matters:** A persistence bug would show up as a wrong result (id 0, question still open) instead of an error.
- **Suggested fix:** Raise (or `assert`) when a persisted entity has no id. Better still, give persisted entities a non-optional `id: int` type, for example separate `NewAnswer` and `Answer` types.

### R-21 — Behaviour switched by flags in the frontend
- **Severity:** low
- **Category:** smell
- **Location:** `readyreply/web/static/js/views/auth.js:8, 18-19`; `readyreply/web/static/js/views/search.js:18`
- **What is wrong:**
  - `credentialsForm` changes autocomplete and hints by testing `introKey === "setup.intro"`.
  - `onQueryInput(query, { immediate })` switches the debounce with a boolean.
- **Why it matters:** The string comparison couples behaviour to a translation key. Renaming the key silently breaks password-manager hints on the setup form.
- **Suggested fix:** Pass an explicit options object, for example `{ passwordAutocomplete: "new-password", showHints: true }`, from `renderSetup`/`renderLogin`. Split the immediate path into `searchNow(query)`.

### R-22 — `add_within` bumps the index revision once per row
- **Severity:** low
- **Category:** smell
- **Location:** `readyreply/application/answers.py:54`; callers in `csv_transfer.py:78-84` and `demo.py:55-57`
- **What is wrong:** Every `add_within` call runs `UPDATE businesses SET content_revision = content_revision + 1`. A 5,000-row import runs 5,000 extra updates on the same row inside one transaction. `LoadDemo` then bumps once more.
- **Why it matters:** This makes imports needlessly slow and holds the SQLite write lock longer, which blocks phones searching at the same time.
- **Suggested fix:** Let the outer use case (`CreateAnswer.execute`, `ImportAnswers`, `LoadDemo`, `AnswerQuestion`, `DuplicateAnswer`) bump once before commit. `add_within` should only add.

### R-23 — "Last admin" is reported as invalid input (422) rather than a state conflict
- **Severity:** low
- **Category:** smell
- **Location:** `readyreply/domain/users.py:44-46`
- **What is wrong:** `ensure_an_admin_remains` raises `InvalidInputError("user.last_admin")`. The request body is valid. It conflicts with the current state, which is what `ConflictError` (409) means in `domain/errors.py`.
- **Why it matters:** The status code is misleading, and the error class does not match the taxonomy the project defines.
- **Suggested fix:** Raise `ConflictError("user.last_admin")` and update the API test's expected status.

### R-24 — Unanswered upsert silently reopens resolved questions, and the resolved state is stored twice
- **Severity:** low
- **Category:** smell
- **Location:** `readyreply/infrastructure/db/repositories/activity.py:47-56`; `readyreply/infrastructure/db/models.py:87-90`
- **What is wrong:** On conflict the upsert sets `resolved = False` but keeps `resolved_answer_id` and the old `times_searched`. "Resolved" is stored in two columns that can disagree: `resolved=False` with a `resolved_answer_id`, or `resolved=True` with a NULL id after the answer is deleted. The domain entity also has no way to express any of this.
- **Why it matters:** A question the owner already answered comes back with its old count. The stored state becomes inconsistent, and stats that use it are skewed.
- **Suggested fix:**
  - Decide the rule in the domain. For example: a resolved question that is searched again reopens with `times_searched = 1` and `resolved_answer_id = NULL`.
  - Derive "resolved" from a single column.
  - Cover the rule with a repository test.

### R-25 — `build_container` is longer than 25 lines
- **Severity:** low
- **Category:** smell
- **Location:** `readyreply/container.py:216-245` (30 lines)
- **What is wrong:** This function mixes engine and session setup, building the shared object graph, and assembling the container. All other hand-written functions are within the limit. The Alembic `upgrade`/`downgrade` functions are auto-generated and excluded.
- **Why it matters:** It is slightly over the agreed function-length limit.
- **Suggested fix:** Extract `_shared(settings, uow_factory) -> _Shared`.

### R-26 — One integrity error during CSV import fails every remaining row with a 500
- **Severity:** low
- **Category:** smell
- **Location:** `readyreply/infrastructure/db/repositories/content.py:171-175`; `readyreply/application/csv_transfer.py:78-84`
- **What is wrong:** `_flush` turns `IntegrityError` into `ConflictError` but does not roll back. After a failed flush the SQLAlchemy session needs a rollback. Every later row in the same import then raises `PendingRollbackError`. That is not a `DomainError`, so it escapes the row loop and returns a 500. This happens if a concurrent request inserts the same title between `title_taken` and `flush`.
- **Why it matters:** A rare race turns a partial-success import into a generic server error.
- **Suggested fix:** Wrap each row in a savepoint, for example a `uow.savepoint()` port backed by `session.begin_nested()`, so a failed row rolls back only itself.

### R-27 — Small drifts from the design document
- **Severity:** low
- **Category:** architecture
- **Location:** `readyreply/infrastructure/search/distance.py:8`; `readyreply/container.py:1`; `readyreply/main.py`
- **What is wrong:**
  - DESIGN §5.3 says fuzzy matching uses Damerau–Levenshtein. The implementation uses `rapidfuzz.distance.OSA` (optimal string alignment), a restricted variant.
  - DESIGN §3 names `main.py` as the composition root, but the wiring lives in `container.py`.
- **Why it matters:** The docs and the code disagree, which misleads maintainers.
- **Suggested fix:** Update DESIGN.md: say "OSA (restricted Damerau–Levenshtein)" and name `container.py` as the composition root. Or switch to `rapidfuzz.distance.DamerauLevenshtein`.

### R-28 — Test levels promised in the design are missing
- **Severity:** low
- **Category:** architecture
- **Location:** `tests/qa/` (only `__init__.py`); `tests/integration/` (only `test_migrations.py`)
- **What is wrong:**
  - DESIGN §12 lists a QA level (hostile inputs, concurrent upserts) and integration tests for the SQLAlchemy repositories. `tests/qa` is empty.
  - Repository behaviour (the upsert under concurrency, cascades, cross-business isolation for every repository) is exercised only indirectly through API tests. Only answers are checked for cross-business isolation (`tests/api/test_content.py:107`).
- **Why it matters:** The atomic upsert (F5-06) and the claim in §11 that "tests already check that one business can't read another's rows" are only partly backed by tests.
- **Suggested fix:**
  - Add `tests/integration/test_repositories.py`, with one isolation test per repository and a threaded upsert test.
  - Fill `tests/qa` as the design describes.

---

## Status

| ID | Severity | Category | Location | Title | Status |
|---|---|---|---|---|---|
| R-01 | high | security | application/auth.py:121-128 | Login timing reveals username existence and inactive accounts | open |
| R-02 | medium | security | api/security.py:72-75 | No request body size limit (pre-auth memory DoS) | open |
| R-03 | medium | security | infrastructure/security/memory.py:31-36 | Login throttle can be bypassed (wipe, race, no per-IP limit) | open |
| R-04 | medium | security | api/routers/auth.py:36-52 | First-run setup claimable from the LAN or via DNS rebinding | open |
| R-05 | medium | security | config.py:22 | Credentials and cookies in cleartext over Wi-Fi | open |
| R-06 | medium | SOLID | config.py:25, infrastructure/ai/registry.py:30 | New AI provider requires editing two modules | open |
| R-07 | medium | architecture | application/auth.py:21 | BusinessResolver port missing; tenant id hard-coded | open |
| R-08 | medium | architecture | api/routers/admin.py:19, 89-103 | Phone-access endpoints skip use case; authorization only in router | open |
| R-09 | medium | typing | tests/e2e/* | ruff, ruff format and mypy gates fail | open |
| R-10 | low | SOLID | application/answers.py:88 and others | Use cases depend on concrete CreateAnswer / SearchIndexCache | open |
| R-11 | low | SOLID | application/auth.py:52 | CSRF token generated outside TokenService port | open |
| R-12 | low | security | api/routers/auth.py:19-28 | Cookie max_age not refreshed; sliding expiry ineffective | open |
| R-13 | low | security | application/auth.py:151-160 | Expired sessions never purged | open |
| R-14 | low | smell | infrastructure/csv/codec.py:41 | CSV import reports wrong row numbers | open |
| R-15 | low | smell | application/search.py:15, 74 | Empty query capped at 50 answers (F3-08) | open |
| R-16 | low | smell | infrastructure/ai/ollama.py:17-25 | Duplicated provider error handling | open |
| R-17 | low | smell | application/ai.py:72 and others | Magic numbers and strings | open |
| R-18 | low | smell | application/demo.py:24, ports.py:149 | Dead code (kinds(), Texts) | open |
| R-19 | low | smell | web/static/js/views/answers.js:6 | Server rules duplicated in frontend | open |
| R-20 | low | smell | api/schemas.py:72, 151 | Silent `or 0` / `is not None` fallbacks | open |
| R-21 | low | smell | web/static/js/views/auth.js:8 | Behaviour switched by flags | open |
| R-22 | low | smell | application/answers.py:54 | Revision bumped once per imported row | open |
| R-23 | low | smell | domain/users.py:44-46 | Last-admin rule raises InvalidInputError instead of ConflictError | open |
| R-24 | low | smell | infrastructure/db/repositories/activity.py:47-56 | Upsert reopens resolved questions; resolved state stored twice | open |
| R-25 | low | smell | container.py:216-245 | build_container longer than 25 lines | open |
| R-26 | low | smell | infrastructure/db/repositories/content.py:171-175 | IntegrityError mid-import fails remaining rows with 500 | open |
| R-27 | low | architecture | infrastructure/search/distance.py:8 | Drift from DESIGN (OSA, composition root location) | open |
| R-28 | low | architecture | tests/qa, tests/integration | QA and repository integration tests missing | open |
