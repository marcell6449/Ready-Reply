# Ready Reply — Acceptance criteria (v1)

Status: **DRAFT for review.**

## How to read this document

- Format: **Given / When / Then**.
- Each criterion has an ID (`F3-04`). Tests reference that ID in their name or docstring, so every criterion can be traced to a test.
- Example customer queries are in Spanish on purpose. The target market writes in Spanish, and accent handling can only be tested with real accented words.
- `admin` means an administrator and `staff` means a staff member. "Variables" means business variables.

---

## Priority 1

### F1 — Business variables

| ID | Given | When | Then |
|---|---|---|---|
| F1-01 | a new database | the admin opens Business data | the 6 built-in variables (`name`, `hours`, `address`, `sinpe`, `phone`, `prices`) exist with empty values |
| F1-02 | the variables form | the admin saves `hours = "L-V 7am–5pm 🕖"` | it is stored and returned exactly, emoji and en dash included |
| F1-03 | the variables form | the admin adds a custom variable with key `wifi` and label "Wi-Fi password" | it is saved and can be used as `{wifi}` |
| F1-04 | the variables form | the admin adds a custom key that is invalid (`Wi Fi`, `1abc`, `ñame`, empty, or longer than 40 chars) | it is rejected with `variable.invalid_key` and nothing is saved |
| F1-05 | custom variable `wifi` exists | the admin adds `wifi` again | it is rejected with `variable.duplicate_key` |
| F1-06 | built-in variable `sinpe` | the admin tries to delete it | it is rejected with `variable.builtin_protected` |
| F1-07 | a value longer than 2,000 chars | it is saved | it is rejected with `variable.value_too_long` |
| F1-08 | staff is logged in | staff sends `PUT /api/variables` | the response is 403 `auth.forbidden` and nothing changes |
| F1-09 | a value with HTML `<script>alert(1)</script>` | it is saved and later shown in the UI | it is shown as literal text and no script runs |

### F2 — Answers

| ID | Given | When | Then |
|---|---|---|---|
| F2-01 | an admin | they create an answer with title, category, body `"Abrimos {hours}"` and tags | it appears in the list and in search |
| F2-02 | an admin | they submit an empty or whitespace-only title or body | it is rejected with `answer.title_required` / `answer.body_required` |
| F2-03 | a title longer than 120 chars or a body longer than 4,000 chars | it is submitted | it is rejected with `answer.title_too_long` / `answer.body_too_long` |
| F2-04 | an answer titled "Horario" exists | the admin creates "horário" or " HORARIO " | it is rejected with `answer.title_taken` |
| F2-05 | an answer exists | the admin edits it | `updated_at` changes and search reflects the new text immediately |
| F2-06 | an answer with copy history | the admin deletes it and confirms | it disappears from the list, search and stats |
| F2-07 | answer "Horario" | the admin duplicates it | "Horario (copia)" is created (the word follows the language). Duplicating again creates "Horario (copia 2)". |
| F2-08 | staff is logged in | staff tries to create, edit, delete or duplicate | the response is 403 and nothing changes |
| F2-09 | the admin double-clicks **Save** on a new answer | — | exactly one answer is created. The button is disabled while saving, and the server also rejects the duplicate title. |
| F2-10 | an answer id that doesn't exist, or belongs to another `business_id` | it is edited or deleted | the response is 404 `answer.not_found` |
| F2-11 | tags `"Pago, SINPE, pago , "` | the answer is saved | the stored tags are `["pago", "sinpe"]` |
| F2-12 | a body with emojis and line breaks | it is saved and copied | emojis and line breaks are kept exactly |

### F3 — Tolerant search

Fixture: the test-only soda business plus the synonym group `horario = abren, atienden, cierran, hora, abierto`.

| ID | Given | When | Then |
|---|---|---|---|
| F3-01 | the fixture | the user searches `horario` | "Horario" is the first result |
| F3-02 | the fixture | the user searches `HORARIO`, `Horário` or `horario` with an accent | "Horario" is first in every case |
| F3-03 | the fixture | the user searches `¿A qué hora abren?` | "Horario" is first (stop words and punctuation ignored, synonym match) |
| F3-04 | the fixture | the user searches `orario`, `hroario` or `horaio` (one typo) | "Horario" is first |
| F3-05 | the fixture | the user searches `sinpe` or `simpe` | the SINPE answer is first |
| F3-06 | the fixture | the user searches `hor` (prefix) | "Horario" appears in the results |
| F3-07 | the fixture | the user searches `xyzzy` | no results |
| F3-08 | the fixture | the user searches an empty or whitespace-only string, or only stop words | the answers ordered by copy count then title (at most 50) |
| F3-09 | the fixture | the user searches `🍔` or `!!!` | no error. The result is the same as an empty query. |
| F3-10 | the fixture | the user searches `' OR 1=1 --` or `%` or `_` | no error and no extra results (the input is treated as plain text) |
| F3-11 | a query of 500 chars | it is searched | the response is 200 within the P8 limit. Queries are cut to 200 chars. |
| F3-12 | the admin adds the synonym group `envio = delivery, express, domicilio` | the user searches `express` | the delivery answer is first |
| F3-13 | two answers match, one in the title and one only in the body | the user searches | the title match ranks higher |
| F3-14 | a 3-letter word with one typo (`sal` vs `sol`) | it is searched | no fuzzy match. Short words need an exact or prefix match. |
| F3-15 | a synonym group with fewer than 2 terms, or a term already in another group | it is saved | it is rejected with `synonym.too_few_terms` / `synonym.term_in_use` |

### F4 — One-click copy

| ID | Given | When | Then |
|---|---|---|---|
| F4-01 | the answer `"Abrimos {hours}"` and `hours = "L-V 7–5"` | the user clicks **Copy** | the clipboard holds `"Abrimos L-V 7–5"` and a "Copied ✓" toast is shown |
| F4-02 | the answer uses `{sinpe}` and `sinpe` is empty | the user clicks **Copy** | nothing is copied. A warning names the missing "SINPE number". Admins see a link to fill it in. |
| F4-03 | the answer uses `{undefined_key}` | the user clicks **Copy** | same as F4-02: blocked, and the key is listed as missing |
| F4-04 | the answer has `{{literal}}` | it is copied | the text contains `{literal}` |
| F4-05 | the answer has an unclosed `{hours` | it is copied | the text is copied as written |
| F4-06 | a phone on `http://192.168.x.x` (not a secure context) | the user taps **Copy** | the fallback copy works and the toast is shown |
| F4-07 | the user double-clicks **Copy** | — | the text is copied, and only **one** copy event is recorded (3-second dedupe) |
| F4-08 | a variable value containing `{hours}` | it is rendered | it is **not** expanded again (single pass) |
| F4-09 | the user's session has expired | they click **Copy** | the response is 401. The UI goes to the login screen and keeps the search text. |

### F9 — Demo data (removed)

Removed at the owner's request: the product has no sample data. Tests use test-only fixtures
in `tests/fixtures/businesses/`, loaded through the public API.

### F12 — Import from WhatsApp chats

| ID | Given | When | Then |
|---|---|---|---|
| F12-01 | chats exported from WhatsApp Business (Android `.txt`, iPhone `.zip`, Spanish or English) | the admin drops them on **Import** | a preview lists the answers, unanswered questions and business details found. Nothing is saved yet. |
| F12-02 | the business appears in every chat | the chats are analyzed | it is chosen as the business automatically; the admin can change it |
| F12-03 | the same question asked in different words in several chats | the chats are analyzed | it becomes one answer with the business's reply and the number of times it was asked |
| F12-04 | a question the business never answered | the chats are analyzed | it is listed as unanswered with its count, and saved to **Unanswered** on import |
| F12-05 | the business wrote its SINPE number, hours or address | the chats are analyzed | they are proposed as business details; on import they are saved and written as `{sinpe}`, `{hours}`, `{address}` inside the imported answers |
| F12-06 | an answer with the same title already exists | the preview is shown | it is marked "already exists", unchecked, and skipped on import |
| F12-07 | greetings, thanks, deleted messages, media and system notices | the chats are analyzed | they are never taken as questions |
| F12-08 | a file that is not a chat, a broken file, or a zip bomb | it is uploaded | it is skipped or rejected with `whatsapp.no_messages`, `whatsapp.invalid_file` or `whatsapp.too_large` (20 MB) |
| F12-09 | staff | they call the import endpoints | the response is 403 |
| F12-10 | customer names and numbers in the chats | the import is saved | they are not stored anywhere (not even the file name) |
| F12-11 | automatic import is on (default) | a `.txt` or `.zip` appears in `Chats de WhatsApp`, or a file named like a WhatsApp export appears in Downloads | within seconds it is imported without any click: new answers, unanswered questions, and only the business details that are still empty |
| F12-12 | the same file, or a re-export of the same chat | it appears again | nothing is counted twice; only new questions are added |
| F12-13 | a file in the folder that is not a chat | it is scanned | it is noted once in the history as ignored and never retried |
| F12-14 | the admin opens **Import** | — | it shows that automatic import is on, the watched folders and the latest automatic imports, refreshing by itself |

### F11 — Installer

| ID | Given | When | Then |
|---|---|---|---|
| F11-01 | a clean folder with the unzipped release on Linux or macOS | the user runs `./start.sh` | a venv is created, dependencies are installed from the bundled wheels, the database is migrated, the browser opens on the app and the first-run setup is shown |
| F11-02 | it has already been installed | `start.sh` is run again | it skips installing, keeps the data and starts in under 10 seconds |
| F11-03 | port 8000 is busy | the user starts the app | it uses the next free port up to 8010 and opens that URL |
| F11-04 | Windows 10/11 with Python 3.12+ | the user double-clicks `start.bat` | same as F11-01 *(manual check by the owner, see P7)* |
| F11-05 | Windows without Python | the user double-clicks `start.bat` | it offers to install Python with `winget`, then continues. Without `winget`, it shows clear steps and a link. *(manual)* |
| F11-06 | a new database | the app starts | Alembic migrates to the latest revision, and the business row with its built-in variables exists |
| F11-07 | an existing database from an older revision | the app starts | it is migrated forward with no data loss |
| F11-08 | the language menu | the user switches to English | every visible text changes to English, and the choice is remembered on that device |
| F11-09 | the translations file | a test compares `es` and `en` | both have exactly the same keys, and every key used in the JS exists |

---

## Priority 2

### F5 — Unanswered questions

| ID | Given | When | Then |
|---|---|---|---|
| F5-01 | a search with no results, stable for 1.5 seconds | — | the question is recorded with `times_searched = 1` |
| F5-02 | the same question with different accents, case or word order | it is searched again later | the same entry's count goes up |
| F5-03 | the user types `h`, `ho`, `hor` quickly | — | nothing is recorded |
| F5-04 | a query shorter than 3 normalized chars | it has no results | it is not recorded |
| F5-05 | the same user submits the same question twice within 30 seconds (double Enter) | — | the count goes up only once |
| F5-06 | 20 parallel requests for the same new question from different users | — | one entry exists with `times_searched = 20` |
| F5-07 | an unanswered question | the admin clicks "Create answer" | the answer form opens prefilled. Saving marks the question resolved and hides it from the list. |
| F5-08 | a question containing `<img src=x onerror=alert(1)>` | it is listed | it is shown as literal text |
| F5-09 | staff | they view the unanswered list | it is allowed. Resolving or deleting returns 403. |

### F6 — Users and roles

| ID | Given | When | Then |
|---|---|---|---|
| F6-01 | a new database with no users | any page is opened | the user is sent to "Create administrator" |
| F6-02 | an admin already exists | someone sends `POST /api/setup` | the response is 409 `setup.already_done` |
| F6-03 | a password shorter than 8 chars | an account is created | it is rejected with `auth.weak_password` |
| F6-04 | the user table | it is inspected | it stores only Argon2id hashes (`$argon2id$...`), never the plain password |
| F6-05 | valid credentials | the user logs in | the session cookie is `HttpOnly`, `SameSite=Strict` and `Path=/` |
| F6-06 | wrong credentials | the user logs in | the response is 401 `auth.invalid_credentials` and does not reveal whether the username exists |
| F6-07 | 5 failed logins for one user within 5 minutes (from any device), or 20 from one address | a further attempt is made | the response is 429 `auth.too_many_attempts` |
| F6-08 | a session idle longer than `RR_SESSION_HOURS` | any request is made | the response is 401 `auth.session_expired` |
| F6-09 | the user logs out | the old cookie is reused | the response is 401 |
| F6-10 | a state-changing request without a valid `X-CSRF-Token`, or with a foreign `Origin` | it is sent | the response is 403 `auth.csrf_failed` |
| F6-11 | staff | they call any admin-only endpoint | the response is 403 |
| F6-12 | the only active admin | they try to demote or deactivate themselves | it is rejected with 409 `user.last_admin` |
| F6-13 | a deactivated user | they log in, or use an existing session | the response is 401 |
| F6-15 | first-run setup | the owner enters a WhatsApp number such as `8888-1234` | after creating the admin, the number is saved at once as the `{phone}` business detail (`+506 8888 1234`) and a welcome screen confirms it and lists the next steps |
| F6-16 | first-run setup | the WhatsApp number is invalid (`123`, letters) | it is rejected with `setup.invalid_whatsapp` and no administrator is created |
| F6-14 | a username `"  Ana "` exists as `ana` | someone creates `ANA` | it is rejected with `user.username_taken` |

### F7 — Statistics

| ID | Given | When | Then |
|---|---|---|---|
| F7-01 | copy events: A×5, B×3, C×1 | the admin opens Stats | top copied shows A, B, C in that order, with counts |
| F7-02 | unanswered questions with counts 7, 2, 4 | the admin opens Stats | they are listed 7, 4, 2. Resolved questions are excluded. |
| F7-03 | a new database | the admin opens Stats | a friendly empty state is shown, not an error |
| F7-04 | staff | they request `/api/stats` | the response is 403 |

### F10 — CSV import and export

| ID | Given | When | Then |
|---|---|---|---|
| F10-01 | answers with accents, emojis, commas, quotes and line breaks | they are exported and re-imported into an empty library | the result is identical (round trip) |
| F10-02 | an export | it is opened | it is UTF-8 **with BOM** (opens correctly in Excel). The header is `title,category,body,tags` and tags are separated by `\|`. |
| F10-03 | an answer whose title starts with `=`, `+`, `-` or `@` | it is exported | the cell is prefixed with `'` |
| F10-04 | a file separated by `;` | it is imported | it is parsed correctly |
| F10-05 | a file with 3 valid rows and 2 invalid rows (empty title, body too long) | it is imported | the 3 valid rows are imported. The report lists row numbers 3 and 5 with their error codes. |
| F10-06 | a row whose title already exists | it is imported | it is skipped and reported as `answer.title_taken` |
| F10-07 | a file larger than 1 MB | it is uploaded | the response is 413 `csv.too_large` **before** parsing |
| F10-08 | a file with more than 5,000 rows | it is uploaded | the response is 422 `csv.too_many_rows` and nothing is imported |
| F10-09 | missing or misspelled headers, a binary or non-UTF-8 file, or an empty file | it is uploaded | the response is 422 `csv.invalid_header` / `csv.invalid_encoding` / `csv.empty` and nothing is imported |
| F10-10 | staff | they use import or export | the response is 403 |

---

## Priority 3

### F8 — Optional AI (free)

| ID | Given | When | Then |
|---|---|---|---|
| F8-01 | `RR_AI_PROVIDER=ollama` (default) and Ollama is running with the model | the admin clicks "Suggest answer with AI" on an unanswered question | a draft is shown in an editable field, with a "Generating…" indicator while waiting |
| F8-02 | a draft in the field | the admin edits it and clicks **Save** | a normal answer is created, and the question is resolved |
| F8-03 | any provider | a suggestion arrives | **nothing is saved** until the admin clicks Save. Leaving the page creates nothing. |
| F8-04 | `RR_AI_PROVIDER=manual` | the admin clicks Suggest | a prompt with the business variables and the question is shown with a **Copy prompt** button and a paste field. If `RR_AI_CHAT_URL` is set, it opens in a new tab. |
| F8-05 | `RR_AI_PROVIDER=openai_compatible` with an API key in `.env` | the admin clicks Suggest | a draft fills the editable field |
| F8-06 | Ollama isn't installed or running, the model isn't pulled, the provider errors, or it exceeds `RR_AI_TIMEOUT_SECONDS` | the admin clicks Suggest | a message `ai.unavailable` explains how to install Ollama, and the app falls back to the manual flow (F8-04) |
| F8-07 | the prompt | it is built | it contains only variables, existing answer titles and the question, and asks for a reply in the language the user chose in the UI. It never contains user names, passwords or stats. |
| F8-08 | a new provider class registered in the composition root | the app starts with it configured | it is used, and no other module was modified (checked in the architecture docs and a test with a fake provider) |
| F8-09 | staff | they call `/api/ai/suggest` | the response is 403 |
| F8-10 | the API key | the logs are inspected | the key never appears |

---

## Public promises

| ID | Promise | Verification |
|---|---|---|
| P1 | Business variables are saved once and filled into every answer | API test: set `hours`, copy 3 different answers that use it, and all contain the value. Change `hours` and all 3 change. Plus F4-01 and F4-02. |
| P2 | Smart search with typos, missing accents and different wording | F3-01 to F3-06 and F3-12 in one test module tagged `promise_p2`. Plus an E2E test on a 360 px phone typing `a que hora abren`. |
| P3 | One-click copy, ready for WhatsApp Business | E2E test at 1280 px and 360 px. One click on Copy, then read the clipboard through Playwright: it equals the rendered text, with line breaks and emojis kept. WhatsApp formatting (`*bold*`, `_italic_`) passes through unchanged. **Manual:** paste into WhatsApp Web and WhatsApp Business on a phone (owner checklist in `docs/QA_REPORT.md`). |
| P4 | Unanswered questions show the owner which answers are missing | E2E test: search something with no answer, wait, and the question appears under Unanswered with its count. Create an answer from it and it disappears. |
| P5 | Free, optional AI that suggests answers, always reviewed by a human | F8-01 to F8-06 against a fake Ollama HTTP server. Ollama and the manual provider need no account, key or payment. The test checks that the answer count doesn't change until Save. **Manual:** owner checklist with real Ollama and `gemma3:4b`. |
| P6 | Team-ready: roles, usage stats, CSV import/export | F6, F7 and F10 suites, tagged `promise_p6`. Answers from WhatsApp chats: F12. |
| P7 | Installs on Windows with a double click and runs locally. Customer data never leaves the computer. | **Automated:** (a) a test that blocks all non-loopback sockets and runs the whole API suite with the default provider; (b) a test that no file in `web/static` references an external `http(s)://` URL; (c) the CSP header; (d) `start.sh` run from the zip in a clean folder. **Manual (owner, on Windows):** a documented 10-minute checklist: unzip, double-click, create admin, load demo, search, copy. |
| P8 | Done in 2 seconds; search < 200 ms with 1,000 answers | **Perf test:** load 1,000 generated answers and run 50 varied queries (typos, accents, synonyms). The p95 server time must be < 200 ms. **E2E:** with 1,000 answers loaded, measure from typing the query to text in the clipboard. It must be < 2 seconds. |

---

## Edge-case checklist (each one maps to at least one criterion)

| Case | Criteria |
|---|---|
| Empty text | F2-02, F3-08, F10-09 |
| Missing variables | F4-02, F4-03, F9-03 |
| Accents | F2-04, F3-02, F5-02 |
| Emojis | F1-02, F2-12, F3-09, F10-01 |
| 1,000 answers | P8 |
| Malformed CSV | F10-05, F10-07, F10-08, F10-09 |
| User without permissions | F1-08, F2-08, F5-09, F6-11, F7-04, F9-04, F10-10, F8-09 |
| Double click | F2-09, F4-07, F5-05 |
| Expired session | F4-09, F6-08, F6-09 |
| New database | F1-01, F6-01, F7-03, F11-06 |
| Injection (SQL / HTML) | F1-09, F3-10, F5-08, F10-03 |
| Concurrency | F5-06 |
