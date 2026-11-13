from datetime import date
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.v1.demo import INTEREST_FIXTURE, TEXT_FIXTURES, InterestPoint, SearchInterest, TextAnalysis
from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def client():
    with patch("app.main.Database", side_effect=AssertionError("Demo must not initialize a database")):
        with TestClient(create_app(Settings(_env_file=None, environment="test"))) as demo_client:
            yield demo_client


def test_demo_fixtures_are_fixed_and_distinct(client):
    path = "/api/v1/demo/text-analysis"
    general = client.get(path)
    enriched = client.get(path, params={"cohort": "uncertainty-enriched"})
    assert general.status_code == enriched.status_code == 200
    assert general.json() == client.get(path, params={"cohort": "general"}).json()
    for response, cohort, total in ((general, "general", 240), (enriched, "uncertainty-enriched", 126)):
        data = TextAnalysis.model_validate(response.json())
        assert data.demo and data.contract_version == "1.0"
        assert data.cohort == cohort and data.document_count == total
        assert data.multi_label and data.emotion_basis == "explicit_expression"
        assert sum(item.count for item in data.groups["topics"]) > total
    assert all(general.json()["groups"][group] != enriched.json()["groups"][group]
               for group in general.json()["groups"])


def test_search_interest_is_independent_and_preserves_gaps(client):
    path = "/api/v1/demo/search-interest"
    before = client.get(path)
    client.get("/api/v1/demo/text-analysis", params={"cohort": "uncertainty-enriched"})
    assert before.status_code == 200 and before.json() == client.get(path).json()
    data = SearchInterest.model_validate(before.json())
    assert data.demo and data.scale == (0, 100)
    assert len(data.points) == 12
    assert [(point.status, point.value) for point in data.points if point.status != "observed"] == [
        ("missing", None), ("suppressed", None),
    ]


@pytest.mark.parametrize("path", [
    "text-analysis?cohort=private-test-input",
    "text-analysis?cohort=general&cohort=general",
    "text-analysis?secret=private-test-input",
    "search-interest?cohort=general",
])
def test_invalid_query_is_rejected_without_echo(client, path):
    response = client.get("/api/v1/demo/" + path)
    assert response.status_code == 400
    assert "private-test-input" not in response.text


def test_demo_is_read_only_and_absent_in_production(client):
    path = "/api/v1/demo/text-analysis"
    assert client.post(path).status_code == 405
    with TestClient(create_app(Settings(_env_file=None, environment="production"))) as production:
        assert production.get(path).status_code == 404
        assert production.get("/api/v1/demo/search-interest").status_code == 404
        assert production.get("/api/v1/health").status_code == 200


def test_text_rejects_overcounts_wrong_groups_duplicates_and_private_fields():
    data = TEXT_FIXTURES["general"].model_dump(mode="json")
    groups = data["groups"]
    invalid_topics = (
        [{"key": "education", "count": 241}],
        [{"key": "hope", "count": 1}],
        [{"key": "education", "count": 1}, {"key": "education", "count": 2}],
        [{"key": "education", "count": 1, "private_text": "private-test-input"}],
    )
    for topics in invalid_topics:
        with pytest.raises(ValidationError) as error:
            TextAnalysis.model_validate({**data, "groups": {**groups, "topics": topics}})
        assert "private-test-input" not in str(error.value)
    with pytest.raises(ValidationError):
        TextAnalysis.model_validate({**data, "document_count": 0})
    assert TextAnalysis(cohort="general", document_count=0, groups=dict.fromkeys(groups, ())).document_count == 0


@pytest.mark.parametrize(("status", "value"), [
    ("missing", 0), ("suppressed", 0), ("observed", None), ("observed", 101), ("observed", False),
])
def test_search_rejects_inconsistent_point(status, value):
    with pytest.raises(ValidationError):
        InterestPoint(date=date(2025, 1, 6), status=status, value=value)


def test_search_contract_requires_ordered_calendar_but_allows_empty_and_zero():
    assert SearchInterest(points=()).points == ()
    zero = InterestPoint(date=date(2025, 1, 6), status="observed", value=0)
    assert SearchInterest(points=(zero,)).points[0].value == 0
    with pytest.raises(ValidationError):
        SearchInterest(points=(INTEREST_FIXTURE.points[1], zero))
    with pytest.raises(ValidationError):
        SearchInterest(points=(zero, INTEREST_FIXTURE.points[2]))
