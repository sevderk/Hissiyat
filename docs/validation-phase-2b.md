# Phase 2B validation

Date: 2026-10-28. Scope: closed synthetic text imports, existing-table
persistence, exact idempotency/versioning, provenance and atomic test rollback.
No real-data source, migration, new table, NLP or publication is included.

## Initial and final state

Initial Git inspection confirmed clean `main`, upstream `origin/main`, the exact
three approved rewritten commits and HEAD
`2d1b241ce2c9282890e0b7f885410595af50aeda`. The existing `origin` URL and local
`noreply` configuration were preserved. No GitHub/network source was contacted
in this phase; `origin/main` was inspected as the existing local tracking ref.

Before and after tests, development had the same five research tables plus
`alembic_version`, at `0001_text_foundation`, with zero research rows. The test
database had no tables before or after. Reflected columns, keys, constraints,
relationships and indexes were inspected; the development schema fingerprint
was unchanged: `2798dd12bac4b9747818c409970ad7d12c5ed3167af29a6f307bd2e59d0f5ad6`.
All 13 existing Docker container identities, images and port bindings matched
the initial snapshot. No container/service mutation command was executed.

## Executed checks (original Phase 2B)

| Check | Exact result |
| --- | --- |
| Complete backend unit/regression tests | **157 passed, 70 deselected, 1 warning**, 1.83 s |
| Complete PostgreSQL integration tests | **70 passed, 157 deselected, 1 warning**, 5.09 s |
| Distinct tests in those commands | **227**: previous 179 plus 27 new unit and 21 new integration cases |
| Dependency integrity | `pip check`: no broken requirements |
| Imports | Existing application and new ingestion service/contracts imported |
| Alembic heads and development current | `0001_text_foundation (head)` |
| Test current after rollback | Succeeded with no applied revision |
| Frontend TypeScript | Passed |
| Frontend ESLint | Passed |
| Frontend production build | Passed; Turkish/English pages prerendered |
| Production locale HTTP checks | All four PASS groups: Turkish default, both locale pages/404s, matching nonempty messages |
| Actual backend HTTP | Liveness **200**, readiness **200**, exact existing JSON bodies |
| Temporary verification servers | Only the owned loopback processes started; both stopped in `finally` |

The unit suite includes existing input contracts and all 43 migration-safety
cases. New tests cover all seven canonical fixture fingerprints, immutable
catalog, malformed/oversize/over-limit/duplicate-key/nonfinite JSON, unsupported
formats, invalid source/time/event metadata, untrusted approval/synthetic flags,
content substitution under a known fixture ID and development/production refusal.

New PostgreSQL tests verify all source/policy/event/record/version joins, exact
Turkish text, publication/retrieval separation, nullable publication time,
receipt-only language/quality metadata, repeat imports, repeated identities within
a batch, source-scoped identities, unknown/unverified policy preservation,
new acquisitions, explicit changed versions, identical content under another
key, content references, conflicting immutable provenance, actual FK violations,
database/processing failures after earlier inserts, complete rollback and retry.
An actual development connection passed with test settings is refused before
ingestion; an absent caller transaction is also refused. There are no skipped
tests or hidden failed cases in the final run.

## Synthetic demonstration

The demonstration executes as part of the integration suite and queries two
complete provenance joins. Counts below refer only to its isolated test scope:

| Point | Sources | Policies | Events | Records | Versions |
| --- | ---: | ---: | ---: | ---: | ---: |
| Before | 0 | 0 | 0 | 0 | 0 |
| First import: 2 accepted | 1 | 1 | 1 | 2 | 2 |
| Identical repeat: 2 duplicates | 1 | 1 | 1 | 2 | 2 |
| Invalid timestamp: 2 rejected | 1 | 1 | 1 | 2 | 2 |

Test savepoints and the module's outer transaction roll back the rows and test
DDL afterward. The independent final inspection confirmed the test database
was empty again. Separate FK/database/processing failure cases verify zero
residual source, policy, event, record or version rows after failed batches and
a successful subsequent retry. This is software validation, not a research
experiment or a source-permission decision.

## Commands and corrections

Read-only inspection used Git status/log/refs/remotes/upstream/config, tracked
file hashes, private-file/proposal hashes without displaying contents, existing
contract/schema/migration/test/document reads, PostgreSQL reflection/catalog
queries through `Settings`/`Database`, and narrowly formatted `docker ps -a`.

From `backend/`, using the existing `.venv/Scripts/python.exe -B`:

```text
-m pytest --tb=short -q
-m pytest -m integration --tb=no -q -s
-m pip check
-m alembic heads
-m alembic -x target=development current
-m alembic -x target=test current
```

An import command loaded `app.main`, `app.ingestion` and its batch contract.
Frontend ran `npm run typecheck`, `npm run lint`, `npm run build` with telemetry
disabled. An owned temporary Next/Uvicorn harness on OS-selected loopback ports
ran `node scripts/verify-routes.mjs` and asserted backend status/bodies.
Its non-sensitive local server logs are ignored under `artifacts/phase2b/`.

The first test collection found equal new unit/integration module basenames;
the new integration file was renamed to `test_synthetic_ingestion.py`. An
intermediate run passed 155 cases but had two setup errors because the large
synthetic payload produced an excessive Windows pytest environment-variable
value. Explicit short parameter IDs fixed that test harness issue. Final tests
were rerun after adding the envelope-limit and receipt provenance checks; only
the final results above are reported as passing.

## Integrity and limits

Only the ingestion package, synthetic fixture/tests and relevant documentation
changed. Original contracts, API, database/config infrastructure, schema,
migrations, dependencies and all frontend sources remain unchanged. Private
environment files and the proposal retain their initial hashes. Git history,
branch, upstream, remotes and author configuration remain unchanged; no staging,
commit, amend or push was performed. New files remain uncommitted for review.

The existing Starlette/httpx deprecation and Next ancestor-lockfile warning
remain. Dependency vulnerability advisories were not refreshed or repaired.
No parallel-writer load test, durable language/quality storage, full acquisition
observation linkage, real-data rights system, retention enforcement, live API,
trend ingestion or scientific/NLP eligibility is claimed. See
`controlled-ingestion.md` for the exact implemented and deferred boundaries.

## Prompt 17 focused security correction

Date: 2026-10-28. Prompt 16 reran the original 227 tests successfully but stopped
the Git checkpoint after two additional probes: a direct call to the old internal
model-based persistence helper wrote modified synthetic content and claimed the
original approved digest; a supplied engine with parameter hiding disabled and
INFO logging exposed synthetic text. These were local Python/connection tests,
not remotely reachable HTTP attacks. All probe rows and DDL were rolled back.

The correction makes the old `_apply_batch` name a fully guarded raw-byte
boundary. The public function delegates to that same path. Both require actual
fixture content authorization, explicit test settings, live destination/schema
checks, safe engine logging and an owned transaction. The previous model-based
call fails before SQL. The write helpers now close over the privately parsed,
frozen validated model and its actual computed canonical digest; no module-level
write helper accepts an arbitrary caller-created batch. Fingerprints in results
describe the actual checked input. Caller labels, constructed models, mutable
buffers and forged fingerprint fields do not grant permission.

The supplied connection must have explicit `hide_parameters=True`, `echo=False`
and a standard engine logger with INFO-or-higher effective level and DEBUG
disabled. Missing, unknown, malformed or inaccessible safety properties fail
closed before savepoint/schema/text SQL. INFO logs can show statements but not
bound values; DEBUG rows require separate refusal because parameter hiding does
not mask returned rows. The service does not reconfigure engine/global logging.
Stable caller configuration and trusted instrumentation remain prerequisites;
arbitrary hooks, tracers, custom handlers and hostile same-process Python/SQL
remain outside the guarantee. No real-data authorization is added.

| Current correction check | Exact result |
| --- | --- |
| Focused ingestion authorization/logging unit tests | **48 passed**, 0.74 s |
| Focused PostgreSQL ingestion/logging tests | **33 passed**, 3.11 s |
| Complete backend unit/regression suite | **178 passed, 82 deselected, 1 warning**, 1.59 s |
| Complete PostgreSQL integration suite | **82 passed, 178 deselected, 1 warning**, 5.91 s |
| Distinct complete-suite cases | **260**, including 33 added cases beyond the original 227; focused cases are subsets, not additional totals |
| Dependencies and imports | `pip check`: no broken requirements; application/ingestion contracts/service imported |
| Alembic inspection | Initial revision remains the only head; development current is `0001_text_foundation`; test current has no applied revision |
| Existing health behavior | Existing liveness/readiness unit tests and real PostgreSQL readiness integration test passed |
| Frontend | Not rerun; original Phase 2B typecheck/lint/build/route results above are historical; all frontend files unchanged |

All test commands executed for this correction passed; there were no failed or
skipped tests. New cases cover the exact old internal-helper call without added
arguments, modified raw input through that boundary, forged approval/fingerprint
fields, validation-bypassing caller models, mutable inputs, missing/wrong test
settings, exact payload/receipt digest equality and caller mutation after encoding.
Live regressions verify both entry points reject an actual development connection
and a missing outer transaction. Existing host/port/database and all 43 migration
safety cases remain in the complete unit run.

Logging tests use approved harmless fixture text as a sentinel: substituting new
text would test authorization instead of logging. A safe INFO test proves that
text INSERT SQL actually ran and was parameter-masked. Unsafe/unknown hiding,
echo and external DEBUG tests observe zero executed SQL, zero new rows and no
sentinel in captured logs. An inaccessible-property unit case confirms errors
do not echo the synthetic connection-detail sentinel. Failure injection now uses
test-owned SQLAlchemy events, preserving actual FK/database/processing rollback
and retry coverage after removing the module-level write helper.

Executed from `backend/` with the existing `.venv/Scripts/python.exe -B`:

```text
-m pytest tests/unit/test_text_ingestion.py --tb=short -q
-m pytest -m integration tests/integration/test_synthetic_ingestion.py tests/integration/test_ingestion_logging.py --tb=short -q
-m pytest --tb=short -q
-m pytest -m integration --tb=no -q
-m pip check
-m alembic heads
-m alembic -x target=development current
-m alembic -x target=test current
```

Only `app/ingestion/service.py`, the existing ingestion unit/integration tests,
the new `tests/integration/test_ingestion_logging.py`, and these directly relevant
Phase 2B documents were changed for this correction. The fixture catalog, fixture
contents, contracts, migrations, Core schema, connection factory, dependencies
and frontend remain unchanged. No staging, commit, push, branch/remote change or
identity change is authorized. Language/quality persistence, repeated-observation
links, retention enforcement and parallel-writer validation remain deferred.

Final independent reflection after the correction matched the initial database
snapshot exactly: development retained revision `0001_text_foundation`, the same
schema fingerprint and zero rows in all five research tables; test had no tables
or applied revision. All 13 Docker identity/image/port tuples matched. Hash checks
confirmed the proposal, three private environment files, frontend, fixture/catalog,
schema/migrations and Git configuration were unchanged. All three existing commits
remain on `main` with upstream `origin/main`; no files were staged or committed,
and nothing was pushed. The added logging test leaves ten untracked Phase 2B files
and the same three previously modified tracked documentation files for review.

## Prompt 19 public-schema regression

Date 2026-11-11. The Prompt 18 receipt reported two accepted versions while
`public.text_versions` contained zero rows and the session-local
`pg_temp.text_versions` contained both versions. PostgreSQL resolves an
unqualified relation through the search path, where an implicit temporary
schema can precede `public`. Ingestion now uses five explicit `public` bindings
in separate SQLAlchemy metadata. The service verifies both connection and engine
execution options before running SQL and rejects non-None schema translation
maps and unverifiable options.

The four shadowing cases failed on the original service. With only
`text_versions` shadowed, the public version count was zero. With all five
names shadowed, all five public counts were zero. The corrected service passed
the same cases, including qualified joins, receipt fingerprints, repeated
imports, identical content under another key, version conflicts and rollback
cleanup. Four further cases verify zero-SQL rejection of connection-level,
engine-level, malformed and unverifiable translation settings. The engine
case also covers a connection override that sets the map to None.

| Check | Result |
| --- | --- |
| Shadowing cases against the original service | 4 failed as expected, 31 deselected, 1.33 s |
| Focused ingestion and logging integration | 41 passed, 3.51 s |
| Full backend unit/regression suite | 178 passed, 90 deselected, 1 existing warning, 1.91 s |
| Full PostgreSQL integration suite | 90 passed, 178 deselected, 1 existing warning, 7.07 s |
| Distinct cases in both complete suites | 268 passed, including eight new PostgreSQL cases |
| Python dependency and import checks | Passed |
| Alembic development check in a read-only transaction | No new upgrade operations detected |

Commands ran from `backend/` using the existing `.venv/Scripts/python.exe -B`.
The full test runs used `-m pytest --tb=short -q` and
`-m pytest -m integration --tb=no -q`. The Alembic checks included `heads`,
`current` for development and test, and `command.check` on a supplied
read-only development connection. The frontend results above are historical.

The development and test schema fingerprints matched their initial snapshots.
Development remained at `0001_text_foundation` with zero rows across the five
research tables. Test returned to an empty public schema with no applied
revision. The ingestion bindings have the same columns and foreign-key
relationships as the shared tables. Migration sources, shared metadata and
physical schema are unchanged. The corrected working tree is available for
independent review with an empty Git staging area.
