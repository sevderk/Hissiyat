"""Synthetic PostgreSQL tests: all DDL and rows roll back in hissiyat_test only."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from alembic.util import CommandError
import pytest
from sqlalchemy import inspect, insert, select, text, update
from sqlalchemy.exc import IntegrityError

from app.core.database import Database
from app.core.migrations import (
    BACKEND_ROOT, INITIAL_REVISION, MigrationSafetyError, inspect_migration_state, migration_settings,
    validate_connection_target,
)
from app.core.schema import collection_events, data_sources, metadata, source_policies, source_records, text_versions

pytestmark = pytest.mark.integration


def migration_config(connection, operation="upgrade"):
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.attributes.update(connection=connection, target="test", operation=operation)
    return config


@pytest.fixture(scope="module")
def migrated_connection():
    # A module-owned transaction rolls back even the initial DDL; never downgrade/reset.
    settings = migration_settings("test")
    database = Database(settings)
    try:
        with database.connection() as connection:
            transaction = connection.begin()
            try:
                inspect_migration_state(connection, "hissiyat_test")
                command.upgrade(migration_config(connection), "head")
                yield connection
            finally:
                if transaction.is_active:
                    transaction.rollback()
    finally:
        database.close()


@pytest.fixture
def connection(migrated_connection):
    savepoint = migrated_connection.begin_nested()
    try:
        yield migrated_connection
    finally:
        if savepoint.is_active:
            savepoint.rollback()


def add_source(connection):
    return connection.execute(insert(data_sources).values(
        source_key=f"synthetic-{uuid4()}", reference="urn:synthetic:source",
    ).returning(data_sources.c.id)).scalar_one()


def add_graph(connection, source_id=None, record_identifier="synthetic-record-001"):
    source_id = source_id or add_source(connection)
    policy_id = connection.execute(insert(source_policies).values(
        source_id=source_id, policy_reference=f"urn:synthetic:policy:{uuid4()}", usage_status="unverified",
        retention_constraints="Synthetic fixture only; transaction rollback after each test.",
    ).returning(source_policies.c.id)).scalar_one()
    event_id = connection.execute(insert(collection_events).values(
        source_id=source_id, policy_id=policy_id, method="file_import", status="completed",
        occurred_at=datetime(2026, 1, 3, tzinfo=timezone.utc), source_reference="urn:synthetic:export",
    ).returning(collection_events.c.id)).scalar_one()
    record_id = connection.execute(insert(source_records).values(
        source_id=source_id, source_record_id=record_identifier, first_collection_event_id=event_id,
    ).returning(source_records.c.id)).scalar_one()
    fixtures = json.loads((Path(__file__).parents[1] / "fixtures/synthetic_contracts.json").read_text(encoding="utf-8"))
    content = fixtures["text_records"][1]["text"]
    retrieved_at = datetime(2026, 1, 2, 15, tzinfo=timezone(timedelta(hours=3)))
    version_id = connection.execute(insert(text_versions).values(
        source_id=source_id, source_record_id=record_id, collection_event_id=event_id,
        version_key="synthetic-v1", text_content=content, retrieved_at=retrieved_at,
    ).returning(text_versions.c.id)).scalar_one()
    return dict(source_id=source_id, policy_id=policy_id, event_id=event_id, record_id=record_id,
                version_id=version_id, content=content, retrieved_at=retrieved_at)


@pytest.fixture
def graph(connection):
    return add_graph(connection)


def expect_integrity(connection, statement, sqlstate):
    with pytest.raises(IntegrityError) as error:
        with connection.begin_nested():
            connection.execute(statement)
    assert error.value.orig.sqlstate == sqlstate


def test_initial_migration_revision_idempotence_and_metadata(connection):
    assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == INITIAL_REVISION
    command.upgrade(migration_config(connection), "head")
    command.check(migration_config(connection, "check"))
    assert inspect_migration_state(connection, "hissiyat_test") == INITIAL_REVISION


def test_real_driver_destination_uses_published_endpoint_not_container_port(connection):
    settings = migration_settings("test")
    validate_connection_target(connection, settings)
    info = connection.connection.driver_connection.info
    assert (info.host, info.hostaddr, info.port, info.dbname) == (
        "127.0.0.1", "127.0.0.1", 55432, "hissiyat_test",
    )
    assert connection.execute(text("SELECT current_database()")).scalar_one() == "hissiyat_test"
    # The server's internal listening port is not the client's Docker-published endpoint.
    assert connection.execute(text("SELECT current_setting('port')")).scalar_one() == "5432"


def test_expected_tables_constraints_and_indexes(connection):
    inspector = inspect(connection)
    assert set(inspector.get_table_names(schema="public")) == set(metadata.tables) | {"alembic_version"}
    for table in metadata.tables.values():
        assert inspector.get_pk_constraint(table.name)["name"] == table.primary_key.name
        expected_checks = {item.name for item in table.constraints if item.__class__.__name__ == "CheckConstraint"}
        assert {item["name"] for item in inspector.get_check_constraints(table.name)} == expected_checks
        expected_unique = {item.name for item in table.constraints if item.__class__.__name__ == "UniqueConstraint"}
        assert {item["name"] for item in inspector.get_unique_constraints(table.name)} == expected_unique
        assert {item["name"] for item in inspector.get_foreign_keys(table.name)} == {item.name for item in table.foreign_key_constraints}
        indexes = {item["name"] for item in inspector.get_indexes(table.name)}
        assert {item.name for item in table.indexes} <= indexes


def test_valid_synthetic_rows_preserve_provenance_unicode_and_unknown_retention(connection, graph):
    row = connection.execute(select(
        text_versions.c.text_content, text_versions.c.retention_until,
        source_policies.c.usage_status, collection_events.c.status, data_sources.c.source_key,
    ).select_from(text_versions.join(source_records,
        text_versions.c.source_record_id == source_records.c.id).join(collection_events,
        text_versions.c.collection_event_id == collection_events.c.id).join(source_policies,
        collection_events.c.policy_id == source_policies.c.id).join(data_sources,
        source_records.c.source_id == data_sources.c.id))).one()
    assert row.text_content == graph["content"]
    assert row.retention_until is None
    assert row.usage_status == "unverified"
    assert row.status == "completed" and row.source_key.startswith("synthetic-")


def test_missing_publication_timestamp_is_preserved(connection, graph):
    assert connection.execute(select(source_records.c.published_at)).scalar_one() is None


def test_timezone_aware_instants_are_preserved(connection, graph):
    retrieved = connection.execute(select(text_versions.c.retrieved_at)).scalar_one()
    assert retrieved.tzinfo is not None
    assert retrieved == graph["retrieved_at"]
    assert retrieved.astimezone(timezone.utc).hour == 12


def test_publication_and_retrieval_instants_remain_distinct(connection, graph):
    published = datetime(2026, 1, 1, 8, tzinfo=timezone.utc)
    connection.execute(update(source_records).values(published_at=published))
    stored = connection.execute(select(source_records.c.published_at)).scalar_one()
    retrieved = connection.execute(select(text_versions.c.retrieved_at)).scalar_one()
    assert stored.tzinfo is not None and stored == published
    assert retrieved - stored == timedelta(days=1, hours=4)


@pytest.mark.parametrize("table,id_key,column", [
    (source_policies, "policy_id", "source_id"),
    (collection_events, "event_id", "policy_id"),
    (source_records, "record_id", "first_collection_event_id"),
    (text_versions, "version_id", "source_record_id"),
    (text_versions, "version_id", "collection_event_id"),
])
def test_missing_foreign_keys_are_rejected(connection, graph, table, id_key, column):
    expect_integrity(connection, update(table).where(table.c.id == graph[id_key]).values(**{column: uuid4()}), "23503")


@pytest.mark.parametrize("relationship", ["event_policy", "record_event", "version_record", "version_event"])
def test_cross_source_relationships_are_rejected(connection, graph, relationship):
    other = add_graph(connection)
    if relationship == "event_policy":
        statement = insert(collection_events).values(source_id=other["source_id"], policy_id=graph["policy_id"],
            method="file_import", occurred_at=graph["retrieved_at"], source_reference="urn:synthetic:export")
    elif relationship == "record_event":
        statement = insert(source_records).values(source_id=other["source_id"], source_record_id="synthetic-other",
            first_collection_event_id=graph["event_id"])
    else:
        statement = insert(text_versions).values(
            source_id=other["source_id"] if relationship == "version_record" else graph["source_id"],
            source_record_id=graph["record_id"], collection_event_id=other["event_id"],
            version_key="synthetic-other", text_content="Entirely synthetic.", retrieved_at=graph["retrieved_at"],
        )
    expect_integrity(connection, statement, "23503")


def test_duplicate_source_record_identifier_is_rejected(connection, graph):
    expect_integrity(connection, insert(source_records).values(
        source_id=graph["source_id"], source_record_id="synthetic-record-001",
        first_collection_event_id=graph["event_id"],
    ), "23505")


def test_same_external_identifier_is_allowed_for_different_sources(connection, graph):
    other = add_graph(connection)
    assert other["record_id"] != graph["record_id"]
    assert len(connection.execute(select(source_records.c.id)).all()) == 2


def test_duplicate_version_key_within_record_is_rejected(connection, graph):
    expect_integrity(connection, insert(text_versions).values(
        source_id=graph["source_id"], source_record_id=graph["record_id"], collection_event_id=graph["event_id"],
        version_key="synthetic-v1", text_content="Entirely synthetic.", retrieved_at=graph["retrieved_at"],
    ), "23505")


def test_retrieval_versions_share_one_source_record(connection, graph):
    connection.execute(insert(text_versions).values(
        source_id=graph["source_id"], source_record_id=graph["record_id"], collection_event_id=graph["event_id"],
        version_key="synthetic-v2", content_reference="urn:synthetic:permitted-content",
        retrieved_at=graph["retrieved_at"] + timedelta(days=1),
    ))
    assert len(connection.execute(select(source_records.c.id)).all()) == 1
    assert len(connection.execute(select(text_versions.c.id)).all()) == 2


@pytest.mark.parametrize("status", ["unknown", "unverified", "denied"])
def test_policy_state_does_not_become_approved(connection, graph, status):
    connection.execute(update(source_policies).values(usage_status=status))
    assert connection.execute(select(source_policies.c.usage_status)).scalar_one() == status


def test_missing_policy_status_defaults_to_unknown(connection):
    source_id = add_source(connection)
    connection.execute(insert(source_policies).values(source_id=source_id, policy_reference="urn:synthetic:unknown-policy"))
    assert connection.execute(select(source_policies.c.usage_status)).scalar_one() == "unknown"


@pytest.mark.parametrize("status", ["planned", "in_progress", "completed", "partial", "failed"])
def test_collection_status_is_preserved(connection, graph, status):
    connection.execute(update(collection_events).values(status=status))
    assert connection.execute(select(collection_events.c.status)).scalar_one() == status


@pytest.mark.parametrize("table,values", [
    (source_policies, {"usage_status": "public_means_allowed"}),
    (source_policies, {"usage_status": "approved"}),
    (source_policies, {"policy_reference": " \t"}),
    (collection_events, {"method": "unapproved_method"}),
    (collection_events, {"status": "unapproved_status"}),
    (source_records, {"record_id_origin": "local"}),
    (source_records, {"record_id_origin": "other"}),
    (text_versions, {"text_content": None}),
    (text_versions, {"content_reference": "urn:synthetic:content"}),
    (text_versions, {"text_content": " \t\n"}),
    (text_versions, {"content_kind": "normalized"}),
    (text_versions, {"version_key": ""}),
])
def test_invalid_status_identifiers_and_content_are_rejected(connection, graph, table, values):
    expect_integrity(connection, update(table).values(**values), "23514")


def test_documented_local_identifier_and_normalized_content_metadata(connection, graph):
    connection.execute(update(source_records).values(record_id_origin="local", local_id_method="Synthetic export ID plus row number."))
    connection.execute(update(text_versions).values(content_kind="normalized", transformation_reference="urn:synthetic:transformation"))
    assert connection.execute(select(source_records.c.record_id_origin)).scalar_one() == "local"
    assert connection.execute(select(text_versions.c.content_kind)).scalar_one() == "normalized"


def test_guard_rejects_unexpected_schema_objects_without_removing_them(connection):
    connection.execute(text("CREATE VIEW synthetic_unexpected_guard AS SELECT 1 AS value"))
    with pytest.raises(CommandError, match="Unexpected"):
        command.upgrade(migration_config(connection), "head")
    assert connection.execute(text("SELECT value FROM synthetic_unexpected_guard")).scalar_one() == 1


def test_guard_rejects_unknown_revision_without_stamping(connection):
    connection.execute(text("UPDATE alembic_version SET version_num='synthetic_unknown_revision'"))
    with pytest.raises(CommandError, match="Unexpected migration history"):
        command.upgrade(migration_config(connection), "head")


def test_guard_rejects_unrelated_user_schema(connection):
    connection.execute(text("CREATE SCHEMA pgsynthetic_unexpected"))
    with pytest.raises(CommandError, match="Unexpected schema objects"):
        command.upgrade(migration_config(connection), "head")


def test_live_database_identity_must_match_selected_target(connection):
    with pytest.raises(MigrationSafetyError, match="does not match"):
        inspect_migration_state(connection, "hissiyat_dev")
