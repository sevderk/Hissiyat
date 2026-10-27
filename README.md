# Hissiyat

An AI-supported research platform for exploring human experience and social
patterns in online data. This repository contains the application foundation and
Phase 1B local PostgreSQL connectivity and Phase 1D source-independent input
validation. It does not collect data or produce analytical results.

## Requirements

- Windows with PowerShell.
- Node.js 24.x; verified locally with Node.js 24.4.1 and npm 11.4.2.
- Python 3.12; verified locally with Python 3.12.9 and pip 24.3.1.
- Git; verified locally with Git 2.47.0.windows.1.

Database readiness and integration tests require an existing working Docker
Desktop Linux engine and Docker Compose. The landing page, liveness endpoint and
unit tests work without PostgreSQL. Dependency downloads require network access.

## Local database setup

From the repository root, create consistent ignored environment files once:

```powershell
python -B scripts/configure_local_database.py
docker compose --project-name hissiyat-dev --file compose.yaml config --quiet
docker compose --project-name hissiyat-dev --file compose.yaml up -d --wait postgres
docker compose --project-name hissiyat-dev --file compose.yaml ps
```

The script refuses to overwrite existing configuration and does not print the
generated local password. The database binds only to `127.0.0.1:55432`. Starting
Compose creates project-specific Docker resources; an agent must obtain explicit
user approval before doing so. Stop without deleting data:

```powershell
docker compose --project-name hissiyat-dev --file compose.yaml stop postgres
```

See [local PostgreSQL development](docs/database-development.md) for prerequisites,
port changes, database health checks and troubleshooting. Do not reuse an
unrelated PostgreSQL instance or delete its data.

## Frontend setup and launch

Open a PowerShell terminal:

```powershell
Set-Location 'C:\Users\Asus\Desktop\Hissiyat\frontend'
npm ci
npm run dev
```

Open <http://127.0.0.1:3000>. The root redirects to `/tr`, including when the
browser language is English. The language switcher navigates between `/tr` and
`/en`. The URL controls the locale; browser detection and locale cookies are
disabled in this phase. No frontend environment file is needed.

## Backend setup and launch

Open a second PowerShell terminal:

```powershell
Set-Location 'C:\Users\Asus\Desktop\Hissiyat\backend'
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.lock.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

If PowerShell prevents virtual environment activation, use the interpreter
directly without changing the execution policy:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Run backend commands from `backend/` so the application and optional `.env` file
resolve consistently. Local addresses:

- Health: <http://127.0.0.1:8000/api/v1/health> returns `{"status":"ok"}`.
- OpenAPI documentation: <http://127.0.0.1:8000/docs>.

The health endpoint reports application liveness only. Database readiness is
available separately at <http://127.0.0.1:8000/api/v1/health/ready>: HTTP 200 when
an authenticated `SELECT 1` succeeds, otherwise HTTP 503 with a generic response.
The frontend is independent of the backend; no API calls or CORS configuration
are needed.

Configuration defaults allow liveness without a local environment file. The
database setup script above creates backend settings. For manual setup only:

```powershell
Copy-Item .env.example .env
```

Fill the blank password with a generated local-only value before using the
template. Configuration includes `HISSIYAT_SERVICE_NAME`, `HISSIYAT_ENVIRONMENT`
and `HISSIYAT_DATABASE_*`; see the database guide. The environment label is not a
production hardening switch. Do not place secrets in committed files.

## Validation

In `frontend/`:

```powershell
npm ls --depth=0
npm run typecheck
npm run lint
npm run build
```

To verify the production routes, stop the frontend development server with
Ctrl+C, start the production build, and run the route check in another terminal:

```powershell
npm run start
```

```powershell
Set-Location 'C:\Users\Asus\Desktop\Hissiyat\frontend'
npm run test:routes
```

The check verifies the Turkish default, both translated pages, document language,
language links, localized missing pages, and matching nonempty message keys. It
requires a running frontend server. For a nondefault port, set
`$env:FRONTEND_BASE_URL = 'http://127.0.0.1:3001'` in that terminal first.

In `backend/`, without requiring activation:

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -c "from app.main import app; print(app.title)"
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m pytest -m integration
Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/health'
Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/health/ready'
```

HTTP commands require a running backend. Endpoint tests use an in-process client.
Default pytest deselects integration tests. The explicit integration command
requires the separate local `hissiyat_test` database and `backend/.env.test`;
missing configuration fails rather than silently skipping tests. Stop local
application servers with Ctrl+C.

## Dependency reproducibility

Frontend direct dependencies are pinned in `frontend/package.json`; use `npm ci`
with the repository's `package-lock.json` for the full resolved tree. Backend direct
dependencies are declared in `requirements.txt` and `requirements-dev.txt`;
`requirements.lock.txt` pins the complete tested development environment,
including transitive dependencies. Install the lock file for repeatable setup.
The Python lock was generated on Windows with Python 3.12; other platforms and
Python versions need separate verification. Package hashes are not included.

See `docs/environment.md` for versions and `docs/validation.md` for executed
checks, and `docs/validation-phase-1b.md` for database-phase results. A future intentional dependency update should regenerate the relevant
lock and rerun validation.

## Repository and current limits

```text
frontend/   Next.js App Router, TypeScript, Tailwind CSS, next-intl
backend/    FastAPI, database connection pool, liveness/readiness, pytest
infrastructure/  PostgreSQL test-database initialization
scripts/    Local-only environment setup
compose.yaml  Isolated local PostgreSQL service
docs/       Architecture, environment and validation notes
```

There are no application tables, migrations, authentication, data collection,
background processing, NLP models, dashboards, or deployment. The approved first
pilot concerns education, career expectations and future uncertainty, using
English text; Turkish text is a parallel feasibility investigation. The platform
and input models remain domain-independent. Stack Exchange text, official Google
Trends CSV exports and Turkish Bluesky text are candidates only; none has final
collection or analysis approval. UI localization does not imply NLP support.

See [input contracts](docs/data-contracts.md) for implemented validation,
provenance metadata, safe error reporting and limitations. Synthetic fixtures are
test inputs, not research observations. The source proposal remains local,
unchanged and excluded from Git. A reviewed Phase 1B foundation baseline was
committed locally before implementing Phase 1D; Phase 1D changes remain
uncommitted for review. See [Phase 1D validation](docs/validation-phase-1d.md).
Work beyond Phase 1D requires explicit approval.
