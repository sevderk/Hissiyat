"""Exercise entirely synthetic inputs, never collected research content."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from pydantic import SecretStr, ValidationError
import pytest

from app.contracts import (
    CollectionMetadata,
    SourcePolicyReference,
    TextRecordInput,
    TrendObservationInput,
    TrendSeriesMetadata,
    validation_error_summary,
)


@pytest.fixture
def synthetic_inputs():
    path = Path(__file__).parents[1] / "fixtures/synthetic_contracts.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def text_input(synthetic_inputs):
    return {**synthetic_inputs["text_records"][0], "collection": synthetic_inputs["collection"]}


@pytest.fixture
def trend_input(synthetic_inputs):
    collection = deepcopy(synthetic_inputs["collection"])
    collection["collection_id"] = "synthetic-trend-import-001"
    collection["source_policy"]["source_id"] = "synthetic-trend-source"
    series = {**synthetic_inputs["trend_series"], "collection": collection}
    return {**synthetic_inputs["trend_observations"][0], "series": series}


@pytest.mark.parametrize("index,language", [(0, "en"), (1, "tr")])
def test_synthetic_text_preserves_unicode_and_provenance(synthetic_inputs, index, language):
    payload = {**synthetic_inputs["text_records"][index], "collection": synthetic_inputs["collection"]}
    record = TextRecordInput.model_validate_json(json.dumps(payload, ensure_ascii=False))

    assert record.language_code == language
    assert isinstance(record.text, SecretStr)
    assert record.text.get_secret_value() == payload["text"]
    assert record.collection.source_policy.source_id == "synthetic-text-source"
    assert record.collection.source_policy.policy_reference == "urn:synthetic:policy:unverified"
    assert record.collection.collection_id == "synthetic-import-001"
    assert record.source_record_id == payload["source_record_id"]
    assert payload["text"] not in repr(record)
    assert payload["text"] not in record.model_dump_json()


def test_missing_publication_time_is_not_replaced_by_retrieval(text_input):
    del text_input["published_at"]
    record = TextRecordInput.model_validate(text_input)

    assert record.published_at is None
    assert not record.has_publication_timestamp
    assert record.retrieved_at == datetime(2026, 1, 2, 12, tzinfo=timezone.utc)


def test_publication_and_retrieval_remain_distinct(text_input):
    record = TextRecordInput.model_validate(text_input)
    assert record.has_publication_timestamp
    assert record.retrieved_at - record.published_at == timedelta(days=1, hours=4)


def test_timestamp_order_compares_instants_with_offsets(text_input):
    text_input.update(published_at="2026-01-02T14:00:00+03:00", retrieved_at="2026-01-02T12:00:00Z")
    record = TextRecordInput.model_validate(text_input)
    assert record.published_at.utcoffset() == timedelta(hours=3)
    text_input["published_at"] = "2026-01-02T16:00:00+03:00"
    with pytest.raises(ValidationError):
        TextRecordInput.model_validate(text_input)


@pytest.mark.parametrize("field", ["published_at", "retrieved_at"])
@pytest.mark.parametrize("value", ["not-a-timestamp", "2026-02-30T10:00:00Z", "2026-01-01T10:00:00", "2026-01-01", 1767225600])
def test_invalid_or_ambiguous_text_timestamps_are_rejected(text_input, field, value):
    text_input[field] = value
    with pytest.raises(ValidationError):
        TextRecordInput.model_validate(text_input)


def test_undetermined_language_does_not_default_to_ui_locale(text_input):
    del text_input["language_code"]
    del text_input["language_method"]
    record = TextRecordInput.model_validate(text_input)
    assert (record.language_code, record.language_method) == ("und", "undetermined")


@pytest.mark.parametrize("code,method", [("English", "source"), ("", "human"), ("en", "undetermined")])
def test_invalid_language_metadata_is_rejected(text_input, code, method):
    text_input.update(language_code=code, language_method=method)
    with pytest.raises(ValidationError):
        TextRecordInput.model_validate(text_input)


def test_additional_language_tag_is_supported(text_input):
    text_input["language_code"] = "pt-BR"
    assert TextRecordInput.model_validate(text_input).language_code == "pt-BR"


@pytest.mark.parametrize("field", ["source_id", "policy_reference"])
@pytest.mark.parametrize("value", [None, "", " \t"])
def test_invalid_required_source_policy_reference(text_input, field, value):
    text_input["collection"]["source_policy"][field] = value
    with pytest.raises(ValidationError):
        TextRecordInput.model_validate(text_input)


def test_missing_source_policy_is_rejected(text_input):
    del text_input["collection"]["source_policy"]
    with pytest.raises(ValidationError):
        TextRecordInput.model_validate(text_input)


@pytest.mark.parametrize("field", ["source_record_id", "retrieved_at", "collection"])
def test_required_record_provenance_cannot_be_omitted(text_input, field):
    del text_input[field]
    with pytest.raises(ValidationError):
        TextRecordInput.model_validate(text_input)


def test_unknown_and_unverified_rights_are_preserved(text_input):
    record = TextRecordInput.model_validate(text_input)
    assert record.collection.source_policy.usage_status == "unverified"
    del text_input["collection"]["source_policy"]["usage_status"]
    assert TextRecordInput.model_validate(text_input).collection.source_policy.usage_status == "unknown"
    text_input["collection"]["source_policy"]["usage_status"] = "denied"
    assert TextRecordInput.model_validate(text_input).collection.source_policy.usage_status == "denied"


def test_claimed_approval_needs_decision_reference(synthetic_inputs):
    payload = {**synthetic_inputs["collection"]["source_policy"], "usage_status": "approved"}
    with pytest.raises(ValidationError):
        SourcePolicyReference.model_validate(payload)
    payload["decision_reference"] = "urn:synthetic:decision:never-real-permission"
    assert SourcePolicyReference.model_validate(payload).usage_status == "approved"


def test_local_identifier_requires_documented_fallback(text_input):
    text_input["record_id_origin"] = "local"
    with pytest.raises(ValidationError):
        TextRecordInput.model_validate(text_input)
    text_input["local_id_method"] = "Synthetic file identifier plus one-based row number."
    assert TextRecordInput.model_validate(text_input).record_id_origin == "local"


def test_content_reference_can_replace_inline_text(text_input):
    del text_input["text"]
    text_input["content_reference"] = "urn:synthetic:permitted-content:001"
    assert TextRecordInput.model_validate(text_input).text is None


@pytest.mark.parametrize("case", ["neither", "both", "blank_text", "blank_reference"])
def test_ambiguous_or_empty_content_is_rejected(text_input, case):
    if case == "neither":
        del text_input["text"]
    elif case == "both":
        text_input["content_reference"] = "urn:synthetic:content:001"
    elif case == "blank_text":
        text_input["text"] = " \n\t"
    else:
        del text_input["text"]
        text_input["content_reference"] = " "
    with pytest.raises(ValidationError):
        TextRecordInput.model_validate(text_input)


def test_collection_requires_aware_time_and_source_reference(synthetic_inputs):
    payload = synthetic_inputs["collection"]
    payload["occurred_at"] = "2026-01-03T12:00:00"
    payload["source_reference"] = " "
    with pytest.raises(ValidationError) as error:
        CollectionMetadata.model_validate(payload)
    assert len(error.value.errors()) == 2


def test_synthetic_trend_observation_keeps_measurement_context(trend_input):
    record = TrendObservationInput.model_validate(trend_input)
    assert record.value == 42
    assert record.series.series_id == "synthetic-trend-001"
    assert record.series.measurement_unit == "normalized_search_interest"
    assert record.series.collection.source_policy.usage_status == "unverified"
    assert record.data_reference == "urn:synthetic:trend-export:row:1"


@pytest.mark.parametrize("index,status", [(1, "missing"), (2, "suppressed")])
def test_missing_and_suppressed_are_not_zero(synthetic_inputs, trend_input, index, status):
    payload = {**synthetic_inputs["trend_observations"][index], "series": trend_input["series"]}
    record = TrendObservationInput.model_validate(payload)
    assert record.value is None
    assert record.value_status == status


def test_observed_zero_remains_a_value(trend_input):
    trend_input["value"] = 0
    assert TrendObservationInput.model_validate(trend_input).value == 0


@pytest.mark.parametrize("status,value", [("observed", None), ("missing", 0), ("suppressed", 42)])
def test_value_status_must_match_presence(trend_input, status, value):
    trend_input.update(value_status=status, value=value)
    with pytest.raises(ValidationError):
        TrendObservationInput.model_validate(trend_input)


@pytest.mark.parametrize("value", [-1, 101, float("nan"), float("inf"), True, "42"])
def test_invalid_values_under_source_declared_scale(trend_input, value):
    trend_input["value"] = value
    with pytest.raises(ValidationError):
        TrendObservationInput.model_validate(trend_input)


def test_universal_model_does_not_assume_zero_to_one_hundred(trend_input):
    trend_input["series"].update(scale_min=-1000, scale_max=1000, measurement_unit="synthetic_custom_index")
    trend_input["value"] = 500
    assert TrendObservationInput.model_validate(trend_input).value == 500
    trend_input["series"].update(scale_min=None, scale_max=None)
    trend_input["value"] = -2500
    assert TrendObservationInput.model_validate(trend_input).value == -2500


def test_inverted_scale_is_rejected(trend_input):
    trend_input["series"].update(scale_min=100, scale_max=0)
    with pytest.raises(ValidationError):
        TrendSeriesMetadata.model_validate(trend_input["series"])


@pytest.mark.parametrize("end", ["2026-01-01T00:00:00Z", "2025-12-31T23:00:00Z", "invalid", "2026-01-02T00:00:00"])
def test_invalid_trend_interval(trend_input, end):
    trend_input["interval_end"] = end
    with pytest.raises(ValidationError):
        TrendObservationInput.model_validate(trend_input)


def test_trend_requires_data_reference(trend_input):
    del trend_input["data_reference"]
    with pytest.raises(ValidationError):
        TrendObservationInput.model_validate(trend_input)


def test_text_and_trend_contracts_reject_mixed_fields(text_input, trend_input):
    text_input["value"] = 42
    trend_input["text"] = "Entirely synthetic mixed-field canary."
    for model, payload in [(TextRecordInput, text_input), (TrendObservationInput, trend_input)]:
        with pytest.raises(ValidationError):
            model.model_validate(payload)


def test_validation_logging_summary_excludes_raw_content_and_unknown_keys(text_input, caplog):
    import logging

    canary = "SYNTHETIC_PRIVATE_CONTENT_CANARY_ğüşİ"
    text_input.update(text=canary, published_at="invalid")
    text_input[canary] = canary
    with pytest.raises(ValidationError) as error:
        TextRecordInput.model_validate(text_input)
    summary = validation_error_summary(error.value)
    logging.getLogger(__name__).warning("Invalid contract: %s", summary)
    assert sum(summary.values()) == 2
    assert canary not in caplog.text
    assert canary not in json.dumps(summary)


def test_standard_error_string_hides_invalid_content(text_input):
    canary = "SYNTHETIC_PRIVATE_TIMESTAMP_CANARY"
    text_input["published_at"] = canary
    with pytest.raises(ValidationError) as error:
        TextRecordInput.model_validate(text_input)
    assert canary not in str(error.value)
