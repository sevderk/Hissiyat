from copy import deepcopy
import json
import logging
from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient
import pytest

from app.core.config import Settings
from app.main import create_app
from app.trends_preview import single_graph

SCOPE = {
    "source": "google_trends", "mode": "topic", "query": "career",
    "start_date": "2026-09-01", "end_date": "2026-10-01", "geography": "TR", "language": None,
}
CONTRACT = {
    "geography": "geo", "cadence": "granularity", "date": "date", "value": "value", "status": "valueStatus",
    "statuses": {"fixture-observed": "observed", "fixture-missing": "missing", "fixture-suppressed": "suppressed"},
    "measurement": "consistently_scaled_search_interest", "display": "local_summary",
}
KEY = "fictional-transport-secret"
ENDPOINT = "/api/v1/local/research"
HEADERS = {"X-Hissiyat-Local-Research": "1"}
FIXTURE = {"lines": [{"term": "career", "geo": "TR", "granularity": "weekly", "points": [
    {"date": "2026-09-07", "value": 213.625, "valueStatus": "fixture-observed"},
    {"date": "2026-09-14", "value": 0, "valueStatus": "fixture-observed"},
    {"date": "2026-09-21", "value": None, "valueStatus": "fixture-missing"},
    {"date": "2026-09-28", "value": None, "valueStatus": "fixture-suppressed"},
    {"date": "2026-10-05", "value": 447.125, "valueStatus": "fixture-observed"},
]}], "private": "fictional-unfiltered-content"}


def client(**overrides):
    options = dict(environment="development", local_research="1", database_user=None, database_password=None,
                   google_trends_api_key=KEY, google_trends_approved_request=json.dumps(SCOPE))
    settings = Settings(_env_file=None, **{**options, **overrides})
    return TestClient(create_app(settings), base_url="http://127.0.0.1:8059", client=("127.0.0.1", 50000))


@pytest.fixture
def graph(monkeypatch):
    request = MagicMock(return_value=(deepcopy(FIXTURE), {"http_status": 200, "query_attempted": True}))
    monkeypatch.setattr("app.trends_preview.single_graph", request)
    return request


def test_exact_single_use_scope_returns_only_safe_shape(graph):
    with client() as local:
        assert local.post(ENDPOINT, headers=HEADERS, json={**SCOPE, "geography": "US"}).status_code == 403
        assert local.post(ENDPOINT, headers={**HEADERS, "Origin": "https://example.invalid"}, json=SCOPE).status_code == 404
        graph.assert_not_called()
        result = local.post(ENDPOINT, headers=HEADERS, json=SCOPE)
        assert result.status_code == 200 and result.headers["cache-control"] == "no-store"
        parsed = result.json()
        assert parsed["summary"] is None and parsed["measurement"] is None
        assert parsed["point_count"] == 5 and parsed["date_kind"] == "string" and parsed["value_kind"] == "decimal"
        assert parsed["metadata_fields"] == ["geo", "granularity", "valueStatus"]
        assert local.post(ENDPOINT, headers=HEADERS, json=SCOPE).status_code == 403
    graph.assert_called_once_with(KEY, terms="career", restrictions_geo="TR",
                                  restrictions_startDate="2026-09", restrictions_endDate="2026-10")
    for canary in (KEY, "fictional-unfiltered-content", "213.625", "447.125", '"points"', "2026-10-05"):
        assert canary not in result.text


@pytest.mark.parametrize("changes", [
    {"start_date": "2026-09-02"}, {"end_date": "2026-11-01"}, {"start_date": "2024-10-01"},
    {"geography": None}, {"geography": "TR-06"}, {"query": "career,education"}, {"query": "/m/example"},
    {"language": "en"}, {"api_key": "fictional"}, {"restrictions_property": "news"}, {"analyze_discussion": True},
])
def test_declines_out_of_scope_dates_geographies_keys_and_overrides(graph, changes):
    with client() as local:
        assert local.post(ENDPOINT, headers=HEADERS, json={**SCOPE, **changes}).status_code == 400
    graph.assert_not_called()


@pytest.mark.parametrize("changes, status", [
    ({"environment": "production"}, 404), ({"local_research": "0"}, 404),
    ({"google_trends_approved_request": None}, 403), ({"google_trends_api_key": None}, 503),
    ({"google_trends_summary_contract": '{"display":"unrestricted"}'}, 503),
])
def test_production_and_unconfigured_requests_never_send(graph, changes, status):
    with client(**changes) as local:
        assert local.post(ENDPOINT, headers=HEADERS, json=SCOPE).status_code == status
    graph.assert_not_called()


def test_verified_contract_discloses_summary_and_keeps_ambiguous_zeros_separate(graph):
    event_scope = {**SCOPE, "mode": "event"}
    with client(google_trends_approved_request=json.dumps(event_scope),
                google_trends_summary_contract=json.dumps(CONTRACT)) as local:
        result = local.post(ENDPOINT, headers=HEADERS, json=event_scope)
    assert result.status_code == 200
    assert result.json()["mode"] == "event"
    assert result.json()["measurement"] == "consistently_scaled_search_interest"
    assert result.json()["summary"] == {
        "geography": "TR", "cadence": "weekly", "first_period": "2026-09-07", "last_period": "2026-10-05",
        "nonzero": 2, "ambiguous_zero": 1, "missing": 1, "suppressed": 1,
        "peak_period": "2026-10-05", "peak_ties": 1, "direction": "increased",
    }
    for canary in (KEY, "fictional-unfiltered-content", "213.625", "447.125", '"points"'):
        assert canary not in result.text


def test_invalid_geography_and_provider_failure_consume_approval(graph):
    payload = deepcopy(FIXTURE)
    payload["lines"][0]["geo"] = "GB"
    graph.return_value = payload, {"http_status": 200}
    with client(google_trends_summary_contract=json.dumps(CONTRACT)) as local:
        assert local.post(ENDPOINT, headers=HEADERS, json=SCOPE).json() == {"code": "invalid_response", "upstream_status": 200}
        assert local.post(ENDPOINT, headers=HEADERS, json=SCOPE).status_code == 403
    graph.assert_called_once()
    graph.reset_mock()
    graph.return_value = None, {"stage": "request", "reason": "request_construction_failed", "http_status": None}
    with client() as local:
        assert local.post(ENDPOINT, headers=HEADERS, json=SCOPE).json() == {"code": "trends_contract_error"}
        assert local.post(ENDPOINT, headers=HEADERS, json=SCOPE).status_code == 403
    graph.assert_called_once()


def test_installed_sdk_uses_exact_guide_arguments_with_fictional_discovery(monkeypatch, caplog):
    pytest.importorskip("googleapiclient.discovery")
    import requests

    params = ("terms", "restrictions_geo", "restrictions_startDate", "restrictions_endDate")
    document = {
        "name": "trends", "version": "v1beta", "rootUrl": "https://trends.googleapis.com:443/", "servicePath": "",
        "schemas": {}, "parameters": {"key": {"type": "string", "location": "query"}},
        "methods": {"getGraph": {"id": "trends.getGraph", "path": "v1beta/fixture-graph", "httpMethod": "GET",
                                 "parameters": {name: {"type": "string", "location": "query", "required": True}
                                                for name in params}}},
    }
    sent = []
    def respond(method, url, **options):
        assert options["allow_redirects"] is False
        logging.getLogger("urllib3.connectionpool").warning("fixture URL %s", url)
        sent.append((method, url))
        wrapper = MagicMock()
        response = wrapper.__enter__.return_value
        response.status_code = 200
        response.headers = {"Content-Type": "application/json"}
        response.iter_content.return_value = iter([json.dumps(document if len(sent) == 1 else FIXTURE).encode()])
        return wrapper
    session = MagicMock()
    session.__enter__.return_value = session
    session.request.side_effect = respond
    monkeypatch.setattr(requests, "Session", lambda: session)
    with caplog.at_level(logging.DEBUG):
        payload, report = single_graph(KEY, **dict(zip(params, ("career", "TR", "2026-09", "2026-10"))))
    assert payload == FIXTURE and report["query_attempted"]
    assert len(sent) == 2 and sent[1][0] == "GET"
    query = parse_qs(urlsplit(sent[1][1]).query)
    assert {name: query[name][0] for name in params} == dict(zip(params, ("career", "TR", "2026-09", "2026-10")))
    assert session.mount.call_args.args[1].max_retries.total == 0
    assert KEY not in caplog.text and "fixture-graph" not in caplog.text
