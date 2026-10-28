# Phase 2A validation

Dates: 2026-10-27 to 2026-10-28. Scope: five-table Core schema, explicit Alembic migration,
synthetic integration tests and necessary documentation. No actual ingestion,
research data, NLP or subsequent phase is implemented.

## Initial inspection

The working tree was clean on `master`; HEAD was
`5744d05885f5b261a13323ae226dc6ba6ab8c3dc`, with two local commits and no remote.
There was no migration system. Both configured local databases were inspected
through the existing application connection layer before file changes:
`hissiyat_dev` and `hissiyat_test` had zero public relations/routines and no
migration history or other user relations. PostgreSQL 18.6 was healthy on the
existing loopback port 55432. Existing Supabase containers were read-only
inspection context, not migration targets.

## Implementation and dependency review

`app/core/schema.py` defines five source-independent tables. The explicit initial
revision `0001_text_foundation` freezes the reviewed table/constraint/index DDL;
it has no runtime dependency on current schema metadata. The model-to-DDL render
was reviewed and the migrated schema was checked against metadata. No live
database autogeneration was accepted without review.

Alembic **1.20.1**, Mako **1.4.3** and MarkupSafe **3.0.4** were added only to the
project virtual environment. Alembic is a pinned development/migration dependency;
the full lock now contains 32 packages. Official PyPI metadata and the constrained
pip dry run were inspected first. Installation used the previous lock as a
constraint; all 29 previous installed/locked versions were verified unchanged.
No system tool or frontend dependency was installed or upgraded.

## Executed checks (original Phase 2A implementation)

| Check | Exact result |
| --- | --- |
| Migration safety unit tests | **16 passed**, 0.43 s |
| Complete backend unit/regression suite | **103 passed, 48 deselected, 1 warning**, 1.67 s |
| Complete PostgreSQL integration suite | **48 passed, 103 deselected, 1 warning**, 4.17 s |
| Dependency integrity | `pip check`: no broken requirements |
| Imports | Application/schema/Alembic imports passed; five Core tables registered |
| Migration revision | `heads`: `0001_text_foundation (head)` |
| Initial online state inspection | `current` succeeded for both empty targets, with no revision applied |
| Offline SQL review | Six CREATE TABLE statements (five research tables plus Alembic bookkeeping); no DROP/TRUNCATE/DELETE |
| Transactional migration | Initial upgrade, second idempotent upgrade, schema/constraint/index reflection and `alembic check` passed on the test connection |
| Unauthorized development command | Upgrade without `allow_development=true` refused before migration |
| Test cleanup | Zero public relations in `hissiyat_test` after the complete suite; all test DDL and rows rolled back |
| Development isolation before approval | Zero public relations after tests and CLI inspection; no persistent migration applied |
| Approved persistent development upgrade | Applied `0001_text_foundation` only to `127.0.0.1:55432/hissiyat_dev` after explicit owner approval |
| Development schema after upgrade | Five research tables plus `alembic_version`; revision at head; `alembic check`: no new upgrade operations detected |
| Research rows after upgrade | Zero rows in all five development research tables; test database still empty |
| Post-upgrade actual backend HTTP | Liveness and readiness **200**, exact existing bodies; temporary backend stopped |
| Docker resource integrity | All 13 existing container identities/images/port bindings unchanged; Hissiyat remains healthy |
| Actual backend HTTP | Liveness and readiness **200**, with exact existing response bodies |
| Frontend TypeScript/lint/build | All passed; Turkish/English pages prerendered |
| Production locale routes | All four existing PASS groups: default, both locale pages/404s, message-key parity |

The integration suite consists of the original three connectivity tests and 45
new schema tests. It covers migration creation/idempotence, expected objects,
synthetic source/policy/event/record/version insertions, non-null/blank/content
rules, FK and cross-source violations, record/version uniqueness, shared record
identity across retrieval versions, missing publication timestamps, distinct
publication/retrieval instants, timezone-aware round trips, policy defaults and
unverified/denied status, all event statuses, local fallbacks, normalized-content
provenance and refusal of unexpected relations, user schemas and revision state.
The 16 new unit tests cover target/operation/approval guards; the original 87
unit/contract tests remain intact.

An earlier intermediate integration run passed 45 tests but emitted a newly
introduced SQLAlchemy `Result.tuples()` deprecation warning. The call was replaced
with normal row iteration, guard coverage was extended and the final 48-test run
passed with only the pre-existing Starlette/httpx warning. No failed migration or
test result was hidden or converted into a skip.

## Commands executed

Read-only inspection used Git status/HEAD/history/remotes, scoped instruction and
migration-file searches, source/test/document reads, file hashes, Docker status
and PostgreSQL catalog queries through guarded `Settings`/`Database` connections.
No environment file or expanded Compose secret was printed.

Dependency commands used `python -B -m pip install --dry-run --constraint
requirements.lock.txt alembic==1.20.1`, followed by the constrained installation
of Alembic/Mako/MarkupSafe at the versions above. The lock was extended only after
checking the previous installed versions.

From `backend/`, using `.\.venv\Scripts\python.exe -B`:

```text
-m pip check
-m alembic heads
-m alembic -x target=test current
-m alembic -x target=development current
-m alembic -x target=test upgrade head --sql
-m alembic -x target=development -x allow_development=true upgrade head
-m alembic -x target=development check
-m pytest tests/unit/test_migration_safety.py
-m pytest
-m pytest -m integration
```

The no-approval development upgrade was deliberately invoked and required to
fail before connecting/migrating. Integration tests call Alembic upgrade/check
with their own explicit test transaction. Negative tests create only synthetic
objects inside savepoints and roll them back; they do not issue DROP/TRUNCATE or
reset commands. Offline SQL is stored only in ignored local `artifacts/`.

Frontend `npm run typecheck`, `npm run lint`, `npm run build` ran with telemetry
disabled. A standard-library harness started temporary loopback-only Uvicorn and
production Next.js child servers on free OS-selected ports, checked actual
backend responses and ran `node scripts/verify-routes.mjs`. Only those temporary
child processes were stopped.

## Persistent migration approval state

The owner explicitly approved applying `0001_text_foundation` to
`127.0.0.1:55432/hissiyat_dev` after the implementation, synthetic migration tests,
regressions and security review were complete. The migration was then applied
with the deliberate development opt-in. Preflight rechecked the target and empty
state. Post-upgrade `current` reported the initial revision at head, `check`
reported no new upgrade operations, and all expected tables/indexes were
recognized by the state guard. All five research tables contain zero rows;
only Alembic's revision bookkeeping row exists.

The test database remains empty after transactional verification. No schema was
persisted there, no real source content was inserted, and no unrelated database
or Docker resource was modified. No destructive downgrade or database/volume
deletion is implemented or executed.

## Integrity and limits

Phase 1D input contracts, original tests, API/config/connection files, Compose and
frontend source remain unchanged. Proposal/environment/source hash and final Git
diff checks passed. No credentials, real research data,
model weights, generated artifacts, containers or volumes are added to Git.
There is no new commit, remote or push; Phase 2A remains uncommitted for review.

The existing Starlette/httpx warning and ancestor-lockfile Next.js notice remain;
no unrelated dependency audit fix or global npm update was attempted. Full
production security, privileges, source rights, retention enforcement, precise
source timestamps, ingestion adapters, corpus/trend persistence, NLP and human
evaluation remain deferred. See `research-schema.md` for validation/database
differences and privacy limitations.

## Changed files

New: `backend/alembic.ini`, `backend/app/core/schema.py`,
`backend/app/core/migrations.py`, `backend/migrations/env.py`,
`backend/migrations/script.py.mako`,
`backend/migrations/versions/0001_text_foundation.py`,
`backend/tests/unit/test_migration_safety.py`,
`backend/tests/integration/test_research_schema.py`, `docs/research-schema.md`,
`docs/validation-phase-2a.md`.

Modified: `README.md`, `backend/requirements-dev.txt`,
`backend/requirements.lock.txt`, `docs/architecture.md`, `docs/data-contracts.md`,
`docs/database-development.md`. No original input contract, application route,
connection/configuration, frontend or Docker file was edited.

## Prompt 10 security correction and verification

Date: 2026-10-28. Prompt 09 stopped without committing after a simulated supplied
connection to an unexpected endpoint reached the migration path. The old code
validated `Settings` and the SQL database name but did not verify the supplied
connection's effective destination. Its active-transaction check did not provide
that assurance. Prompt 09's Docker unavailability was a separate environmental
blocker, not proof that the guard was safe.

The focused correction adds `validate_connection_target` and invokes it before
schema inspection/Alembic configuration on both online execution paths. It uses
the active psycopg connection's libpq metadata through SQLAlchemy's driver
connection, never a formatted connection URL or password. It validates authorized
settings separately, requires a valid open connection, active transaction,
supported synchronous driver and established connection status, then compares
strictly typed host/address/port/database values. Unavailable metadata and
metadata-access errors fail closed with constant sanitized errors. The existing
SQL database-name and schema/history checks follow unchanged.

Twenty-seven new deterministic unit cases exercise mismatched host, resolved IP,
port and database; absent/malformed metadata; inactive/unknown transactions;
closed/invalidated/broken/unestablished or unsupported connections; misleading
engine URLs; metadata-error redaction; subsequent SQL database identity checks;
and refusal before migration configuration/execution. These simulations do not
prove a real server's identity. One new live integration test validates the
Hissiyat test driver destination and confirms client port 55432 versus server
internal port 5432. No arbitrary external address was contacted.

| Current security-fix check | Exact result |
| --- | --- |
| Focused migration safety tests | **43 passed**, 0.92 s (16 original + 27 new) |
| Existing backend unit/contract tests | **87 passed, 1 warning**, 0.98 s |
| Complete PostgreSQL integration suite | **49 passed, 130 deselected, 1 warning**, 4.42 s (48 original + 1 new) |
| Unique test coverage in these commands | 130 unit/contract tests and 49 integration tests; no failed or skipped tests |
| Dependencies and imports | `pip check`: no broken requirements; application, Alembic, SQLAlchemy and psycopg imported |
| Development read-only CLI | `current`: `0001_text_foundation (head)`; `check`: no new upgrade operations detected |
| Development contents | Same five research tables plus revision bookkeeping; zero research rows |
| Test cleanup | Test database empty after transactional migration tests |
| Docker | Existing `hissiyat-dev-postgres-1` healthy; no start/recreation/configuration change required |
| Frontend | Not rerun for this backend-only correction; earlier frontend results above are historical |

Executed from `backend/` with `.\.venv\Scripts\python.exe -B`:

```text
-m pytest tests/unit/test_migration_safety.py
-m pytest tests/test_health.py tests/unit/test_data_contracts.py tests/unit/test_database.py tests/unit/test_database_config.py tests/unit/test_readiness.py
-m pytest -m integration
-m pip check
-m alembic -x target=development current
-m alembic -x target=development check
-m alembic -x target=test current
```

The correction edits only `app/core/migrations.py`, `migrations/env.py`, the two
migration/schema test files and these two relevant documents. Schema metadata,
the frozen revision, existing input contracts, connection/configuration files,
dependencies, frontend, private environment files and proposal remain intact.
No development upgrade/downgrade, new research table, dependency, ingestion or NLP
was added. All Phase 2A changes, including this correction, remain uncommitted;
HEAD stays `5744d05885f5b261a13323ae226dc6ba6ab8c3dc` with two commits and no remote.
The existing Starlette/httpx warning remains. The guard validates the observed
client destination and SQL database name, not authenticated server identity.
