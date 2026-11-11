"""Real supplied connections; native SQL logs captured without raw text output."""

import json
import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import event, func, select

from app.core.database import Database
from app.core.migrations import BACKEND_ROOT, inspect_migration_state, migration_settings
from app.core.schema import metadata
from app.ingestion.service import import_synthetic_batch

pytestmark = pytest.mark.integration


@pytest.fixture
def supplied(caplog):
    # Set INFO before Connection construction, as with an externally configured
    # application; changing only logger level on an old connection is insufficient.
    caplog.set_level(logging.INFO, logger="sqlalchemy.engine.Engine")
    settings = migration_settings("test")
    database = Database(settings)
    try:
        with database.connection() as connection:
            with connection.begin() as outer:
                try:
                    inspect_migration_state(connection, "hissiyat_test")
                    config = Config(str(BACKEND_ROOT / "alembic.ini"))
                    config.attributes.update(connection=connection, target="test", operation="upgrade")
                    command.upgrade(config, "head")
                    yield connection, settings
                finally:
                    if outer.is_active:
                        outer.rollback()
    finally:
        database.close()


def fixture_input():
    batch = json.loads((Path(__file__).parents[1] / "fixtures/synthetic_imports.json").read_text(encoding="utf-8"))["batches"]["base"]
    # An approved harmless sentence acts as the sentinel. Substituting unrelated
    # text would only test fingerprint rejection, not the logging guard.
    return json.dumps(batch, ensure_ascii=False).encode(), batch["records"][0]["record"]["text"]


def counts(connection):
    return {name: connection.execute(select(func.count()).select_from(table)).scalar_one()
            for name, table in metadata.tables.items()}


def test_safe_info_logging_masks_parameters_and_preserves_success(supplied, caplog):
    connection, settings = supplied
    payload, sentinel = fixture_input()
    caplog.clear()
    result = import_synthetic_batch(connection, settings, payload)
    assert result.status == "applied" and result.counts["accepted"] == 2
    assert "INSERT INTO public.text_versions" in caplog.text
    assert "SQL parameters hidden" in caplog.text
    assert sentinel not in caplog.text
    assert import_synthetic_batch(connection, settings, payload).counts["duplicate"] == 2


@pytest.mark.parametrize("unsafe", ["parameters_off", "parameters_unknown", "echo", "debug_echo", "external_debug"])
def test_unsafe_supplied_logging_is_rejected_before_any_sql(supplied, caplog, unsafe):
    connection, settings = supplied
    payload, sentinel = fixture_input()
    engine = connection.engine
    original_hide = engine.hide_parameters
    original_echo = engine.echo
    original_level = logging.getLogger("sqlalchemy.engine.Engine").level
    original_handlers = logging.getLogger("sqlalchemy.engine.Engine").handlers[:]
    before = counts(connection)
    executed = []

    def observe(*args):
        executed.append(True)

    try:
        if unsafe == "parameters_off":
            engine.hide_parameters = False
        elif unsafe == "parameters_unknown":
            engine.hide_parameters = None
        elif unsafe == "echo":
            engine.echo = True
        elif unsafe == "debug_echo":
            engine.echo = "debug"
        else:
            caplog.set_level(logging.DEBUG, logger="sqlalchemy.engine.Engine")
        caplog.clear()
        event.listen(connection, "before_cursor_execute", observe)
        try:
            result = import_synthetic_batch(connection, settings, payload)
        finally:
            event.remove(connection, "before_cursor_execute", observe)
        assert (result.status, result.code) == ("rejected", "unsafe_connection_logging")
        assert not executed and sentinel not in caplog.text
        assert result.fixture_fingerprint is None
        # The service must not silently repair a caller-owned logging setting.
        if unsafe == "parameters_off":
            assert engine.hide_parameters is False
        if unsafe == "external_debug":
            assert logging.getLogger("sqlalchemy.engine.Engine").level == logging.DEBUG
    finally:
        engine.hide_parameters = original_hide
        engine.echo = original_echo
        logging.getLogger("sqlalchemy.engine.Engine").setLevel(original_level)
        logging.getLogger("sqlalchemy.engine.Engine").handlers = original_handlers
    assert counts(connection) == before and all(v == 0 for v in before.values())
