"""Synthetic ingestion in transactional test DDL; no persistent test/dev writes."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
from psycopg import sql
import pytest
from sqlalchemy import event, func, select, text, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.sql.dml import Insert

from app.core.database import Database
from app.core.migrations import BACKEND_ROOT, inspect_migration_state, migration_settings
from app.core.schema import collection_events, data_sources, metadata, source_policies, source_records, text_versions
from app.ingestion import service
from app.ingestion.contracts import TextImportBatch

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def settings():
    return migration_settings("test")


@pytest.fixture(scope="module")
def migrated_connection(settings):
    database = Database(settings)
    try:
        with database.connection() as connection:
            with connection.begin() as outer:
                try:
                    inspect_migration_state(connection, "hissiyat_test")
                    config = Config(str(BACKEND_ROOT / "alembic.ini"))
                    config.attributes.update(connection=connection, target="test", operation="upgrade")
                    command.upgrade(config, "head")
                    yield connection
                finally:
                    if outer.is_active:
                        outer.rollback()
    finally:
        database.close()


@pytest.fixture
def connection(migrated_connection):
    with migrated_connection.begin_nested() as savepoint:
        try:
            yield migrated_connection
        finally:
            if savepoint.is_active:
                savepoint.rollback()


@pytest.fixture
def batches():
    return json.loads((Path(__file__).parents[1] / "fixtures/synthetic_imports.json").read_text(encoding="utf-8"))["batches"]


def encode(payload):
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def counts(connection):
    return {name: connection.execute(select(func.count()).select_from(table)).scalar_one()
            for name, table in metadata.tables.items()}


def run(connection, settings, batches, name="base"):
    return service.import_synthetic_batch(connection, settings, encode(batches[name]))


def test_persistence_relationships_timestamps_unicode_and_metadata(connection, settings, batches):
    result = run(connection, settings, batches)
    assert result.status == "applied" and result.counts == dict(accepted=2, rejected=0, duplicate=0, failed=0)
    assert counts(connection) == dict(data_sources=1, source_policies=1, collection_events=1, source_records=2, text_versions=2)
    rows = connection.execute(select(
        source_records.c.source_record_id, source_records.c.published_at,
        source_records.c.first_collection_event_id, text_versions.c.text_content,
        text_versions.c.retrieved_at, text_versions.c.collection_event_id,
        collection_events.c.id, source_policies.c.usage_status, data_sources.c.source_key,
    ).select_from(text_versions.join(source_records,
        text_versions.c.source_record_id == source_records.c.id).join(collection_events,
        text_versions.c.collection_event_id == collection_events.c.id).join(source_policies,
        collection_events.c.policy_id == source_policies.c.id).join(data_sources,
        source_records.c.source_id == data_sources.c.id))).mappings().all()
    for row in rows:
        assert row["first_collection_event_id"] == row["collection_event_id"] == row["id"] == result.collection_event_id
        assert row["usage_status"] == "unverified" and row["source_key"] == "synthetic-phase2b-text"
    by_id = {r["source_record_id"]: r for r in rows}
    assert by_id["synthetic-en-001"]["published_at"] == datetime(2026, 1, 1, 8, tzinfo=timezone.utc)
    assert by_id["synthetic-en-001"]["retrieved_at"] == datetime(2026, 1, 2, 12, tzinfo=timezone.utc)
    assert by_id["synthetic-tr-001"]["published_at"] is None
    assert by_id["synthetic-tr-001"]["text_content"] == batches["base"]["records"][1]["record"]["text"]
    assert [r.language_code for r in result.rows] == ["en", "tr"]
    assert [r.has_publication_timestamp for r in result.rows] == [True, False]
    assert result.language_and_quality_storage == "input_and_receipt_only"
    assert result.rows[1].retrieved_at.utcoffset() == timedelta(hours=3)
    assert result.rows[1].published_at is None
    canonical = json.dumps(batches["base"], sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    assert result.fixture_id == batches["base"]["fixture_id"]
    assert result.fixture_fingerprint == hashlib.sha256(canonical.encode()).hexdigest()


def test_repeated_identical_import_preserves_every_row_and_provenance(connection, settings, batches):
    first = run(connection, settings, batches)
    before = counts(connection)
    second = run(connection, settings, batches)
    assert second.counts == dict(accepted=0, rejected=0, duplicate=2, failed=0)
    assert before == counts(connection)
    assert [r.text_version_id for r in first.rows] == [r.text_version_id for r in second.rows]
    assert first.collection_event_id == second.collection_event_id
    assert all(not r.record_created for r in second.rows)


def test_repeated_identity_within_batch_is_one_logical_record(connection, settings, batches):
    result = run(connection, settings, batches, "within-batch")
    assert result.counts == dict(accepted=1, rejected=0, duplicate=1, failed=0)
    assert result.rows[0].source_record_id == result.rows[1].source_record_id
    assert counts(connection)["source_records"] == counts(connection)["text_versions"] == 1


def test_record_identity_is_source_scoped_and_unknown_rights_remain_unknown(connection, settings, batches):
    first = run(connection, settings, batches)
    other = run(connection, settings, batches, "other-source")
    assert other.counts["accepted"] == 1
    assert other.rows[0].source_record_id != first.rows[0].source_record_id
    assert counts(connection)["data_sources"] == 2 and counts(connection)["source_records"] == 3
    assert set(connection.execute(select(source_policies.c.usage_status)).scalars()) == {"unknown", "unverified"}


def test_genuine_reacquisition_adds_only_event_and_preserves_original_version(connection, settings, batches):
    first = run(connection, settings, batches)
    second = run(connection, settings, batches, "reacquisition")
    assert second.counts["duplicate"] == 2 and second.collection_event_id != first.collection_event_id
    assert counts(connection)["collection_events"] == 2
    assert counts(connection)["source_records"] == counts(connection)["text_versions"] == 2
    assert all(row.version_collection_event_id == first.collection_event_id for row in second.rows)
    assert all(row.retrieved_at == datetime(2026, 1, 4, 12, tzinfo=timezone.utc) for row in second.rows)
    assert connection.execute(select(text_versions.c.retrieved_at).limit(1)).scalar_one() == datetime(2026, 1, 2, 12, tzinfo=timezone.utc)


def test_changed_content_requires_explicit_new_version_and_never_overwrites(connection, settings, batches):
    first = run(connection, settings, batches)
    changed = run(connection, settings, batches, "new-version")
    assert changed.counts["accepted"] == 1
    assert changed.rows[0].source_record_id == first.rows[0].source_record_id
    assert changed.rows[0].text_version_id != first.rows[0].text_version_id
    assert counts(connection)["source_records"] == 2 and counts(connection)["text_versions"] == 3
    original = connection.execute(select(text_versions.c.text_content).where(text_versions.c.id == first.rows[0].text_version_id)).scalar_one()
    assert original == batches["base"]["records"][0]["record"]["text"]
    assert run(connection, settings, batches, "new-version").counts["duplicate"] == 1


def test_identical_content_with_another_declared_key_does_not_add_version(connection, settings, batches):
    first = run(connection, settings, batches)
    repeated = run(connection, settings, batches, "same-content-new-key")
    assert repeated.counts["duplicate"] == 1
    assert repeated.rows[0].text_version_id == first.rows[0].text_version_id
    assert counts(connection)["text_versions"] == 2 and counts(connection)["collection_events"] == 2


def test_content_reference_and_undetermined_language(connection, settings, batches):
    result = run(connection, settings, batches, "reference")
    row = connection.execute(select(text_versions)).mappings().one()
    assert result.counts["accepted"] == 1
    assert row["text_content"] is None and row["content_reference"] == "urn:synthetic:phase2b:permitted-content"
    assert result.rows[0].language_code == "und" and result.rows[0].language_method == "undetermined"


@pytest.mark.parametrize("case,code", [
    ("content", "version_conflict"), ("publication", "record_provenance_conflict"),
    ("retrieval", "version_provenance_conflict"), ("policy", "policy_conflict"),
    ("event", "collection_conflict"),
])
def test_conflicting_existing_provenance_is_rejected_without_overwrite(connection, settings, batches, case, code):
    run(connection, settings, batches)
    if case == "content":
        connection.execute(update(text_versions).values(text_content="Entirely synthetic conflict canary."))
    elif case == "publication":
        connection.execute(update(source_records).values(published_at=None))
    elif case == "retrieval":
        connection.execute(update(text_versions).values(retrieved_at=datetime(2026, 1, 1, tzinfo=timezone.utc)))
    elif case == "policy":
        connection.execute(update(source_policies).values(usage_status="denied"))
    else:
        connection.execute(update(collection_events).values(source_reference="urn:synthetic:conflicting-event"))
    before = {name: connection.execute(select(table)).all() for name, table in metadata.tables.items()}
    result = run(connection, settings, batches)
    assert (result.status, result.code) == ("rejected", code)
    assert result.counts["accepted"] == result.counts["duplicate"] == 0
    assert before == {name: connection.execute(select(table)).all() for name, table in metadata.tables.items()}


@pytest.mark.parametrize("failure", ["foreign_key", "database", "processing"])
def test_mid_batch_failure_rolls_back_all_rows_and_retry_is_safe(connection, settings, batches, caplog, failure):
    calls = 0
    canary = "SYNTHETIC_PRIVATE_FAILURE_CANARY"

    def fail_second_version(conn, statement, multiparams, parameters, execution_options):
        nonlocal calls
        if isinstance(statement, Insert) and statement.table is service.text_versions:
            calls += 1
            if calls == 2:
                if failure == "foreign_key":
                    statement = statement.values(collection_event_id=uuid4())
                elif failure == "database":
                    raise OperationalError("synthetic statement", {"text": canary}, Exception(canary))
                else:
                    raise RuntimeError(canary)
        return statement, multiparams, parameters

    before = counts(connection)
    event.listen(connection, "before_execute", fail_second_version, retval=True)
    try:
        result = run(connection, settings, batches)
    finally:
        event.remove(connection, "before_execute", fail_second_version)
    assert result.status == "failed" and result.counts["failed"] == 2
    assert counts(connection) == before and all(value == 0 for value in before.values())
    assert canary not in result.model_dump_json() + caplog.text
    for entry in batches["base"]["records"]:
        assert entry["record"]["text"] not in result.model_dump_json() + caplog.text
    assert run(connection, settings, batches).counts["accepted"] == 2


def test_invalid_second_record_never_partially_persists(connection, settings, batches):
    payload = deepcopy(batches["base"])
    payload["records"][1]["record"]["retrieved_at"] = "invalid"
    before = counts(connection)
    result = service.import_synthetic_batch(connection, settings, encode(payload))
    assert result.code == "invalid_input" and result.counts["rejected"] == 2
    assert counts(connection) == before


def test_unreviewed_content_cannot_enter_even_with_a_registered_fixture_id(connection, settings, batches):
    payload = deepcopy(batches["base"])
    payload["records"][0]["record"]["text"] = "Synthetic unauthorized content substitution."
    result = service.import_synthetic_batch(connection, settings, encode(payload))
    assert result.code == "synthetic_authorization_required"
    assert all(value == 0 for value in counts(connection).values())


@pytest.mark.parametrize("entrypoint", ["public", "internal"])
def test_actual_development_connection_is_refused_despite_test_settings(settings, batches, entrypoint):
    database = Database(migration_settings("development"))
    try:
        with database.connection() as connection:
            with connection.begin():
                result = (run(connection, settings, batches) if entrypoint == "public" else
                          service._apply_batch(connection, encode(batches["base"]), settings=settings))
                assert (result.status, result.code) == ("rejected", "unsafe_target_or_schema")
    finally:
        database.close()


@pytest.mark.parametrize("entrypoint", ["public", "internal"])
def test_caller_must_own_an_active_transaction(settings, batches, entrypoint):
    database = Database(settings)
    try:
        with database.connection() as connection:
            assert not connection.in_transaction()
            result = (run(connection, settings, batches) if entrypoint == "public" else
                      service._apply_batch(connection, encode(batches["base"]), settings=settings))
            assert result.code == "unsafe_target_or_schema" and not connection.in_transaction()
    finally:
        database.close()


def test_synthetic_workflow_demonstration(connection, settings, batches):
    before = counts(connection)
    first = run(connection, settings, batches)
    after_first = counts(connection)
    relationships = connection.execute(select(func.count()).select_from(
        text_versions.join(source_records, text_versions.c.source_record_id == source_records.c.id)
        .join(collection_events, text_versions.c.collection_event_id == collection_events.c.id)
        .join(source_policies, collection_events.c.policy_id == source_policies.c.id)
        .join(data_sources, source_policies.c.source_id == data_sources.c.id)
    )).scalar_one()
    assert relationships == 2
    repeated = run(connection, settings, batches)
    after_repeat = counts(connection)
    invalid = deepcopy(batches["base"])
    invalid["records"][1]["record"]["published_at"] = "invalid"
    rejected = service.import_synthetic_batch(connection, settings, encode(invalid))
    assert first.counts["accepted"] == 2 and repeated.counts["duplicate"] == 2
    assert rejected.code == "invalid_input" and after_first == after_repeat == counts(connection)
    assert all(value == 0 for value in before.values())
    print(json.dumps({"synthetic_demo": {"before": before, "after_first": after_first,
        "after_repeat": after_repeat, "after_invalid": counts(connection),
        "verified_relationships": relationships, "first_result": first.counts, "repeat_result": repeated.counts,
        "invalid_result": rejected.counts, "cleanup": "outer test transaction rollback"}}))


@pytest.mark.parametrize("shape", ["old_model_call", "raw_bytes"])
def test_previous_internal_bypass_rejects_modified_content_before_any_sql(connection, settings, batches, shape):
    payload = deepcopy(batches["base"])
    payload["records"][0]["record"]["text"] = "Entirely synthetic unreviewed review canary."
    attempted = TextImportBatch.model_validate(payload) if shape == "old_model_call" else encode(payload)
    executed = []

    def observe(*args):
        executed.append(True)

    before = counts(connection)
    event.listen(connection, "before_cursor_execute", observe)
    try:
        result = (service._apply_batch(connection, attempted) if shape == "old_model_call" else
                  service._apply_batch(connection, attempted, settings=settings))
    finally:
        event.remove(connection, "before_cursor_execute", observe)
    assert result.status == "rejected" and not executed
    assert result.fixture_fingerprint is None
    assert counts(connection) == before and all(v == 0 for v in before.values())
    assert not hasattr(service, "_resolve")


def test_internal_boundary_accepts_only_the_same_authorized_raw_payload(connection, settings, batches):
    payload = encode(batches["base"])
    result = service._apply_batch(connection, payload, settings=settings)
    assert result.status == "applied" and result.counts["accepted"] == 2
    canonical = json.dumps(batches["base"], sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    assert result.fixture_fingerprint == hashlib.sha256(canonical.encode()).hexdigest()
    assert run(connection, settings, batches).counts["duplicate"] == 2


def test_caller_mutation_after_authorization_cannot_change_owned_input(connection, settings, batches, monkeypatch):
    caller_data = deepcopy(batches["base"])
    payload = encode(caller_data)
    original_text = caller_data["records"][0]["record"]["text"]
    original_guard = service._validate_connection_logging

    def mutate_caller_owned_data(conn):
        original_guard(conn)
        caller_data["records"][0]["record"]["text"] = "Synthetic caller mutation after authorization."

    monkeypatch.setattr(service, "_validate_connection_logging", mutate_caller_owned_data)
    result = service.import_synthetic_batch(connection, settings, payload)
    assert result.status == "applied"
    stored = connection.execute(select(text_versions.c.text_content).where(
        text_versions.c.id == result.rows[0].text_version_id,
    )).scalar_one()
    assert stored == original_text and stored != caller_data["records"][0]["record"]["text"]
    assert result.fixture_fingerprint == service.APPROVED_FIXTURES[batches["base"]["fixture_id"]]


def qualified_counts(connection, schema, names):
    return {
        name: connection.execute(text(sql.SQL("SELECT count(*) FROM {}").format(
            sql.Identifier(schema, name),
        ).as_string())).scalar_one()
        for name in names
    }


@pytest.mark.parametrize("shadows", [("text_versions",), tuple(metadata.tables)], ids=["original", "all-five"])
@pytest.mark.parametrize("explicit_temp_path", [False, True], ids=["default-path", "temp-first"])
def test_public_ingestion_ignores_temporary_shadows(migrated_connection, settings, batches, shadows, explicit_temp_path):
    connection = migrated_connection
    expected_counts = dict(data_sources=1, source_policies=1, collection_events=1, source_records=2, text_versions=2)
    with connection.begin_nested() as experiment:
        try:
            for name in shadows:
                create_shadow = sql.SQL("CREATE TEMP TABLE {} (LIKE {} INCLUDING ALL) ON COMMIT DROP").format(
                    sql.Identifier(name), sql.Identifier("public", name),
                )
                connection.execute(text(create_shadow.as_string()))
            connection.execute(text(
                "SET LOCAL search_path TO pg_temp, public" if explicit_temp_path else "SET LOCAL search_path TO DEFAULT"
            ))
            # Verify the session really would resolve each unqualified name to its temporary twin.
            for name in shadows:
                assert connection.execute(text("SELECT to_regclass(:name) = to_regclass(:shadow)"), {
                    "name": name, "shadow": f"pg_temp.{name}",
                }).scalar_one() is True

            first = run(connection, settings, batches)
            assert first.status == "applied" and first.counts == dict(accepted=2, duplicate=0, rejected=0, failed=0)
            assert qualified_counts(connection, "public", expected_counts) == expected_counts
            assert qualified_counts(connection, "pg_temp", shadows) == dict.fromkeys(shadows, 0)
            canonical = json.dumps(batches["base"], sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            assert first.fixture_fingerprint == hashlib.sha256(canonical.encode()).hexdigest()
            versions = connection.execute(text("""
                SELECT v.id, r.id AS record_id, v.collection_event_id, r.source_record_id,
                       r.first_collection_event_id, p.policy_reference, s.source_key, v.text_content
                FROM public.text_versions AS v
                JOIN public.source_records AS r ON r.id = v.source_record_id AND r.source_id = v.source_id
                JOIN public.collection_events AS e ON e.id = v.collection_event_id AND e.source_id = v.source_id
                JOIN public.source_policies AS p ON p.id = e.policy_id AND p.source_id = e.source_id
                JOIN public.data_sources AS s ON s.id = v.source_id
            """)).mappings().all()
            assert len(versions) == len(first.rows)
            by_version = {row["id"]: row for row in versions}
            for receipt, entry in zip(first.rows, batches["base"]["records"], strict=True):
                record = entry["record"]
                stored = by_version[receipt.text_version_id]
                assert stored["record_id"] == receipt.source_record_id
                assert stored["collection_event_id"] == stored["first_collection_event_id"] == first.collection_event_id
                assert stored["source_record_id"] == record["source_record_id"]
                assert stored["policy_reference"] == record["collection"]["source_policy"]["policy_reference"]
                assert stored["source_key"] == record["collection"]["source_policy"]["source_id"]
                assert stored["text_content"] == record["text"]

            repeat = run(connection, settings, batches)
            assert repeat.counts["duplicate"] == 2
            assert [row.text_version_id for row in repeat.rows] == [row.text_version_id for row in first.rows]
            assert qualified_counts(connection, "public", expected_counts) == expected_counts

            # Exercise the same-content lookup under a different key as well as the original key.
            reused = run(connection, settings, batches, "same-content-new-key")
            assert reused.counts["duplicate"] == 1
            assert reused.rows[0].text_version_id == first.rows[0].text_version_id
            expected_counts["collection_events"] = 2
            assert qualified_counts(connection, "public", expected_counts) == expected_counts

            canary = "Entirely synthetic public version conflict."
            connection.execute(text("UPDATE public.text_versions SET text_content = :value WHERE id = :id"),
                               {"value": canary, "id": first.rows[0].text_version_id})
            rejected = run(connection, settings, batches)
            assert (rejected.status, rejected.code) == ("rejected", "version_conflict")
            assert rejected.counts["rejected"] == 2
            assert connection.execute(text("SELECT text_content FROM public.text_versions WHERE id = :id"),
                                      {"id": first.rows[0].text_version_id}).scalar_one() == canary
            assert qualified_counts(connection, "public", expected_counts) == expected_counts
            assert qualified_counts(connection, "pg_temp", shadows) == dict.fromkeys(shadows, 0)
            assert experiment.is_active and connection.in_transaction()
        finally:
            if experiment.is_active:
                experiment.rollback()

    assert qualified_counts(connection, "public", expected_counts) == dict.fromkeys(expected_counts, 0)
    for name in shadows:
        assert connection.execute(text("SELECT to_regclass(:shadow)"), {"shadow": f"pg_temp.{name}"}).scalar_one() is None


@pytest.mark.parametrize("option_source", ["connection", "engine", "malformed", "unverifiable"])
def test_supplied_schema_translation_is_rejected_before_sql(settings, batches, monkeypatch, option_source):
    database = Database(settings)
    executed = []

    def observe(*args):
        executed.append(True)

    def unavailable():
        raise RuntimeError("SYNTHETIC_SCHEMA_OPTIONS_CANARY")

    try:
        if option_source == "engine":
            database._engine.update_execution_options(schema_translate_map={"public": "pg_temp"})
        with database.connection() as connection, connection.begin() as outer:
            if option_source == "connection":
                connection.execution_options(schema_translate_map={"public": "pg_temp"})
            elif option_source == "engine":
                # A connection override must not hide the engine's nondefault mapping.
                connection.execution_options(schema_translate_map=None)
            elif option_source == "malformed":
                connection.execution_options(schema_translate_map="not-a-schema-map")
            else:
                monkeypatch.setattr(connection, "get_execution_options", unavailable)
            event.listen(connection, "before_cursor_execute", observe)
            try:
                result = run(connection, settings, batches)
                assert (result.status, result.code) == ("rejected", "unsafe_target_or_schema")
                assert result.fixture_fingerprint is None
                assert result.counts["rejected"] == 2
                assert "SYNTHETIC_SCHEMA_OPTIONS_CANARY" not in result.model_dump_json()
                assert not executed and outer.is_active
            finally:
                event.remove(connection, "before_cursor_execute", observe)
                outer.rollback()
    finally:
        database.close()
