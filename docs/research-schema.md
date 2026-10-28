# Minimal research schema and controlled migrations

Phase 2A implements five PostgreSQL tables with SQLAlchemy Core, plus Alembic's
`alembic_version` bookkeeping table. No ingestion, persistence API, external data
collection, normalization or NLP is implemented. Importing metadata and starting
FastAPI do not create or migrate tables.

## Tables and relationships

| Table | Purpose and principal fields |
| --- | --- |
| `data_sources` | UUID identity, unique nonblank `source_key`, optional non-secret `reference`. A registry row grants no permission. |
| `source_policies` | Source FK, source-unique `policy_reference`, `usage_status`, optional decision/documentation references, `reviewed_at`, usage and retention constraints. |
| `collection_events` | Source and policy, method, `occurred_at`, explicit event status, non-secret export/request provenance reference. No authentication or arbitrary query/header payload. |
| `source_records` | UUID identity, source-scoped external ID or documented fallback, first event, optional `published_at` and original reference. |
| `text_versions` | Parent record, collection event, record-scoped `version_key`, original/normalized kind, exactly one inline text/content reference, retrieval timestamp, optional transformation reference and retention deadline. |

All IDs are UUIDs; SQLAlchemy inserts supply client-side UUID defaults. Direct
SQL must supply IDs explicitly. The initial migration intentionally does not
depend on an extension or server UUID generator.
`source_records.source_record_id` is the source's external string identifier;
`text_versions.source_record_id` is the parent record's internal UUID.

Policies belong to sources. Composite foreign keys pair IDs with `source_id` so
events cannot use another source's policy, records cannot use another source's
first event, and text versions cannot combine a record and event from different
sources. The repeated `source_id` in versions is deliberate structural integrity
metadata. Parent `(id, source_id)` uniqueness supports those composite keys.
Foreign keys restrict deletion; no automatic cascade or retention purge exists.
Future writers must use a new policy reference for a changed policy version;
this phase does not implement a policy edit/audit workflow.

`(source_id, source_record_id)` is unique regardless of identifier origin. A local
fallback must have `local_id_method`; a source-provided ID must not. Repeated
retrievals can add versions to the same record; they are not new independent
records. `(source_record_id, version_key)` is unique. A future adapter must define
version identity, deduplication and idempotence rather than blindly inserting.

Checks enforce nonblank supplied strings, valid policy/event/method/content-kind
values, inline/reference content exclusivity, documented local IDs and a
transformation reference for normalized content. Original content has no
transformation reference. These are supplied provenance claims, not proof that
an actual transformation or independent assessment exists. Foreign-key lookup
indexes supplement the primary/unique indexes; there are no analysis indexes.

Policy states are `unknown` (default), `unverified`, `approved`, `denied`.
An approval claim requires a decision reference, but neither that reference nor
the review timestamp is independently authenticated. Event statuses are
`planned` (default), `in_progress`, `completed`, `partial`, `failed`. Method values
match the existing input contract. Incomplete or failed events remain expressible.

## Validation differences and privacy limits

The Phase 1D Pydantic contracts remain unchanged. They are input snapshots, not
table-row schemas: a future adapter must resolve references into UUIDs, supply
an explicit collection status and version key, and enforce trusted permissions.
Language and quality assessments and physical trend storage remain deferred.

PostgreSQL `TIMESTAMPTZ` stores instants and returns timezone-aware values; it
does not retain the original offset or precision. Unlike Pydantic, PostgreSQL
can interpret naive inputs using the session timezone. Strict timezone-aware
input validation must remain at a future write boundary. No publication time is
invented or defaulted. Retrieval time belongs to each text version. The existing
input rule `published_at <= retrieved_at` spans two physical tables and is not a
database check here; enforcing it for future writes needs a validated transaction
or a separately reviewed trigger. No trigger is installed.

Database nonblank checks use PostgreSQL POSIX whitespace rules; Pydantic uses
Unicode `\S`. They are not advertised as identical language/Unicode validators.

Unknown `retention_constraints` or `retention_until=NULL` means **unknown**, not
unlimited retention. There is no deletion scheduler, license interpretation,
trusted approval registry or public-display permission system. A row, a completed
event or even an asserted approved status must not authorize real ingestion,
retention, processing or display. No candidate source currently has final use
approval. Only explicitly synthetic content is used in tests.

Inline database text is plaintext, unlike Pydantic's masked `SecretStr`
representation. There is no encryption/PII removal/access-control layer here.
Future persistence must sanitize driver errors (PostgreSQL constraint details can
include row content), restrict references/notes to necessary non-secret metadata,
minimize personal data and enforce retention. Never store tokens, cookies,
authentication headers, credential URLs or raw sensitive query metadata.

## Migration configuration and inspection

Install `requirements.lock.txt` in the existing backend virtual environment.
Alembic is pinned in `requirements-dev.txt`; its environment reuses `Settings`
and `Database`, never an INI connection URL. No password appears in migration
files, SQL output or deliberate CLI error messages. Driver details are withheld
on migration failure; inspect only redacted diagnostics.

From `backend/`:

```powershell
.\.venv\Scripts\python.exe -B -m alembic heads
.\.venv\Scripts\python.exe -B -m alembic history
.\.venv\Scripts\python.exe -B -m alembic -x target=test current
.\.venv\Scripts\python.exe -B -m alembic -x target=development current
.\.venv\Scripts\python.exe -B -m alembic -x target=test upgrade head --sql
```

The initial revision is `0001_text_foundation`. The explicit revision freezes
the reviewed DDL; it does not import current application metadata at runtime.
The metadata-to-DDL render was reviewed before freezing, and integration tests
compare the migrated schema with the metadata through `alembic check`.

Targets must be exactly `127.0.0.1:55432`, `hissiyat_test` / test environment or
`hissiyat_dev` / development environment. Shell variables can override dotenv;
unexpected effective settings fail before connecting.

Every online path, including a supplied SQLAlchemy connection, additionally
checks the active synchronous psycopg driver's destination through
`connection.connection.driver_connection.info`. An engine URL alone is not
authoritative: a creator or connection arguments may establish a different
destination. The live driver's `host`, `hostaddr`, client `port` and `dbname`
must exactly match the separately validated target. Missing, ambiguous or
unsupported metadata, closed/broken/invalidated connections, unestablished libpq
status and absent active transactions fail closed before schema SQL or migration
execution. Errors contain no destination values, credentials or connection URLs.

The comparison uses the client endpoint `127.0.0.1:55432`, not PostgreSQL's
container-internal listening port `5432`. After that destination check,
`current_database()` separately confirms the connected database name. Neither
driver host/port metadata nor a database name proves authenticated server
identity: proxies/forwarders and a different server using the same endpoint are
outside this guard's assurance. This local phase adds no TLS/certificate or
server-attestation system. Deterministic mock tests verify rejection/control flow;
they are not evidence of actual PostgreSQL endpoint identity. A live integration
test exercises the existing Hissiyat test connection and Docker port mapping.

Preflight also confirms the
actual database, public search path, absence of unexpected relations, schemas,
extensions, routines, custom types/triggers, and either an empty schema or the
known initial object names and revision. It never stamps, resets or repairs an
unknown state. This initial-state guard must be deliberately extended when a
later approved revision changes the expected schema. `check` detects supported
metadata drift; it is not a complete policy/security audit.

## Applying migrations safely

Only a separately intended persistent test setup needs this command; the
integration fixture itself uses transactional DDL:

```powershell
.\.venv\Scripts\python.exe -B -m alembic -x target=test upgrade head
.\.venv\Scripts\python.exe -B -m alembic -x target=test check
```

Before any persistent development upgrade, inspect `current`, review the SQL,
confirm the intended target and obtain explicit project-owner approval when
acting as an agent. Only after that approval:

```powershell
.\.venv\Scripts\python.exe -B -m alembic -x target=development -x allow_development=true upgrade head
.\.venv\Scripts\python.exe -B -m alembic -x target=development check
```

The flag is a deliberate operator guard, not evidence of human approval. Ordinary
startup does not migrate. Current/check inspection does not require the upgrade
flag and rolls back its inspection transaction. Online downgrade, stamp and
unreviewed revision operations are rejected; destructive downgrade is not
implemented. Never use database/volume deletion or a reset to repair migration
state. No downgrade/reset test is performed against development.

## Synthetic integration isolation and deferred work

Explicitly selected schema tests require the dedicated test configuration. A
module-owned outer transaction applies the initial migration; every test has a
savepoint and rolls back its own synthetic rows/negative-test objects. Finally
the outer transaction rolls back even newly created tables and the revision
marker. No drop/truncate/delete cleanup is used. If the test schema was empty,
it is empty afterward; if a recognized initial schema already existed, it is
preserved. Unknown state fails rather than being reset. Tests do not depend on
execution order or touch development.

Corpus versions/memberships, language/quality assessments, trend series and
observations, analysis runs, model versions, embeddings, topics, concept
inferences, human annotations and evaluations are not implemented. Two independent
evaluators remain a research target, not existing annotation data. Ingestion
requires a future approved phase with verified source rights and privacy rules.

References: [Alembic tutorial](https://alembic.sqlalchemy.org/en/latest/tutorial.html),
[shared connection recipe](https://alembic.sqlalchemy.org/en/latest/cookbook.html#sharing-a-connection-across-one-or-more-programmatic-migration-commands),
[libpq connection status accessors](https://www.postgresql.org/docs/current/libpq-status.html),
[SQLAlchemy driver connection](https://docs.sqlalchemy.org/en/21/core/pooling.html#sqlalchemy.pool.ManagesConnection.driver_connection).
