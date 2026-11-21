# Ready Reply v1.0.0 — QA report

Date: 2026-11-21. Scope: the source under `readyreply/`, the release zip `dist/ready-reply-v1.0.0.zip`, `README.md`, `start.sh` and `start.bat`. The tests were written only from `docs/CRITERIA.md`, `docs/DESIGN.md`, `README.md` and the code. The product code was not changed.

## 1. Summary

- **230 new automated QA tests** in `tests/qa/`: API, live server with threads, real Chromium at 1280 px and 360 px, and a real `./start.sh` run from the release zip.
- **22 tests fail** against the current code. They expose **15 defects** (QA-01 … QA-15): 0 high, 5 medium, 10 low. All are open.
- Held up under attack: SQL injection, and HTML/JS injection in every text field. In the browser nothing ran and the text was shown literally. Also: the permission matrix (anonymous, staff, CSRF, foreign Origin, logout, expiry, deactivated and deleted users), concurrency (first-admin setup, same-title creates, copies, unanswered records, demo loads, imports), CSV size and row limits, search relevance and speed, and the rule that AI never saves anything by itself.
- Weak spots:
  - Unicode handling of titles (emoji-only, invisible and decomposed characters).
  - CSV header handling.
  - The session cookie is not renewed while the user is active.
  - The README backup advice.
  - A stale release zip.

Test run (`pytest tests/qa -q -p no:cacheprovider`):

```
22 failed, 208 passed in 100.89s (0:01:40)
```

The project's `addopts` already contains `-q`, so the exact command prints only the `FAILED` lines. The counts above come from the same run with `-o addopts="--strict-markers"`.

Test files:

| File | What it attacks |
|---|---|
| `tests/qa/test_qa_input.py` | Strange input: emojis, RTL and zero-width characters, NFC/NFD, NUL, very long strings, whitespace-only text, numbers, SQL and HTML in every field, error-code translations |
| `tests/qa/test_qa_security.py` | Every endpoint as anonymous and as staff; missing, forged and old CSRF tokens; foreign Origin and Referer; logout, expiry, cookie renewal; deactivated, deleted and demoted users; login throttling |
| `tests/qa/test_qa_concurrency.py` | Parallel first-admin setup, same-title creates, duplicates, copies (20 users and one user double-clicking), unanswered records from 20 users, demo replace, CSV imports |
| `tests/qa/test_qa_csv.py` | Exactly 1 MiB vs 1 MiB + 1 byte (with and without Content-Length), 5,000 vs 5,001 rows, BOM, LF/CRLF/CR, `;`, quotes, embedded newlines, binary, UTF-16, Latin-1, header order and case, extra columns, formula injection, round trip |
| `tests/qa/test_qa_search.py` | Relevance (typos, accents, synonyms, wording), robustness, title over body, live index updates, P8 with 1,000 answers and 50 varied queries |
| `tests/qa/test_qa_ai.py` | Fake Ollama/OpenAI server: drafts never saved; fallback on HTTP 500, empty, non-JSON, wrong shape, refused connection, slow and trickling replies; API key never logged; prompt privacy; staff blocked |
| `tests/qa/test_qa_browser.py` | Chromium: HTML injection on every screen, language switch, P2/P3/P4/P5/P8 end-to-end, expired session on Copy, fast typing, variables form |
| `tests/qa/test_qa_promises.py` | P1, P6, and P7 (no outbound connection with the default provider, no external URLs, CSP) |
| `tests/qa/test_qa_install.py` | Release zip contents, `./start.sh` in a clean folder (offline install, migration, restart time, busy port), README backup procedure, `.env.example` completeness |

## 2. Public promises

| ID | Promise | Evidence | Result |
|---|---|---|---|
| P1 | Business variables are saved once and filled into every answer | `test_qa_promises.py::test_p1_variable_saved_once_fills_every_answer`: 3 answers use `{hours}` and all copies contain it; after `hours` changes, all 3 copies and search previews change. `test_p1_empty_or_unknown_variable_blocks_copy_and_records_nothing`. `test_qa_input.py::test_variable_value_with_placeholder_is_not_expanded_twice` | **PASS** |
| P2 | Smart search with typos, missing accents and different wording | `test_qa_search.py::test_opening_hours_found_with_typos_accents_and_wording` (17 queries, including `a que ora abren`, `hroario` and full-width letters), `test_relevance_for_common_customer_questions` (13 queries), `test_new_synonym_group_takes_effect_immediately`; `test_qa_browser.py::test_p2_phone_typing_finds_opening_hours` (360 px, typing `a que hora abren`). See QA-06 for stop-word-only queries | **PASS** |
| P3 | One-click copy, ready for WhatsApp Business | `test_qa_browser.py::test_p3_one_click_copy_keeps_whatsapp_text_exactly[desktop/phone]`: one click; the clipboard equals the rendered text with `*bold*`, `_italic_`, `~strike~`, a code block, a ZWJ emoji family, Hebrew and line breaks; exactly one copy event. **Manual (pending, owner):** checklist in section 6 | **PASS** (automated part) |
| P4 | Unanswered questions show the owner which answers are missing | `test_qa_browser.py::test_p4_unanswered_question_appears_and_disappears_when_answered`, `test_fast_typing_records_nothing`; `test_qa_concurrency.py::test_parallel_unanswered_from_twenty_users_counts_twenty` | **PASS** |
| P5 | Free, optional AI that suggests answers, always reviewed by a human | `test_qa_ai.py` (11 pass) and `test_qa_browser.py::test_p5_ai_draft_in_browser_is_saved_only_on_save` and `test_p5_ai_failure_in_browser_shows_manual_prompt`: the answer count stays 0 until Save, also after leaving the page; every failure mode falls back to the manual prompt with `ai.unavailable`. Two edge defects do not break the promise: QA-11 (the timeout is not a total deadline) and QA-12 (the prompt language ignores the UI language). **Manual (pending, owner):** real Ollama with `gemma3:4b` | **PASS** (with QA-11, QA-12 open) |
| P6 | Team-ready: roles, usage stats, CSV import/export, demo data | `test_qa_security.py` (roles and sessions), `test_qa_promises.py::test_p6_*`, `test_qa_csv.py` (37 pass). **Fails:** a CSV with header `Title,Category,Body,Tags` is accepted, but every row is rejected (QA-07). Also QA-08, QA-09, QA-10 | **FAIL** (QA-07) |
| P7 | Installs with a double click and runs locally. Customer data never leaves the computer | (a) `test_qa_promises.py::test_p7_default_provider_never_leaves_the_computer`; (b) and (c) `test_p7_no_external_urls_in_static_files_and_csp`; (d) `test_qa_install.py::test_start_sh_installs_offline_migrates_and_restarts_fast`, plus the manual clean install in section 4. Release and doc issues: QA-13, QA-14, QA-15. Windows was not executable here: review in section 5; owner checklist in section 6 | **PASS** (automated; Windows manual pending) |
| P8 | Done in 2 seconds; search < 200 ms with 1,000 answers | `test_qa_search.py::test_p8_search_p95_under_200ms_with_1000_answers`: 1,000 answers, ~3,000-word vocabulary, 50 varied queries including 200-char ones; median 6.6 ms, p95 11.1 ms, max 19.1 ms. `test_qa_browser.py::test_p8_type_to_clipboard_under_2_seconds_with_1000_answers`: typing to clipboard took 0.16–0.39 s | **PASS** |

## 3. Defects

### QA-01 — Different emoji-only or symbol-only titles count as the same title

- **Severity:** low
- **Steps:**
  1. As admin, `POST /api/answers` with title `🍔`. The response is 201.
  2. `POST /api/answers` with title `🍕`, or create `!!!` and then `☕`.
- **Expected:** both answers are created; the titles are different.
- **Actual:** 409 `answer.title_taken`. `normalize()` removes every non-alphanumeric character, so every emoji-only or symbol-only title gets the same empty key `""`, and the unique constraint fires.
- **Tests:** `tests/qa/test_qa_input.py::test_emoji_only_titles_are_distinct_answers`, `::test_punctuation_title_does_not_block_an_unrelated_emoji_title`
- **Status:** open

### QA-02 — Invisible characters bypass "title required" and "title taken"

- **Severity:** medium
- **Steps:**
  1. Create an answer with title `"⁠"`, `"­"` or `"​‌‍"`.
  2. On a library that has "Horario", create `"Hora​rio"`, `"Hor⁠ario"` or `"Ho­rario"`.
- **Expected:**
  1. 422 `answer.title_required`: the title is blank (F2-02).
  2. 409 `answer.title_taken`: the title looks exactly like "Horario" (F2-04).
- **Actual:**
  1. 201: an answer with an invisible title appears in the list.
  2. 201: two answers that look identical. Zero-width and format characters (category Cf) are neither stripped nor ignored. `normalize()` turns them into a space, so `hora rio` ≠ `horario`. Text pasted from WhatsApp or the web often carries such characters.
- **Tests:** `tests/qa/test_qa_input.py::test_invisible_only_title_is_rejected_as_empty[...]` (3 cases), `::test_title_differing_only_by_invisible_characters_is_a_duplicate[...]` (3 cases)
- **Status:** open

### QA-03 — Text is not NFC-normalized; decomposed accents count double

- **Severity:** low
- **Steps:**
  1. Create an answer whose title is `"Otra "` followed by 115 × `é` in NFD (e + U+0301). The text a macOS keyboard or some copy sources produce is 120 visible characters.
- **Expected:** accepted. The 120-character limit is about what the user sees, and the stored text is normalized.
- **Actual:** 422 `answer.title_too_long`. Limits count code points, and the text is stored decomposed. The same happens for bodies (4,000) and variables (2,000).
- **Test:** `tests/qa/test_qa_input.py::test_decomposed_accents_do_not_count_double_against_the_title_limit`
- **Status:** open

### QA-04 — A NUL byte is accepted in an answer, and the CSV backup then cannot be imported

- **Severity:** low
- **Steps:**
  1. `POST /api/answers` with title `"Horario\x00"`. The response is 201.
  2. `GET /api/csv/export`.
  3. Delete the answers and import the exported file.
- **Expected:** NUL is rejected or stripped on save, or the export can be re-imported (F10-01 round trip).
- **Actual:** the import of the app's own export fails with 422 `csv.invalid_encoding` for the **whole file**.
- **Test:** `tests/qa/test_qa_input.py::test_null_byte_in_an_answer_does_not_break_csv_backup`
- **Status:** open

### QA-05 — A long search query returns 422 instead of being cut to 200 characters

- **Severity:** low
- **Steps:**
  1. `GET /api/search?q=` with `"horario "` repeated 300 times (2,400 characters).
- **Expected:** 200, with the query cut to 200 characters (F3-11: "Queries are cut to 200 chars").
- **Actual:** 422 `request.invalid`, because `Query(max_length=2000)` rejects the request before the cut. The UI input has `maxlength=200`, so the browser is not affected; API clients and pasted URLs are.
- **Test:** `tests/qa/test_qa_input.py::test_search_accepts_a_long_pasted_query`
- **Status:** open

### QA-06 — A query made only of stop words hides every answer and is recorded as "unanswered"

- **Severity:** low
- **Steps:**
  1. Load the soda demo.
  2. Search `hola buenas`, `de la` or `que`.
- **Expected:** stop words are ignored (F3-03), so the query behaves like an empty query (F3-08/F3-09): all answers are shown and nothing is recorded.
- **Actual:** 0 results. The search screen then records the greeting as an unanswered question. `POST /api/unanswered` with `hola buenas` returns 204, and the entry is listed under Unanswered, which fills the owner's list with greetings.
- **Test:** `tests/qa/test_qa_input.py::test_stop_words_only_query_behaves_like_an_empty_query`
- **Status:** open

### QA-07 — A CSV header with capital letters or spaces is accepted, but every row is rejected

- **Severity:** medium
- **Steps:**
  1. Import `Title,Category,Body,Tags\nHorario,Info,Abrimos a las 8,hora\n`. A spreadsheet user would naturally write this header.
  2. Also try `title, category, body, tags`.
- **Expected:** `{"imported": 1, "rejected": []}`. The header check accepts these headers, so the rows must be read with them.
- **Actual:** `{"imported": 0, "rejected": [{"line": 2, "code": "answer.title_required"}]}`, and `answer.body_required` for the spaced header. `validate_header` trims and case-folds the header, but `row_to_draft` reads the cells by the exact names `title`, `category`, … So every row of the file is rejected with a misleading message.
- **Tests:** `tests/qa/test_qa_csv.py::test_header_with_capital_letters_imports_the_rows`, `::test_header_with_spaces_imports_the_rows`
- **Status:** open

### QA-08 — CSV round trip strips a leading apostrophe the user typed

- **Severity:** low
- **Steps:**
  1. Create an answer titled `'=50% descuento`.
  2. Export, delete, and import the export.
- **Expected:** the title comes back as `'=50% descuento` (F10-01).
- **Actual:** it comes back as `=50% descuento`. Export does not escape a cell that already starts with `'`, but import removes a leading `'` when the next character is `=`, `+`, `-` or `@`.
- **Test:** `tests/qa/test_qa_csv.py::test_round_trip_keeps_a_title_that_starts_with_apostrophe_and_equals`
- **Status:** open

### QA-09 — The session cookie is not renewed, so active users are logged out after RR_SESSION_HOURS anyway

- **Severity:** medium
- **Steps:**
  1. Log in. The cookie has `Max-Age=43200` (12 h).
  2. Keep using the app. At 11 h 56 min a request extends the server session (`ResolveSession._refresh`).
- **Expected:** only **idle** sessions expire (F6-08). When the server extends the session, the response re-sends `rr_session` with a fresh `Max-Age`.
- **Actual:** no `Set-Cookie` is sent. The browser drops the cookie 12 h after login, even though the server session is still valid, so a staff member who works all day is logged out mid-shift. Verified at the API level with a controlled clock. With `RR_SESSION_HOURS=1`, the server still accepted the session at 86 minutes, while the cookie had a 60-minute lifetime.
- **Test:** `tests/qa/test_qa_security.py::test_active_session_cookie_is_renewed_with_the_server_session`
- **Status:** open

### QA-10 — Login throttling is per device and user, not per user

- **Severity:** low
- **Steps:**
  1. Send 5 failed logins for `admin`, each from a different client address (192.168.1.1–5).
  2. Send a 6th failed login from 192.168.1.99.
- **Expected:** 429 `auth.too_many_attempts` (F6-07: "5 failed logins for one user").
- **Actual:** 401. The throttle key is `client_address:username`, so every device on the Wi-Fi gets its own 5 attempts per 5 minutes.
- **Test:** `tests/qa/test_qa_security.py::test_login_throttle_is_per_user_not_per_address`
- **Status:** open

### QA-11 — RR_AI_TIMEOUT_SECONDS is not a total deadline

- **Severity:** low
- **Steps:**
  1. Set `RR_AI_PROVIDER=ollama` and `RR_AI_TIMEOUT_SECONDS=1`.
  2. Point the app at a provider that streams its JSON reply in 8-byte chunks every 0.4 s.
  3. Click Suggest.
- **Expected:** after ~1 s, the app falls back to the manual prompt with `ai.unavailable` (F8-06: "exceeds RR_AI_TIMEOUT_SECONDS").
- **Actual:** the request takes 2.8 s and returns a draft. `httpx.Client(timeout=…)` applies the timeout to each connect or read, not to the whole call. A slow model that keeps producing output can hold the request (and a worker thread) far longer than configured.
- **Test:** `tests/qa/test_qa_ai.py::test_timeout_is_a_total_deadline_not_per_chunk`
- **Status:** open

### QA-12 — The AI prompt ignores the language chosen in the UI

- **Severity:** low
- **Steps:**
  1. Run with the default `RR_LOCALE=es`.
  2. In the browser, click **EN**.
  3. Go to Unanswered and click **Suggest with AI** (manual provider).
- **Expected:** the prompt asks for a reply in the UI language, English (F8-07).
- **Actual:** the prompt is in Spanish and asks for a reply in "español". The suggest API never receives the UI language; server-side texts always follow `RR_LOCALE`. The duplicate suffix shows the same behavior: it creates "(copia)" in the English UI.
- **Test:** `tests/qa/test_qa_browser.py::test_ai_prompt_is_in_the_language_the_user_chose`
- **Status:** open

### QA-13 — The release zip is stale

- **Severity:** low
- **Steps:**
  1. Compare `dist/ready-reply-v1.0.0.zip` with the source tree and with `scripts/build_dist.py`.
- **Expected:** the zip contains the current code and every file the build script lists.
- **Actual:**
  - `readyreply/__main__.py` in the zip lacks the `flush=True` from commit "Flush the startup banner". The banner may not appear when output is piped or redirected.
  - `docs/DESIGN.md` and `docs/CRITERIA.md`, which `DOCS` lists, are missing.
  - The zip was built before the last source changes.
- **Test:** `tests/qa/test_qa_install.py::test_release_zip_matches_the_source_and_build_script`
- **Status:** open

### QA-14 — Following the README backup advice can lose the latest data

- **Severity:** medium
- **Steps:**
  1. Run the installed app and create an answer.
  2. Close the terminal. This sends SIGHUP; on Windows, closing the console window is the documented way to stop ("Close it to stop the program").
  3. Copy only `data/readyreply.db`, as the FAQ says.
- **Expected:** the copy contains all data.
- **Actual:** the copy lacks the last answer. The database runs in WAL mode; when the process is not stopped gracefully, the recent writes stay in `readyreply.db-wal`, which the README does not mention. Reproduced with SIGHUP (automated) and with SIGKILL (manually: 13 instead of 14 answers in the copied file). A graceful SIGTERM or Ctrl+C checkpoints correctly.
- **Test:** `tests/qa/test_qa_install.py::test_readme_backup_after_closing_the_window_keeps_all_data`
- **Status:** open

### QA-15 — `.env.example` does not list every setting

- **Severity:** low
- **Steps:**
  1. Compare the `Settings` fields with `.env.example`.
- **Expected:** every `RR_*` option is listed. The README says "every option is an `RR_*` environment variable. See `.env.example`."
- **Actual:** `RR_MAX_CSV_BYTES` and `RR_COOKIE_SECURE` are missing.
- **Test:** `tests/qa/test_qa_install.py::test_env_example_lists_every_setting`
- **Status:** open

### Checked and not defects (for the record)

- **SQL injection:** in answers, variables, synonyms, usernames, CSV cells, search and unanswered questions, it is always stored or treated as plain text.
- **HTML injection:** shown literally on every screen in Chromium: search cards, missing-variable warning, editor, answer list, toast, business data, unanswered, stats. No element was injected, no script ran, no dialog appeared.
- **Permissions:**
  - All 28 routes return 401 to anonymous users.
  - All admin routes return 403 to staff, and nothing changes.
  - Missing, empty, forged or old CSRF tokens give 403 `auth.csrf_failed` on all 17 state-changing routes.
  - Foreign, `null`, suffix and userinfo Origins and a foreign Referer give 403.
  - Deactivated and deleted users lose their sessions at once; a demoted admin loses admin rights on the next request.
- **Concurrency:**
  - 12 parallel first-admin setups: exactly 1 admin.
  - 12 parallel creates of "Horario" variants: exactly 1 answer.
  - 20 users copying: 20 events. One user's 10 parallel clicks: 1 event.
  - 20 users recording one question: `times_searched = 20`.
  - Parallel demo replace and parallel imports: no duplicates and no 5xx.
  - Parallel duplicates of one answer: some return 409, never 5xx, and titles stay unique.
- **CSV limits:**
  - Exactly 1,048,576 bytes is accepted; one byte more gives 413, also for a chunked upload without Content-Length.
  - 5,000 rows are imported; 5,001 give 422 and nothing is imported.
  - BOM/no BOM, LF/CRLF/CR and `;` all work.
  - Formula cells starting with `=`, `+`, `-` or `@` are prefixed with `'` on export.
- **Flaky-looking result that is not a product bug:** Playwright can send keystrokes before the search bar is shown, and those keystrokes are lost. A person cannot type into a hidden field, so the test now waits for the first results.

## 4. Clean install (Linux) — log summary

The zip `dist/ready-reply-v1.0.0.zip` existed, so the build was not run. It was unzipped into a new empty folder under `/tmp`, and started only as the README says (`./start.sh`), with `RR_OPEN_BROWSER=false RR_PORT=8731` set in the environment. Python 3.13.

| Step | Result |
|---|---|
| Unzip | `start.sh` keeps its executable bit; `.env.example` and 46 wheels are present |
| First `./start.sh` | Printed "Installing Ready Reply (first run only)...". Created `.venv` and installed offline from `wheels/` (`--no-index`). Created `.env` and `data/readyreply.db`. Alembic ran `-> 0001, initial schema`. HTTP 200 after **~7 s** |
| Browser (Chromium) | The first screen was "Bienvenido a Ready Reply" (create administrator). Created the admin, loaded the soda demo from **Demo & CSV**, searched `a que ora abren`: the first result was "Horario". **Copiar** put the exact rendered text in the clipboard. No script errors |
| Stop (SIGTERM to the process I started) | Clean exit; the WAL was checkpointed |
| Second `./start.sh` | No reinstall; data kept (`needs_setup: false`); HTTP 200 after **0.7 s** (F11-02 < 10 s) |
| Second instance on the same busy port | Moved to 8732 and printed that URL (F11-03) |
| Abrupt stop (SIGKILL), then copying only `readyreply.db` | The copy lost the last answer → QA-14 |

Every server process started for QA was stopped afterwards. The same flow is automated in `tests/qa/test_qa_install.py`.

### README issues

1. **Backup advice is unsafe (QA-14).** "To back up, copy that file while the program is closed" does not mention the `readyreply.db-wal` and `readyreply.db-shm` files. Closing the window is not a graceful stop.
2. **macOS is not offline.** The zip has wheels only for Windows and Linux x86_64 (cp312/cp313), so the first macOS run needs internet. The README does not say so.
3. **Linux prerequisites are missing.** On Debian and Ubuntu, `python3 -m venv` needs the `python3-venv` package; without it, `start.sh` stops with a pip/ensurepip error. The README says only "It needs Python 3.12 or newer".
4. **How to stop on Linux and macOS is not stated.** The script runs in the foreground: Ctrl+C stops it gracefully, while closing the terminal does not (see 1).
5. **Ports.** "Uses the next free port (8001, 8002…)": the search stops at 8010, and after that the app exits with a message. The README does not say this.
6. **Settings.** "Every option is an `RR_*` environment variable. See `.env.example`" is incomplete (QA-15). It also does not say that `start.sh`/`start.bat` create `.env` on the first run, or that environment variables override `.env` (both verified).
7. **Bundled docs.** The release zip lacks `docs/DESIGN.md` and `docs/CRITERIA.md` (QA-13). The README links only `docs/ARCHITECTURE.md` and the screenshots, which are present.

## 5. Windows `start.bat` — review (not executable here)

The script uses CRLF line endings, which is good for labels and `goto` in `cmd`. It is identical in the zip and in the source. Risks:

1. **Python 3.14 or 32-bit/ARM64 Python with no internet.** `:find_python` accepts `py -3.14` and any `python` ≥ 3.12. The bundled wheels are only `win_amd64` cp312/cp313, so the `--no-index` install fails, and the fallback `pip install -r requirements.txt` needs internet. Offline, this ends at ":failed" with no clear reason.
2. **Python just installed by winget.** `--scope user` installs Python, but `PATH` is not refreshed in the running `cmd`. The script handles this by checking `%LOCALAPPDATA%\Programs\Python\Python312|313\python.exe`. If winget installs elsewhere (machine scope, policy, an older winget), it falls through to the download page. winget can also take minutes, or fail on a first-time source agreement or UAC.
3. **Microsoft Store `python` alias.** A missing Python may hit the Store alias. The check `python -c ...` returns non-zero, so it is skipped, but the Store may open in front of the user.
4. **The install stamp is a fixed name.** It is `.venv\installed-1.0.0.txt`, unlike `start.sh`, which uses a checksum of `requirements.txt`. An update that changes dependencies but keeps 1.0.0 will not reinstall.
5. **A failed install leaves a half-built `.venv`.** The message asks the user to delete the folder by hand.
6. **Closing the window kills Python without a graceful shutdown.** The README tells users to do this, so the WAL is not checkpointed and the README backup procedure loses data (QA-14).
7. **The suggested folder `Documents\Ready Reply` is often OneDrive-synced on Windows 10/11.** A venv with thousands of files and a live SQLite database in a synced folder risks file locks, slow first runs and sync conflicts.
8. **Firewall.** The prompt is for `.venv\Scripts\python.exe`. If the Wi-Fi profile is "Public", choosing "Allow on private networks" does not help phones. The README mentions private networks but not how to check the profile.
9. **Paths with `%` or `!` in the folder name.** `cd /d "%~dp0"` is quoted, but a `%` in the path can break later `%PY%`-style expansion. This is rare.
10. **`pause` after the server exits.** It keeps errors visible, which is good. Ctrl+C prints "Terminate batch job (Y/N)?", which may confuse users.

## 6. Manual checks pending for the owner

**P3 — WhatsApp (10 min)**
1. Load the soda demo.
2. Copy "Horario" and "Menú del día".
3. Paste into WhatsApp Web and into WhatsApp Business on a phone.
4. Check that `*bold*` shows as bold, `_italic_` as italic, and that emojis and line breaks are kept.
5. Repeat on a phone over `http://192.168.x.x:8000` (F4-06 fallback copy).

**P5 — real Ollama**
1. Install Ollama and run `ollama pull gemma3:4b`.
2. Search an unknown question, click **Suggest with AI**, and wait for the draft (10–40 s).
3. Leave the page and confirm that no answer was created.
4. Suggest again, edit the draft and save; check that the question is resolved.
5. Stop Ollama and check that the manual prompt appears with the notice.

**P7 — Windows 10/11 (10 min)**
1. Unzip to `Documents\Ready Reply`.
2. Double-click `start.bat`, and allow the firewall on private networks.
3. Create the admin.
4. Load a demo, search `a que ora abren`, and copy.
5. Open the app from a phone through the QR code.
6. Repeat on a PC without Python (the winget path).
7. Stop with Ctrl+C before you back up (see QA-14).
