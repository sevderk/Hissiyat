# Phase 1D validation

Date: 2026-10-23. Scope: secure local foundation baseline, minimal input
contracts, synthetic fixtures and focused documentation. No subsequent phase is
implemented.

## Baseline and security inspection

Initial inspection found zero commits, no tracked/staged files and no remote.
Effective author and committer identity were present in the existing Git
configuration; neither identity nor global configuration was changed. No active
custom Git hooks were found.

All 53 candidate files were content-reviewed before staging. The actual local
password was compared in memory against candidate contents without displaying
it. Key/token, private-key, authenticated-URL and email scans found no candidate
matches. Synthetic unit password canaries are test inputs, not local credentials.
The npm lock's 497 package entries were inspected as metadata; resolved URLs use
HTTPS `registry.npmjs.org` without credentials, query strings or local paths.
This is a bounded content review, not a guarantee from a dedicated secret scanner.

Existing ignore rules needed no change. Eleven sensitive/generated-path probes
passed: the actual proposal PDF, three private environment files, the virtual
environment, Node dependencies, Next build output, ignored local review artifacts,
and sample data/dataset/model paths. Environment template password fields are
blank. The proposal's contents were not opened, copied, moved or modified in this
phase. Its SHA-256 still equals the previously recorded value:

`9A3B5DFA0296FC747839694CD365DEF29605955A52352EF4C606A6C2E34F02B0`.

Before committing, staged paths exactly matched the reviewed file manifest, and
staged blob contents matched reviewed bytes after Git newline normalization.
The staged diff and lock metadata were checked; `git diff --cached --check`
passed. One root commit was created:

`781442695d9dff621ef9e5ef503ee243047a9ba6`

Message: `chore: establish verified application foundation`.
The commit was completed before contract implementation. No push, remote setup,
amend, history rewrite or destructive Git operation was performed. Existing Git
autocrlf settings produced LF-to-CRLF notices; global settings were not changed.

## Files in the baseline

Exactly 53 files: root 5, backend 20, frontend 21, documentation 5,
infrastructure 1 and setup scripts 1. The manifest is reproducible with
`git ls-tree -r --name-only 7814426`:

```text
.editorconfig
.env.example
.gitignore
README.md
backend/.env.example
backend/.env.test.example
backend/app/__init__.py
backend/app/api/__init__.py
backend/app/api/v1/__init__.py
backend/app/api/v1/health.py
backend/app/api/v1/router.py
backend/app/core/__init__.py
backend/app/core/config.py
backend/app/core/database.py
backend/app/main.py
backend/pyproject.toml
backend/requirements-dev.txt
backend/requirements.lock.txt
backend/requirements.txt
backend/tests/integration/test_postgres.py
backend/tests/test_health.py
backend/tests/unit/test_database.py
backend/tests/unit/test_database_config.py
backend/tests/unit/test_readiness.py
compose.yaml
docs/architecture.md
docs/database-development.md
docs/environment.md
docs/validation-phase-1b.md
docs/validation.md
frontend/eslint.config.mjs
frontend/messages/en.json
frontend/messages/tr.json
frontend/next-env.d.ts
frontend/next.config.ts
frontend/package-lock.json
frontend/package.json
frontend/postcss.config.mjs
frontend/scripts/verify-routes.mjs
frontend/src/app/[locale]/[...rest]/page.tsx
frontend/src/app/[locale]/layout.tsx
frontend/src/app/[locale]/not-found.tsx
frontend/src/app/[locale]/page.tsx
frontend/src/app/globals.css
frontend/src/components/language-switcher.tsx
frontend/src/i18n/navigation.ts
frontend/src/i18n/request.ts
frontend/src/i18n/routing.ts
frontend/src/i18n/types.ts
frontend/src/proxy.ts
frontend/tsconfig.json
infrastructure/postgres/01-create-test-database.sql
scripts/configure_local_database.py
```

## Executed checks and exact results

| Check | Result |
| --- | --- |
| Pre-baseline dependency integrity | `pip check`: no broken requirements |
| Pre-baseline backend tests | **25 passed, 3 deselected, 1 warning**, 1.19 s |
| New contract tests | **62 passed**, 0.30 s |
| Full backend unit/regression tests | **87 passed, 3 deselected, 1 warning**, 0.96 s |
| Explicit PostgreSQL integration attempt | **2 failed, 1 passed, 87 deselected, 1 warning**, 9.16 s |
| Final backend dependencies/imports | No broken requirements; application, all five contracts, Pydantic 2.14.1, SQLAlchemy and psycopg imported |
| Compose configuration | `config --quiet` passed; no configuration change |
| Docker service availability | Linux-engine named pipe unavailable; `docker ps -a` and project `ps` failed |
| Actual backend HTTP | Liveness **200**; readiness **503** with expected generic body while PostgreSQL was offline |
| Frontend TypeScript | Passed |
| Frontend lint | Passed |
| Frontend production build | Passed; `/tr` and `/en` prerendered |
| Production route checks | Four PASS groups: default `/tr`, Turkish page/404, English page/404, message-key parity/nonempty translations |
| Source/infrastructure/dependency integrity | Every baseline file except the intentionally edited README and architecture document has the same byte hash |
| Proposal integrity | SHA-256 unchanged |
| Final Git state | One commit only; Phase 1D files unstaged/uncommitted, no remote, no tracked local secrets/generated data |

The two integration failures are real-connection/readiness checks blocked by
unavailable PostgreSQL. The reserved non-listening-port/liveness test passed.
They are not reported as successful integration validation or silently skipped.
The Docker engine was not started or repaired. Successful readiness and current
database table counts could not be reverified in this session. Earlier Phase 1B
results remain historical evidence, not current measurements.

New tests cover English/Turkish Unicode, exact text preservation and masked
representations, publication/retrieval distinction and offset ordering, missing
publication time, invalid/ambiguous timestamps, `und`, additional language tags,
source/policy/collection references, unknown/unverified/denied rights, documented
approval claims, local fallback IDs, inline/reference content alternatives,
collection time, trend measurement context, observed zero, missing/suppressed
values, finite numeric values, declared scale bounds, alternate/unbounded scales,
invalid intervals, separation of text/trend fields and safe diagnostic summaries.
No collected data or external source was used.

## Commands executed

Read-only inspection used `Get-Location`, scoped `rg --files`, `Get-Content`,
Git status/history/identity/config/remote/index checks and Python standard-library
hash/content/lockfile inspection. The explicitly reviewed 53-path manifest was
passed to `git add -- <paths>`, followed by staged name/diff/check inspection and
`git commit -m "chore: establish verified application foundation"`.

Backend commands from `backend/` used the existing virtual environment:

```powershell
.\.venv\Scripts\python.exe -B -m pip check
.\.venv\Scripts\python.exe -B -m pytest tests/unit/test_data_contracts.py
.\.venv\Scripts\python.exe -B -m pytest
.\.venv\Scripts\python.exe -B -m pytest -m integration --tb=no
```

An import command loaded the application, five contracts and existing database
libraries. `--tb=no` avoided dumping driver traceback details during the expected
offline integration attempt.

```powershell
docker compose --project-name hissiyat-dev --file compose.yaml config --quiet
docker ps -a --format '{{.ID}}|{{.Names}}|{{.Image}}|{{.Status}}|{{.Ports}}'
docker compose --project-name hissiyat-dev --file compose.yaml ps
```

Frontend commands from `frontend/` ran with `NEXT_TELEMETRY_DISABLED=1`:

```powershell
npm run typecheck
npm run lint
npm run build
```

A Python standard-library harness started temporary loopback-only child servers
on OS-selected free ports: `python -B -m uvicorn app.main:app --host 127.0.0.1
--port <port>` and `node node_modules/next/dist/bin/next start --hostname 127.0.0.1
--port <port>`. It asserted actual backend status/bodies, then ran
`node scripts/verify-routes.mjs` with `FRONTEND_BASE_URL` set. Only those child
servers were terminated in `finally` blocks. Their logs/review hashes remain in
ignored local `artifacts/`; no secrets were printed.

## Scope and remaining limits

Phase 1D adds `backend/app/contracts/{__init__,inputs}.py`, the synthetic JSON
fixture, `tests/unit/test_data_contracts.py`, `docs/data-contracts.md` and this
validation record. Only README and architecture documentation were edited among
baseline files. The new implementation remains uncommitted for owner review.

No schema, DDL, migration, database configuration, dependency, frontend source,
environment credential or proposal change was made. No container/volume/service
mutation command was run. Unrelated container state cannot be independently
inspected while the daemon is unavailable; the task did not modify it.

The existing Starlette/httpx deprecation warning and ancestor-lockfile Next.js
notice remain. Earlier dependency audit findings were not refreshed or fixed in
this phase. Validation is local Windows validation, not cross-platform or
production certification. Permissions, duplicate detection, persistence,
adapters, NLP and evaluation remain deferred as described in `data-contracts.md`.

Next: make the existing Docker engine available and rerun the three read-only
integration tests. Any later database model or controlled ingestion task needs
explicit scope approval and verified source rights before actual data use.
