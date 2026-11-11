"""Validation and authorization tests use only synthetic payloads and no SQL."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import logging
from unittest.mock import MagicMock

import pytest

from app.core.config import Settings
from app.ingestion import service
from app.ingestion.contracts import TextImportBatch
from app.ingestion.service import MAX_INPUT_BYTES, import_synthetic_batch
from app.ingestion.synthetic_catalog import APPROVED_FIXTURES


@pytest.fixture
def batches():
    return json.loads((Path(__file__).parents[1] / "fixtures/synthetic_imports.json").read_text(encoding="utf-8"))["batches"]


def encode(payload):
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def test_closed_catalog_matches_complete_unmasked_synthetic_inputs(batches):
    assert len(batches) == len(APPROVED_FIXTURES) == 7
    for payload in batches.values():
        TextImportBatch.model_validate(payload)
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        assert hashlib.sha256(canonical.encode()).hexdigest() == APPROVED_FIXTURES[payload["fixture_id"]]
    with pytest.raises(TypeError):
        APPROVED_FIXTURES["unreviewed"] = "unreviewed"


@pytest.mark.parametrize("mutation", [
    "invalid_timestamp", "missing_source", "invalid_event", "mixed_event", "unknown_version",
    "missing_version_key", "empty_records", "unknown_field", "invalid_method", "record_limit",
])
def test_invalid_envelopes_reject_the_whole_batch_without_sql(batches, mutation):
    payload = deepcopy(batches["base"])
    record = payload["records"][0]["record"]
    if mutation == "invalid_timestamp":
        record["retrieved_at"] = "SYNTHETIC_PRIVATE_TIMESTAMP_CANARY"
    elif mutation == "missing_source":
        del record["collection"]["source_policy"]["source_id"]
    elif mutation == "invalid_event":
        for entry in payload["records"]:
            entry["record"]["collection"]["collection_id"] = "not-a-uuid"
    elif mutation == "mixed_event":
        record["collection"]["source_reference"] = "urn:synthetic:different-event"
    elif mutation == "unknown_version":
        payload["format_version"] = "hissiyat.text-import.v999"
    elif mutation == "missing_version_key":
        del payload["records"][0]["version_key"]
    elif mutation == "empty_records":
        payload["records"] = []
    elif mutation == "unknown_field":
        record["SYNTHETIC_PRIVATE_UNKNOWN_KEY"] = "synthetic-only"
    elif mutation == "record_limit":
        payload["records"] = [payload["records"][0]] * 51
    else:
        for entry in payload["records"]:
            entry["record"]["collection"]["method"] = "api"
    connection = MagicMock()
    result = import_synthetic_batch(connection, Settings(_env_file=None), encode(payload))
    assert (result.status, result.code) == ("rejected", "invalid_input")
    assert result.counts["accepted"] == 0
    if mutation == "record_limit":
        assert result.rows == ()
    assert "SYNTHETIC_PRIVATE" not in result.model_dump_json()
    assert not connection.mock_calls


@pytest.mark.parametrize("payload", [
    b"{", b"[]", b"null", b"{}", b"\xff", b'{"records":[],"records":[]}',
    b'{"value":NaN}', b"x" * (MAX_INPUT_BYTES + 1), "not-bytes",
], ids=["malformed", "list", "null", "empty", "encoding", "duplicate-key", "nonfinite", "oversize", "not-bytes"])
def test_malformed_or_unsupported_input_is_safe(payload):
    connection = MagicMock()
    result = import_synthetic_batch(connection, Settings(_env_file=None), payload)
    assert (result.status, result.code) == ("rejected", "invalid_input")
    assert not connection.mock_calls


@pytest.mark.parametrize("mutation", ["text", "source", "approved", "synthetic_flag", "fixture_id"])
def test_claims_and_reused_fixture_ids_cannot_authorize_other_content(batches, mutation, caplog):
    payload = deepcopy(batches["base"])
    if mutation == "text":
        payload["records"][0]["record"]["text"] = "SYNTHETIC_UNAUTHORIZED_CONTENT_CANARY"
    elif mutation == "source":
        for entry in payload["records"]:
            entry["record"]["collection"]["source_policy"]["source_id"] = "unverified-external-candidate"
    elif mutation == "approved":
        for entry in payload["records"]:
            entry["record"]["collection"]["source_policy"].update(
                usage_status="approved", decision_reference="urn:synthetic:untrusted-assertion",
            )
    elif mutation == "synthetic_flag":
        payload["synthetic"] = True
    else:
        payload["fixture_id"] = "unreviewed"
    connection = MagicMock()
    result = import_synthetic_batch(connection, Settings(_env_file=None), encode(payload))
    assert result.status == "rejected"
    assert result.code == ("invalid_input" if mutation == "synthetic_flag" else "synthetic_authorization_required")
    assert not connection.mock_calls
    assert "SYNTHETIC_UNAUTHORIZED_CONTENT_CANARY" not in caplog.text + result.model_dump_json()


@pytest.mark.parametrize("environment,database", [("production", "hissiyat_test"), ("development", "hissiyat_dev")])
def test_synthetic_path_cannot_activate_for_other_environments(batches, environment, database):
    settings = Settings(_env_file=None, environment=environment, database_name=database,
                        database_user="synthetic", database_password="synthetic-only")
    connection = MagicMock()
    result = import_synthetic_batch(connection, settings, encode(batches["base"]))
    assert (result.status, result.code) == ("rejected", "unsafe_target_or_schema")
    assert not connection.mock_calls


@pytest.mark.parametrize("kind", ["validated_model", "unvalidated_model", "mutable_bytes", "mutable_dict"])
def test_internal_boundary_cannot_trust_caller_models_or_mutable_inputs(batches, kind):
    payload = deepcopy(batches["base"])
    payload["records"][0]["record"]["text"] = "SYNTHETIC_MODIFIED_MODEL_SENTINEL"
    attempted = {
        "validated_model": lambda: TextImportBatch.model_validate(payload),
        "unvalidated_model": lambda: TextImportBatch.model_construct(**payload),
        "mutable_bytes": lambda: bytearray(encode(payload)),
        "mutable_dict": lambda: payload,
    }[kind]()
    connection = MagicMock()
    result = service._apply_batch(connection, attempted)
    assert (result.status, result.code) == ("rejected", "invalid_input")
    assert result.fixture_fingerprint is None and not connection.mock_calls


@pytest.mark.parametrize("claim", ["approved", "authorized", "fixture_fingerprint"])
def test_caller_forged_envelope_claims_never_authorize_writes(batches, claim):
    payload = deepcopy(batches["base"])
    payload[claim] = APPROVED_FIXTURES[payload["fixture_id"]] if claim == "fixture_fingerprint" else True
    connection = MagicMock()
    result = service._apply_batch(connection, encode(payload))
    assert (result.status, result.code) == ("rejected", "invalid_input")
    assert result.fixture_fingerprint is None and not connection.mock_calls


def test_approved_raw_bytes_without_explicit_settings_fail_closed(batches):
    connection = MagicMock()
    result = service._apply_batch(connection, encode(batches["base"]))
    assert (result.status, result.code) == ("rejected", "unsafe_target_or_schema")
    assert not connection.mock_calls


@pytest.mark.parametrize("field,value", [
    ("database_host", "192.0.2.1"), ("database_port", 54322), ("database_name", "hissiyat_dev"),
])
def test_internal_boundary_preserves_exact_test_target_restrictions(batches, field, value):
    values = dict(_env_file=None, environment="test", database_name="hissiyat_test",
                  database_user="synthetic", database_password="synthetic-only")
    values[field] = value
    connection = MagicMock()
    result = service._apply_batch(connection, encode(batches["base"]), settings=Settings(**values))
    assert (result.status, result.code) == ("rejected", "unsafe_target_or_schema")
    assert not connection.mock_calls


@pytest.mark.parametrize("field,value", [
    ("hide_parameters", False), ("hide_parameters", None), ("hide_parameters", 1),
    ("hide_parameters", "true"), ("echo", True), ("echo", "debug"),
    ("echo", None), ("echo", 0), ("logger", None),
])
def test_logging_safety_requires_explicit_supported_values(field, value):
    from sqlalchemy import Connection, Engine

    connection = MagicMock(spec=Connection)
    engine = MagicMock(spec=Engine)
    engine.hide_parameters = True
    engine.echo = False
    engine.logger = logging.getLogger("hissiyat.synthetic.unit.sql")
    old_level = engine.logger.level
    engine.logger.setLevel(logging.INFO)
    connection.engine = engine
    try:
        setattr(engine, field, value)
        with pytest.raises(service._UnsafeConnectionLogging):
            service._validate_connection_logging(connection)
        connection.execute.assert_not_called()
    finally:
        logging.getLogger("hissiyat.synthetic.unit.sql").setLevel(old_level)


def test_unknown_logging_metadata_is_rejected_without_exposing_details(batches, monkeypatch):
    from sqlalchemy import Connection, Engine
    from unittest.mock import PropertyMock, patch

    connection = MagicMock(spec=Connection)
    engine = MagicMock(spec=Engine)
    connection.engine = engine
    sentinel = "SYNTHETIC_CONNECTION_METADATA_SENTINEL"
    monkeypatch.setattr(service, "validate_connection_target", lambda *args: None)
    settings = Settings(_env_file=None, environment="test", database_name="hissiyat_test",
                        database_user="synthetic", database_password="synthetic-only")
    with patch.object(type(engine), "hide_parameters", new_callable=PropertyMock, create=True) as attribute:
        attribute.side_effect = RuntimeError(sentinel)
        result = import_synthetic_batch(connection, settings, encode(batches["base"]))
    assert (result.status, result.code) == ("rejected", "unsafe_connection_logging")
    assert sentinel not in result.model_dump_json()
    connection.execute.assert_not_called()
    connection.begin_nested.assert_not_called()
