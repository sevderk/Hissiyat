# Phase 1B validation

Date: 2026-10-17. Scope: local PostgreSQL infrastructure and backend connectivity.

## Environment and resource authorization

- Docker CLI and Linux daemon: 29.8.2; Compose: v5.6.0.
- Docker named-pipe inspection was initially blocked by the Codex sandbox;
  approved read-only diagnostics confirmed a working daemon.
- Existing Supabase/PostgreSQL containers belong to another project. They were
  not altered; its database remained healthy on port 54322 after validation.
- Existing application listeners on 3000 and 8000 were left running. Temporary
  verification servers used 3001 and 8001.
- Host port 55432 was free; no existing Hissiyat project volume or network existed.
- The owner explicitly approved downloading the official image and creating the
  Hissiyat container, network, named volume and empty dev/test databases before
  `docker compose up` was executed.

## Implemented and exercised

| Check | Exact result |
| --- | --- |
| Compose configuration | `config --quiet` passed |
| Generated environment files | Created without displaying a password; all three files ignored by Git |
| Repeat environment setup | Refused existing files with exit code 2; no overwrite |
| Dependency installation | Four new packages; existing versions constrained, no unrelated upgrades |
| Backend dependency integrity | `pip check`: no broken requirements |
| Imports | FastAPI application, SQLAlchemy 2.1.5 and psycopg 3.3.6 imported |
| Default unit/regression suite | **25 passed, 3 deselected, 1 warning**, 0.82 s |
| Explicit PostgreSQL integration suite | **3 passed, 25 deselected, 1 warning**, 3.17 s |
| Actual HTTP before PostgreSQL startup | Liveness 200; readiness 503 with generic body |
| Actual HTTP after PostgreSQL startup, same backend | Liveness 200; readiness 200 with database `ok` |
| PostgreSQL image and server | `postgres:18.6-bookworm`; actual server PostgreSQL 18.6 |
| Container health | `hissiyat-dev-postgres-1` healthy |
| Published database port | Only `127.0.0.1:55432 -> 5432/tcp` |
| Persistence configuration | Named volume `hissiyat-dev_postgres_data` mounted at `/var/lib/postgresql` |
| Development database | `hissiyat_dev`, zero public application tables |
| Integration database | `hissiyat_test`, zero public application tables |
| Frontend TypeScript | Passed |
| Frontend lint | Passed |
| Frontend production build | Passed; `/tr` and `/en` prerendered |
| Frontend HTTP locale regression | Root default, both locale pages, message keys and localized 404s passed on 3001 |
| Proposal integrity | SHA-256 unchanged from the Phase 1A recorded value |
| Frontend source integrity | `src/`, messages, package manifest and lock hashes unchanged |
| Git | Zero commits; secrets excluded |

The unit suite covers environment loading, missing and invalid database settings,
secret-safe representations/errors, connection release and failure handling, pool
disposal, lazy startup and liveness/readiness separation. Successful readiness
unit tests use a dependency override; they are distinct from the three real
PostgreSQL integration tests. The latter check the dedicated database, real
readiness and an unreachable local port while liveness remains available. No
tests were silently skipped; deselection is explicit in the separate commands.

The real HTTP transition from offline to ready used the same running application,
so a failed initial database connection did not require an application restart.
No application tables, migration, test content or research data were created.

## Commands executed

Read-only environment review used repository-file reads, Git status/diff/history,
hashes, tool versions, `docker info`, `docker ps -a`, project-filtered volume and
network listings, and local listener inspection. Metadata was read from official
PostgreSQL/Docker/SQLAlchemy/psycopg documentation and PyPI.

Backend commands, from `backend/`:

```powershell
.\.venv\Scripts\python.exe -m pip install --constraint requirements.lock.txt -r requirements-dev.txt --disable-pip-version-check --retries 0 --timeout 30
.\.venv\Scripts\python.exe -m pip freeze
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -c "import sqlalchemy, psycopg; from app.main import app; print(app.title)"
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m pytest -m integration
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

The freeze output was written to the updated requirements lock. Its 29 entries
include the original 25 plus SQLAlchemy, psycopg, psycopg-binary and tzdata.

Infrastructure commands, from the root:

```powershell
python -B scripts/configure_local_database.py
docker compose --project-name hissiyat-dev --file compose.yaml config --quiet
docker compose --project-name hissiyat-dev --file compose.yaml up -d --wait postgres
docker compose --project-name hissiyat-dev --file compose.yaml ps
```

Additional read-only commands used project `exec ... psql` to inspect version,
database names and public-table counts, and narrowly formatted `docker inspect`
to inspect port/volume bindings without environment values. Image inspection
recorded the digest in `environment.md`. HTTP checks used Python urllib with
status/body assertions for success and explicit inspection of the 503 response.

Frontend commands:

```powershell
$env:NEXT_TELEMETRY_DISABLED='1'
npm run typecheck
npm run lint
npm run build
npm run start -- --port 3001
$env:FRONTEND_BASE_URL='http://127.0.0.1:3001'
npm run test:routes
```

Only the newly started verification application servers were stopped afterward.
The approved Hissiyat PostgreSQL service was left running for local development;
its non-destructive stop command is in `database-development.md`.

## Review limits and existing notices

There is no committed Git baseline: Phase 1A files were already untracked and no
commit was authorized. `git diff --stat` / `git diff --check` therefore cannot
represent changes to those files. Review used the initial file contents, the
known patch scope, source inventory and unchanged frontend/proposal hashes.
The `.gitignore` rules already covered every generated environment file and did
not need modification.

Starlette's existing httpx TestClient deprecation warning remains unchanged. The
frontend build/start reports an unrelated ancestor lockfile being ignored outside
the repository. All requested frontend checks passed; no unrelated frontend
configuration was changed to suppress this notice. Phase 1A npm audit/ESLint
maintenance findings were not automatically fixed or re-audited in this phase.

The named volume and mount were verified; a destructive-reset or volume recovery
experiment was not performed. Cross-platform setup, public deployment, TLS,
least-privilege production roles and production secret management were not
validated. Local Compose uses an isolated development initialization role.

Application schema design, Alembic, ingestion, research data, NLP, authentication,
background workers and dashboards remain postponed. Phase 1B ends here.
