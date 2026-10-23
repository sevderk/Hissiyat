# Local PostgreSQL development

## Prerequisites and isolation

Use the existing Docker Desktop installation with its Linux engine running.
On Windows, Docker Desktop needs a working supported virtualization/WSL 2 or
Hyper-V backend. If `docker info` fails outside the Codex sandbox, open Docker
Desktop and resolve its reported prerequisite issue manually. This project does
not install or repair Docker, WSL or PostgreSQL.

From the repository root, inspect the environment before starting anything:

```powershell
docker --version
docker compose version
docker info --format '{{json .ServerVersion}}'
docker ps -a --format '{{.Names}}  {{.Image}}  {{.Status}}  {{.Ports}}'
Get-NetTCPConnection -State Listen -LocalPort 55432 -ErrorAction SilentlyContinue
```

`compose.yaml` defines only project `hissiyat-dev`. The official image is pinned
to `postgres:18.6-bookworm`; neither `latest` nor a release candidate is used.
Its named volume is `hissiyat-dev_postgres_data`. PostgreSQL 18 stores its
versioned data under `/var/lib/postgresql`, which is the mounted volume path.
The service publishes only `127.0.0.1:<configured-port>:5432`, default 55432.
It does not reuse or modify existing Supabase or other PostgreSQL instances.

## Environment files

For a new local setup, run once from the repository root:

```powershell
python -B scripts/configure_local_database.py
```

The standard-library-only script generates one random local password and creates
three consistent ignored files: root `.env`, `backend/.env`, and
`backend/.env.test`. It refuses to overwrite any existing environment file and
does not display the password. It does not create Docker resources. To choose a
different free port before creating files:

```powershell
python -B scripts/configure_local_database.py --port 55433
```

`--database` and `--username` optionally customize the development database and
role. The separate integration database name is reserved as `hissiyat_test`.
Templates `.env.example`, `backend/.env.example` and `backend/.env.test.example`
document the settings. Their password fields are intentionally blank and must
not be copied into use without a generated or explicitly supplied local password.

Root variables configure Compose. Backend variables use the
`HISSIYAT_DATABASE_` prefix. If changing the host port after setup, update all
three files consistently. PostgreSQL connection passwords use `SecretStr`; the
SQLAlchemy URL is constructed from separate fields to handle reserved characters.
Do not print environment files or expanded `docker compose config` output.
Use `config --quiet` for validation.

## Start and inspect

Starting creates a project network, container and persistent volume, and may
download the official image. When an agent performs this operation it must obtain
the project owner's explicit approval first.

```powershell
Set-Location 'C:\Users\Asus\Desktop\Hissiyat'
docker compose --project-name hissiyat-dev --file compose.yaml config --quiet
docker compose --project-name hissiyat-dev --file compose.yaml up -d --wait postgres
docker compose --project-name hissiyat-dev --file compose.yaml ps
docker compose --project-name hissiyat-dev --file compose.yaml exec -T postgres sh -c 'pg_isready -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

The health check tests server acceptance. Backend readiness additionally checks
an authenticated connection with `SELECT 1`. Neither test proves the presence
of application tables, and none are created in this phase.

On the first boot of an empty volume, the official entrypoint creates the chosen
development database and runs `01-create-test-database.sql` to create the separate
empty `hissiyat_test` database. Both use the isolated local development role.
Initialization scripts run only on an empty data directory. The role is an
image-initialization superuser for this local-only setup; least-privilege runtime
and migration roles are deferred until a later approved schema/security task.

## Backend and health endpoints

From `backend/`:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

If 8000 belongs to an already running process, leave it untouched and use a free
port such as 8001, changing the checks accordingly.

```powershell
Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/health'
Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/health/ready'
```

- Liveness: always HTTP 200 `{"status":"ok"}` for a running application.
- Readiness with a reachable database: HTTP 200
  `{"status":"ready","database":"ok"}`.
- Missing database credentials or unreachable database: HTTP 503
  `{"status":"unavailable","database":"unavailable"}`.

Absent connection credentials allow the application to start with readiness
unavailable. Blank explicitly supplied values, invalid ports and invalid timeout
bounds fail configuration validation without echoing inputs. Invalid configuration
is distinct from an offline database. The frontend does not depend on either
health endpoint and continues to render independently.

The pool is created lazily during FastAPI lifespan and disposed at shutdown.
SQLAlchemy Core uses psycopg, two pooled connections, zero overflow, pre-ping and
a two-second pool wait. Defaults are a three-second connection timeout and a
three-second statement timeout. The latter values are configurable within bounds.
No credentials, driver error details or connection strings are returned by
readiness or logged by the connection check.

## Tests

Unit tests never need PostgreSQL. Default pytest explicitly deselects integration
tests; its summary is not proof of real connectivity.

```powershell
Set-Location 'C:\Users\Asus\Desktop\Hissiyat\backend'
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m pytest -m integration
```

Integration tests require `backend/.env.test`, loopback host, test environment and
the exact `hissiyat_test` database name. Missing or unsafe settings fail the tests
rather than silently skipping them. Shell environment variables override dotenv;
remove conflicting `HISSIYAT_DATABASE_*` values before running tests. The suite
uses only read-only queries. Failure testing reserves a non-listening local port;
it does not stop an existing database. No user or research data is used.

## Stop without deleting data

From the repository root:

```powershell
docker compose --project-name hissiyat-dev --file compose.yaml stop postgres
```

Restart with the same `up -d --wait postgres` command. Do not use volume deletion
or broad prune commands. No automatic restart policy is enabled.

## Troubleshooting and limits

- **Port already allocated:** identify the listener; do not stop an unrelated
  process. Choose a free loopback port and update the three environment files.
- **Connection refused / HTTP 503:** check Docker Desktop, project `ps`, port and
  backend settings. Liveness remaining HTTP 200 is expected.
- **Authentication failure after changing `.env`:** changing variables does not
  change a role password already stored in a persistent volume. Restore the
  matching local configuration or arrange a deliberate credential update. Do not
  delete the volume as a shortcut.
- **Missing test database on an existing volume:** initialization scripts do not
  rerun. Inspect the project-specific database first and arrange an explicit
  non-destructive creation if needed; do not reset another instance.
- **Docker permission failure only in Codex:** request tool approval for Docker
  named-pipe access; do not weaken host security settings.

This is local development infrastructure, not a production deployment. The files
contain no application schema, migrations, ingestion, background jobs or NLP.
Docker administrators can inspect container environment variables; ignored local
files are not a production secrets manager. No unrelated dependency upgrades or
npm audit fixes are part of this phase.

References: [PostgreSQL version policy](https://www.postgresql.org/support/versioning/),
[official PostgreSQL image](https://hub.docker.com/_/postgres),
[SQLAlchemy engines](https://docs.sqlalchemy.org/en/21/core/engines.html),
[psycopg installation](https://www.psycopg.org/psycopg3/docs/basic/install.html).
