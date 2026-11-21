# Ready Reply — Architecture guide for developers

This guide explains how the code is organized and how to extend it without
breaking it. The full design rationale is in [DESIGN.md](DESIGN.md), and the
acceptance criteria are in [CRITERIA.md](CRITERIA.md).

## Layers

```
web/static (HTML, CSS, JS)  →  api (FastAPI)  →  application (use cases + ports)
                                                   ↙                       ↘
                                       domain (pure rules)        infrastructure (adapters)
```

| Layer | Folder | May import | Never imports |
|---|---|---|---|
| Domain | `readyreply/domain` | the standard library | FastAPI, SQLAlchemy, httpx, rapidfuzz, files, network |
| Application | `readyreply/application` | domain, `ports.py` | infrastructure, FastAPI |
| Infrastructure | `readyreply/infrastructure` | domain, application ports, third-party libraries | api |
| API | `readyreply/api` | everything above, through the container | — |
| Composition root | `readyreply/container.py` | everything | — |

`container.py` is the **only** place that creates concrete classes and connects them to ports.

## Request lifecycle (copy an answer)

1. `web/static/js/views/search.js` copies the rendered preview inside the click handler, so phones allow it. Then it calls `POST /api/answers/{id}/copy`.
2. `api/routers/content.py` → `api/deps.py` resolves the session cookie, checks the CSRF header and builds an `Actor`.
3. `application/copying.py` (`CopyAnswer`) checks `Action.COPY`, loads the answer and variables through the `UnitOfWork` port, and renders with `domain/templates.py`. It records a copy event unless it is a double click.
4. `infrastructure/db/unit_of_work.py` commits the SQLAlchemy transaction.

## Extension points

### Add a search strategy

Implement the `Scorer` protocol (`domain/search/scorers.py`):

```python
class SoundsLikeScorer:
    def matches(self, token: str, index: SearchIndex) -> Iterator[TermMatch]:
        ...  # yield TermMatch(term_in_vocabulary, strength_between_0_and_1)
```

Then add it to the list in `container.py::_search`. The engine combines all scorers, so no
other file changes. Ranking constants live in `domain/search/scoring_config.py`.

### Add an AI provider

Write a class with `suggest(prompt: str) -> Draft | ManualHandoff`. Raise
`ProviderUnavailableError` when it cannot answer; the app then falls back to the
copy-and-paste flow. Register it with one line in `infrastructure/ai/registry.py` and add
its name to `Settings.ai_provider` in `config.py`. Providers only return text: saving
always goes through `CreateAnswer`, after a person clicks Save.

### Add a language

Add a new top-level object (for example `"pt"`) to `web/static/i18n/translations.json`,
with the same keys as `"es"`. `tests/unit/test_translations.py` fails if any key is
missing. Then add the code to `LOCALES` in `web/static/js/i18n.js` and to `Settings.locale`.

### Switch to PostgreSQL

Set `RR_DATABASE_URL=postgresql+psycopg://user:pass@host/db` and install `psycopg`.
The repositories use the SQLAlchemy ORM and Core only. The one dialect-specific
statement, the unanswered-question upsert, already supports both SQLite and PostgreSQL
(`infrastructure/db/repositories/activity.py`). Migrations are run at startup by
`infrastructure/db/migrate.py`.

### Add a database change

Edit `infrastructure/db/models.py`, then generate a migration:

```bash
python -c "from alembic import command; from readyreply.infrastructure.db.migrate import alembic_config; command.revision(alembic_config('sqlite:///./data/readyreply.db'), message='describe change', autogenerate=True)"
```

`tests/integration/test_migrations.py` fails if the models and migrations disagree.

## Path to the SaaS version

- **Tenancy:** every table has `business_id`, and every repository method takes it. v1 always uses business `1` (`application/auth.py::BUSINESS_ID`). A SaaS version resolves the business from the subdomain or the session instead.
- **Search index:** cached in memory per business and rebuilt when `businesses.content_revision` changes. With several app instances, each keeps its own cache, and the revision check keeps them correct.
- **Double-click guards and login throttling:** they use in-memory stores (`infrastructure/security/memory.py`) behind the `RepeatGuard` and `LoginFailureLog` ports. With several instances, replace them with a shared store such as Redis.
- **Sessions:** they are stored in the database, so they already work across instances.

## Tests

| Folder | What | Run |
|---|---|---|
| `tests/unit` | domain rules (100% coverage), translations, frontend safety | `pytest tests/unit` |
| `tests/integration` | migrations | `pytest tests/integration` |
| `tests/api` | every endpoint, roles, CSRF, privacy, AI with a fake model server | `pytest tests/api` |
| `tests/perf` | P8: 1,000 answers, p95 < 200 ms | `pytest tests/perf -s` |
| `tests/e2e` | Playwright at 1280 px and 360 px, README screenshots | `pytest tests/e2e` |
| `tests/qa` | independent QA attack tests | `pytest tests/qa` |

Tests are tagged with the promise they verify: `pytest -m promise_p2`.
