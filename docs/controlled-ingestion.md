# Controlled synthetic text ingestion (Phase 2B)

`app/ingestion/` provides a local application-service boundary. It has no HTTP
route, upload screen, CLI that commits data, source client or real-data enable flag.
The five existing Core tables and `0001_text_foundation` remain unchanged.

## Input and execution boundary

The service accepts UTF-8 JSON bytes, at most 64 KiB. The envelope is
`{"format_version":"hissiyat.text-import.v1","fixture_id":"...","records":[...]}`.
Each entry has a nonblank `version_key` and a `record` validated by the unchanged
Phase 1D `TextRecordInput`. Extra fields, duplicate JSON keys, nonfinite constants,
unsupported versions and invalid input are rejected. One batch contains 1–50
entries with exactly the same `CollectionMetadata`. Its `collection_id` must be
an explicitly supplied canonical UUID; `method` must be `file_import`.

The complete runnable examples are the seven reviewed batches in
`backend/tests/fixtures/synthetic_imports.json`. They contain invented English and
Turkish sentences, missing publication/language metadata, content references,
and repeat/version scenarios. They are never scientific observations.

`import_synthetic_batch(connection, settings, payload)` requires a caller-owned
active transaction. It validates both test settings and the actual synchronous
psycopg destination with the existing migration safety checks, then requires the
reviewed initial schema. Only `127.0.0.1:55432/hissiyat_test` in the `test`
environment is allowed. Development/production settings, a supplied development
connection disguised by test settings, an absent transaction or an unexpected
schema fail closed. The service neither opens connections nor applies migrations.

## Authorization is separate from metadata

Only exact canonical SHA-256 fingerprints in the immutable code-owned
`synthetic_catalog.py` are authorized. Fingerprints cover every original JSON
field, including unmasked text; whitespace/key-order differences do not matter.
The raw UTF-8 input must be an immutable `bytes` object. Both the public function
and the internal `_apply_batch` boundary parse, validate and authorize those owned
bytes. Caller-created Pydantic models (including validation-bypassing constructed
models), mutable dictionaries/buffers and supplied approval/fingerprint fields
cannot replace that check. The former direct `_apply_batch(connection, model)`
call is rejected before SQL; direct raw-byte calls require explicit test settings
and pass the same target, logging and schema guards. SQL-writing helpers are
closures over the authorized frozen model and its computed fingerprint, not
independently callable module persistence APIs. The receipt reports that actual
computed fingerprint, rather than looking up a label after writing.

The fixture ID, a synthetic-looking source name or a JSON approval assertion
cannot authorize changed content. Updating this closed catalog requires review
of the entire synthetic fixture and new immutable fixture/event references.
It is not an extensible runtime permission API or an authority over online data.

Unknown/unverified policy status is stored as supplied for these synthetic
fixtures; it is never upgraded to approved. Source/policy rows and decision
references remain metadata claims. Real-data import is disabled. Before any
future real-data path, independently verify source access, licenses/terms,
permitted operations, retention/withdrawal requirements, personal-data handling
and explicit project approval through a trusted authorization mechanism.
This boundary does not defend against an operator changing trusted Python code
or writing directly to the database with privileged credentials.

## Supplied connections and SQL logging

The service supports ordinary synchronous SQLAlchemy Core `Connection`/`Engine`
objects whose actual psycopg destination passes the existing checks. Before
creating its savepoint or executing schema/text SQL it additionally requires:

- `engine.hide_parameters is True` and `engine.echo is False`, using explicit
  boolean values rather than truthy strings, integers or unknown settings.
- A standard Python SQLAlchemy engine logger with an established effective level
  of INFO or higher, and DEBUG disabled. Unknown/inaccessible properties fail
  closed with a constant `unsafe_connection_logging` rejection.

Externally configured INFO logging is supported: SQLAlchemy hides bound values.
The logging tests confirm that real text INSERT statements ran while the approved
harmless sentence sentinel was absent from captured logs. Unsafe/unknown parameter
hiding, echo and externally enabled DEBUG are rejected before any SQL is executed.
`hide_parameters` alone is insufficient: SQLAlchemy DEBUG can log returned rows,
which may contain inline text even when bind values are hidden.

The service reads these settings; it never changes a caller's engine/logger,
handlers, global levels or credentials. The trusted caller must keep connection
and logging configuration stable during the operation. This check covers standard
SQLAlchemy parameter/row logging, not arbitrary custom event listeners, handlers,
tracers, profilers, logging prefixes containing caller-supplied sensitive values,
concurrent reconfiguration or malicious code with process/database access.
Python naming conventions and local closures are not a sandbox against such code.
Connection-creation diagnostics outside the import call are also the caller's
responsibility. No real-data authorization is introduced by these safeguards.

## PostgreSQL relation selection

PostgreSQL resolves an unqualified name such as `text_versions` through the
session search path. An existing temporary schema can take precedence even after
`SET LOCAL search_path TO public`. The schema check previously verified the
public tables while the ingest statements still used unqualified names.

Ingestion uses its own SQLAlchemy Core table bindings copied from the shared
metadata with an explicit `public` schema. The five bindings cover inserts and
their conflict targets, row locks, identity lookups, version-key lookups and
same-content lookups. The shared metadata and Alembic DDL stay separate. The
service checks execution options on both the supplied connection and its engine
before the savepoint. An explicit non-None `schema_translate_map` or unavailable
options cause an `unsafe_target_or_schema` rejection before any SQL.

PostgreSQL regression cases create a temporary `text_versions` twin and all five
temporary twins under the default and explicit temporary-first search paths.
Qualified assertions verify public row counts, stored text and receipt IDs,
fingerprints, deduplication and conflict handling. Temporary tables remain empty,
and the test savepoints remove them and the inserted rows on rollback. The
receipt describes changes in the verified public relations within the caller's
transaction. Its durability depends on the caller's eventual commit.

These guarantees assume a trusted connection, stable execution options and
callers that preserve the checked tables and constraints. A privileged caller
can execute its own SQL or install instrumentation. Concurrent writers still
need the locking protocol described below for same-content deduplication.

## Identity, provenance and version rules

- `source_id` maps to `data_sources.source_key`; policies are source-scoped by
  `policy_reference`. Existing supplied policy values must match, without updates.
- The collection UUID maps directly to `collection_events.id`. Replaying that
  event requires equal source, policy, method, time, status and export reference.
  A genuine acquisition uses an explicit new event UUID/reference. Successful
  events have `completed` status; this is not scientific eligibility or permission.
- Logical record identity is `(source_id, source_record_id)`. The database UUID
  is internal identity. Publication time, ID origin/fallback method and original
  reference must agree on later imports; conflicts are rejected, including a
  later attempted replacement of an unknown publication time. First-event
  provenance is never overwritten.
- A version key is explicit, scoped to the record and immutable. The same key
  with different content rejects the entire batch. Changed content with a new
  explicit key can create a new version; no key is invented from content.
- Exact inline text/reference equality under another key returns the existing
  version without creating an alias row. There is no normalization, near-duplicate
  detection, cross-record text deduplication or cross-source identity merging.
- A duplicate preserves its first stored retrieval time/event. Conflicting
  retrieval time for the same event is rejected. A genuinely new event may
  observe the same version again and retain its incoming time in the receipt.

PostgreSQL uniqueness constraints, `ON CONFLICT DO NOTHING` and row locks arbitrate
identity conflicts. A source row lock serializes this boundary's same-source
batches through the caller's transaction. No parallel-writer load test was
performed; unrelated writers must follow the same protocol for content equality
under different keys, since that equality has no separate unique constraint.

## Metadata storage limits

Publication time remains nullable and distinct from retrieval time. The existing
contract checks aware timestamps and publication/retrieval ordering. PostgreSQL
retains instants, not original offsets; the input/receipt retain the supplied
offsets. Missing publication time remains NULL and never grants temporal-analysis
eligibility. No import result certifies scientific eligibility.

The schema has no language/quality assessment columns. Validated language code,
method, quality label, publication/retrieval metadata and fixture fingerprint are
preserved in the returned receipt and reviewed input, **not as durable database
assessments**. The result explicitly says `input_and_receipt_only`. Event export
references identify the immutable synthetic examples, but SQL alone cannot
reconstruct all of that metadata. Keep the input and receipt together for this
demonstration; they are not a durable research corpus or a substitute for a later
approved metadata design.

There is also no many-to-many acquisition/version observation table. A new event
can be stored for a duplicate, while the version still points to its first event;
the receipt associates the new event with that reused version. That additional
association and the incoming duplicate retrieval time are not persisted as SQL
relations. No unrelated column is repurposed to conceal these limitations.

## Atomic results and errors

Each batch owns one savepoint inside the caller's transaction. Success releases
that savepoint; `applied` does **not** claim an outer commit. Tests always roll
back the outer transaction, including initial test DDL. The service never commits.

An `accepted` entry creates a version; a `duplicate` reuses one. Receipts contain
internal record/version IDs and whether the logical record was new. Invalid
input, authorization failure or a provenance conflict rejects the entire batch;
database/processing failures mark the entire batch failed. No rolled-back entry
is reported accepted or duplicate. Partial acceptance is not implemented.
`result.counts` reports accepted/rejected/duplicate/failed categories. Malformed,
oversize or over-limit envelopes have no enumerated rows and a batch-level code;
otherwise an atomic rejection/failure covers all submitted entries.

Errors contain constant codes, row indexes and Pydantic error-code counts only.
They contain no input text, references, unknown field names, SQL, credentials or
driver messages. Exceptions are not logged. Successful receipts also omit raw
text/references; they are diagnostic metadata, not public research results.

## Tests and smallest demonstration

From `backend/`, with the existing Hissiyat PostgreSQL service available:

```powershell
.\.venv\Scripts\python.exe -B -m pytest
.\.venv\Scripts\python.exe -B -m pytest -m integration --tb=no
.\.venv\Scripts\python.exe -B -m pytest -m integration -s --tb=no tests/integration/test_synthetic_ingestion.py -k demonstration
```

The module migrates only inside an owned test transaction. Each test adds a
savepoint and rolls it back; final teardown rolls back the initial schema too.
There are no resets, drops, truncates, dev inserts or volume operations. The
demonstration prints only table counts and result categories, verifies the join
graph through the persistence test, repeats the same fixture, rejects invalid
input, and leaves no persistent rows/tables. Separate failure-injection tests
exercise an actual FK violation after an earlier row succeeded, database and
processing failures, complete rollback and safe retry. See
`validation-phase-2b.md` for executed results and final database inspection.

Prompt 17 adds exact regressions for the former model-based helper bypass,
forged claims, caller mutation after encoding, payload/result fingerprint equality,
safe INFO import and zero-SQL rejection of unsafe logging. Failure injection now
uses test-owned SQLAlchemy events instead of an exposed low-level write helper;
these deliberate test hooks do not imply protection from malicious instrumentation.
