"""Atomic, source-independent persistence behind a closed synthetic-only gate."""

from collections.abc import Mapping
import hashlib
import json
import logging
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import Connection, Engine, MetaData, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError

from app.contracts.inputs import validation_error_summary
from app.core import schema as research_schema
from app.core.config import Settings
from app.core.migrations import (
    INITIAL_REVISION, MigrationSafetyError, inspect_migration_state,
    validate_connection_target, validate_target,
)
from app.ingestion.contracts import ImportResult, RowResult, TextImportBatch
from app.ingestion.synthetic_catalog import APPROVED_FIXTURES

MAX_INPUT_BYTES = 65536

# Keep the DML bindings separate from the metadata used for Alembic DDL and checks.
_ingestion_metadata = MetaData()
data_sources = research_schema.data_sources.to_metadata(_ingestion_metadata, schema="public")
source_policies = research_schema.source_policies.to_metadata(_ingestion_metadata, schema="public")
collection_events = research_schema.collection_events.to_metadata(_ingestion_metadata, schema="public")
source_records = research_schema.source_records.to_metadata(_ingestion_metadata, schema="public")
text_versions = research_schema.text_versions.to_metadata(_ingestion_metadata, schema="public")


class _ImportConflict(ValueError):
    """Carry only an internal constant code, never database/input details."""


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key.")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("Non-finite JSON constant.")


def _result(status, code, count, errors=None):
    return ImportResult(
        status=status, code=code,
        rows=tuple(RowResult(index=i, status=status, code=code) for i in range(count)),
        validation_errors=errors or {},
    )


def _require_equal(row, values, code):
    if any(row[key] != value for key, value in values.items()):
        raise _ImportConflict(code)


class _UnsafeConnectionLogging(ValueError):
    """Reject unknown logging configuration without exposing its values."""


def _validate_connection_logging(connection: Connection) -> None:
    """Check built-in SQL parameter/row logging; do not reconfigure caller state."""
    try:
        if not isinstance(connection, Connection) or not isinstance(connection.engine, Engine):
            raise _UnsafeConnectionLogging("Unsupported SQLAlchemy connection.")
        engine = connection.engine
        logger = engine.logger
        if engine.hide_parameters is not True or engine.echo is not False:
            raise _UnsafeConnectionLogging("Unsafe SQLAlchemy parameter or echo configuration.")
        if not isinstance(logger, logging.Logger):
            raise _UnsafeConnectionLogging("Unsupported SQLAlchemy logger.")
        level = logger.getEffectiveLevel()
        # hide_parameters masks bind values, but DEBUG can emit returned rows.
        if type(level) is not int or level < logging.INFO or logger.isEnabledFor(logging.DEBUG) is not False:
            raise _UnsafeConnectionLogging("SQLAlchemy row-debug logging must be disabled.")
    except _UnsafeConnectionLogging:
        raise
    except Exception:
        raise _UnsafeConnectionLogging("SQLAlchemy logging safety could not be established.") from None


def _validate_schema_execution_options(connection: Connection) -> None:
    """Ensure SQLAlchemy cannot translate the explicit public schema."""
    try:
        for owner in (connection, connection.engine):
            options = owner.get_execution_options()
            if not isinstance(options, Mapping) or options.get("schema_translate_map") is not None:
                raise MigrationSafetyError("Ingestion requires untranslated SQLAlchemy schemas.")
    except MigrationSafetyError:
        raise
    except Exception:
        raise MigrationSafetyError("Ingestion schema execution options could not be verified.") from None


def _apply_batch(
    connection: Connection, payload: bytes, *, settings: Settings | None = None,
) -> ImportResult:
    """Apply one reviewed JSON batch in a savepoint; caller owns the outer rollback.

    The caller owns the connection and outer transaction. Diagnostics are safe
    result codes; native SQL logging requires the checked engine configuration.
    An applied result describes the savepoint, never a durable scientific corpus.
    """
    count = 0
    if type(payload) is not bytes or len(payload) > MAX_INPUT_BYTES:
        return _result("rejected", "invalid_input", count)
    try:
        data = json.loads(payload.decode("utf-8"), object_pairs_hook=_unique_object, parse_constant=_reject_constant)
        if isinstance(data, dict) and isinstance(data.get("records"), list):
            count = len(data["records"]) if len(data["records"]) <= 50 else 0
        batch = TextImportBatch.model_validate(data)
        # Hash the original parsed JSON, never a SecretStr-masked model dump.
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
        fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    except ValidationError as error:
        return _result("rejected", "invalid_input", count, validation_error_summary(error))
    except (ValueError, TypeError, UnicodeError, RecursionError):
        return _result("rejected", "invalid_input", count)
    if APPROVED_FIXTURES.get(batch.fixture_id) != fingerprint:
        return _result("rejected", "synthetic_authorization_required", count)

    def _resolve(table, values, keys):
        """Let PostgreSQL arbitrate uniqueness before locking/reading the winning row."""
        inserted = connection.execute(insert(table).values(**values).on_conflict_do_nothing(
            index_elements=[table.c[key] for key in keys],
        ).returning(table.c.id)).scalar_one_or_none()
        row = connection.execute(select(table).where(
            *(table.c[key] == values[key] for key in keys),
        ).with_for_update()).mappings().one()
        return row, inserted is not None

    def persist_authorized_input():
        collection = batch.records[0].record.collection
        policy = collection.source_policy
        # This source lock serializes batches for the same source until the outer
        # transaction ends, including same-content/different-key version checks.
        source, _ = _resolve(data_sources, {"source_key": policy.source_id}, ["source_key"])
        policy_values = dict(
            source_id=source["id"], policy_reference=policy.policy_reference,
            usage_status=policy.usage_status, decision_reference=policy.decision_reference,
        )
        policy_row, _ = _resolve(source_policies, policy_values, ["source_id", "policy_reference"])
        _require_equal(policy_row, policy_values, "policy_conflict")
        event_values = dict(
            id=UUID(collection.collection_id), source_id=source["id"], policy_id=policy_row["id"],
            method=collection.method, occurred_at=collection.occurred_at,
            status="completed", source_reference=collection.source_reference,
        )
        event, _ = _resolve(collection_events, event_values, ["id"])
        _require_equal(event, event_values, "collection_conflict")
        rows = []
        for index, entry in enumerate(batch.records):
            record = entry.record
            provenance = dict(
                record_id_origin=record.record_id_origin, local_id_method=record.local_id_method,
                published_at=record.published_at, original_reference=record.original_reference,
            )
            record_row, record_created = _resolve(source_records, dict(
                source_id=source["id"], source_record_id=record.source_record_id,
                first_collection_event_id=event["id"], **provenance,
            ), ["source_id", "source_record_id"])
            _require_equal(record_row, provenance, "record_provenance_conflict")
            content = dict(
                content_kind="original",
                text_content=record.text.get_secret_value() if record.text is not None else None,
                content_reference=record.content_reference, transformation_reference=None,
            )
            version = connection.execute(select(text_versions).where(
                text_versions.c.source_record_id == record_row["id"],
                text_versions.c.version_key == entry.version_key,
            )).mappings().one_or_none()
            if version is not None:
                _require_equal(version, content, "version_conflict")
                created = False
            else:
                # Exact equality only: no normalization, hashes-as-identities or NLP.
                version = connection.execute(select(text_versions).where(
                    text_versions.c.source_record_id == record_row["id"],
                    *(text_versions.c[key].is_(None) if value is None else text_versions.c[key] == value
                      for key, value in content.items()),
                ).order_by(text_versions.c.id).limit(1)).mappings().one_or_none()
                if version is not None:
                    created = False
                else:
                    version, created = _resolve(text_versions, dict(
                        source_record_id=record_row["id"], source_id=source["id"],
                        collection_event_id=event["id"], version_key=entry.version_key,
                        retrieved_at=record.retrieved_at, **content,
                    ), ["source_record_id", "version_key"])
                    _require_equal(version, content, "version_conflict")
            if not created and version["collection_event_id"] == event["id"]:
                _require_equal(version, {"retrieved_at": record.retrieved_at}, "version_provenance_conflict")
            rows.append(RowResult(
                index=index, status="accepted" if created else "duplicate",
                code="new_version" if created else "identical_version",
                source_record_id=record_row["id"], text_version_id=version["id"],
                version_collection_event_id=version["collection_event_id"], record_created=record_created,
                language_code=record.language_code, language_method=record.language_method,
                quality_status=record.quality_status, has_publication_timestamp=record.has_publication_timestamp,
                published_at=record.published_at, retrieved_at=record.retrieved_at,
            ))
        return ImportResult(
            status="applied", code="batch_applied", rows=tuple(rows), collection_event_id=event["id"],
            fixture_id=batch.fixture_id, fixture_fingerprint=fingerprint,
        )

    if not isinstance(settings, Settings):
        return _result("rejected", "unsafe_target_or_schema", count)
    try:
        validate_target(settings, "test")
        validate_connection_target(connection, settings)
        _validate_connection_logging(connection)
        _validate_schema_execution_options(connection)
        with connection.begin_nested():
            if inspect_migration_state(connection, "hissiyat_test") != INITIAL_REVISION:
                raise MigrationSafetyError("The reviewed schema must already exist in the test transaction.")
            result = persist_authorized_input()
        return result
    except _UnsafeConnectionLogging:
        return _result("rejected", "unsafe_connection_logging", count)
    except MigrationSafetyError:
        return _result("rejected", "unsafe_target_or_schema", count)
    except _ImportConflict as error:
        return _result("rejected", str(error), count)
    except (SQLAlchemyError, OSError):
        return _result("failed", "database_failure", count)
    except Exception:
        # Driver/processing exceptions can embed rows or credentials. Never log
        # them or return their messages, traceback, SQL, parameters or causes.
        return _result("failed", "processing_failure", count)


def import_synthetic_batch(connection: Connection, settings: Settings, payload: bytes) -> ImportResult:
    """Use the same full guard as a direct call to the internal batch boundary.

    Only owned raw bytes are accepted. No caller-created model, approval label
    or fingerprint can replace validation of the actual input. SQL-writing
    helpers are local to that guarded operation, not alternative module APIs.
    This is not isolation against hostile code in the trusted Python process.
    """
    return _apply_batch(connection, payload, settings=settings)
