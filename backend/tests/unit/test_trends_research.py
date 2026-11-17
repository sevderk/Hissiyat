from copy import deepcopy
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient
import pytest

from app.core.config import Settings
from app.core.trends_research import DocumentedFields, GraphError, adapt_graph
from app.main import create_app
from app.trends_preview import SingleSend, main, shape_summary, single_graph

FIXTURE = json.loads((Path(__file__).parents[1] / "fixtures/fictional_trends.json").read_text(encoding="utf-8"))
FIELDS = DocumentedFields.model_validate(FIXTURE["fields"])
ENDPOINT = "/api/v1/local/trends-preview"
HEADERS = {"X-Hissiyat-Trends-Preview": "1"}


def test_original_values_and_explicit_gaps():
    series = adapt_graph(FIXTURE["response"], FIELDS, fictional=True)
    assert series["source"] == "fictional_fixture"
    assert (series["term"], series["geography"], series["granularity"]) == ("career", "CA", "monthly")
    assert [(point["status"], point["value"]) for point in series["points"]] == [
        ("observed", 124.25), ("observed", 0), ("missing", None), ("suppressed", None), ("observed", 60.125),
    ]
    assert [point["date"] for point in series["points"]] == [f"2025-0{month}-01" for month in range(1, 6)]


@pytest.mark.parametrize("field,value,reason", [
    ("fixture_start", "2025-02-30", "invalid_period_start"),
    ("fixture_start", "2025-02-01T00:00:00Z", "invalid_period_start"),
    ("fixture_start", "2025-01-01", "invalid_period_sequence"),
    ("fixture_start", "2025-02-02", "invalid_period_sequence"),
    ("fixture_status", "unknown", "unverified_value_status"),
    ("fixture_status", "hidden", "unverified_gap_value"),
    ("fixture_value", None, "invalid_observed_value"),
    ("fixture_value", False, "invalid_observed_value"),
    ("fixture_value", float("inf"), "invalid_observed_value"),
])
def test_unverified_or_inconsistent_points_are_rejected(field, value, reason):
    payload = deepcopy(FIXTURE["response"])
    payload["lines"][0]["points"][1][field] = value
    with pytest.raises(GraphError, match=f"^{reason}$"):
        adapt_graph(payload, FIELDS)


def test_schema_metadata_are_required_and_gaps_are_not_imputed():
    payload = deepcopy(FIXTURE["response"])
    line = payload["lines"][0]
    del line["fixture_region"]
    with pytest.raises(GraphError, match="unknown_geography_or_cadence"):
        adapt_graph(payload, FIELDS)
    line["fixture_region"] = "CA"
    del line["points"][1]
    with pytest.raises(GraphError, match="invalid_period_sequence"):
        adapt_graph(payload, FIELDS)


@pytest.mark.parametrize("cadence, dates", [
    ("daily", ("2024-02-29", "2024-03-01")),
    ("weekly", ("2024-12-31", "2025-01-07")),
    ("yearly", ("2024-01-01", "2025-01-01")),
])
def test_calendar_sequences(cadence, dates):
    points = [{"fixture_start": day, "fixture_status": "ok", "fixture_value": 10} for day in dates]
    graph = {"lines": [{"term": "career", "fixture_region": "worldwide", "fixture_aggregation": cadence, "points": points}]}
    assert [point["date"] for point in adapt_graph(graph, FIELDS)["points"]] == list(dates)


def client(environment="development", configured=True, peer="127.0.0.1"):
    settings = Settings(_env_file=None, environment=environment, database_user=None, database_password=None)
    series = adapt_graph(FIXTURE["response"], FIELDS, fictional=True) if configured else None
    return TestClient(create_app(settings, trends_preview=series), base_url="http://127.0.0.1:8058", client=(peer, 50000))


def test_only_loopback_same_process_preview_and_no_store():
    with client() as local:
        response = local.get(ENDPOINT, headers=HEADERS)
        assert response.status_code == 200
        assert response.json()["source"] == "fictional_fixture"
        assert response.headers["cache-control"] == "no-store"
        assert local.get(ENDPOINT).status_code == 404
        assert local.get(ENDPOINT + "?term=apple", headers=HEADERS).status_code == 404
        assert local.get(ENDPOINT, headers={**HEADERS, "Origin": "https://external.invalid"}).status_code == 404
        assert ENDPOINT not in local.get("/openapi.json").json()["paths"]
    for restricted in (client("production"), client(configured=False), client(peer="192.0.2.1")):
        with restricted:
            assert restricted.get(ENDPOINT, headers=HEADERS).status_code == 404


def test_shape_summary_never_echoes_values_or_unrecognized_keys():
    private = "fictional-secret-placeholder"
    summary = shape_summary({"lines": [{"term": private, "points": [{"value": private, private: private}]}], private: private})
    assert summary == {"root": {"lines": "list"}, "line": {"points": "list", "term": "str"},
                       "first_point": {"value": "str"}, "point_count": 1}


def test_one_sdk_query_no_retry_and_sanitized_failure(monkeypatch):
    build = MagicMock()
    build.return_value.getGraph.side_effect = TypeError("fictional-confidential-content")
    session = MagicMock()
    monkeypatch.setitem(sys.modules, "googleapiclient.discovery", SimpleNamespace(build=build))
    monkeypatch.setitem(sys.modules, "requests", SimpleNamespace(Session=lambda: session))
    monkeypatch.setitem(sys.modules, "requests.adapters", SimpleNamespace(HTTPAdapter=MagicMock()))
    payload, failure = single_graph("fictional.key")
    assert payload is None and failure == {"stage": "request", "reason": "request_construction_failed",
                                           "discovery_attempted": False, "query_attempted": False, "http_status": None}
    build.return_value.getGraph.assert_called_once_with(terms="career")
    assert build.call_args.kwargs["num_retries"] == 0
    assert build.call_args.kwargs["cache_discovery"] is False
    session.request.assert_not_called()


def test_transport_rejects_an_external_target_and_a_second_send(monkeypatch):
    monkeypatch.setitem(sys.modules, "httplib2", SimpleNamespace(Response=dict))
    session = MagicMock()
    transport = SingleSend(session)
    with pytest.raises(GraphError, match="transport_rejected"):
        transport.request("https://external.invalid/")
    assert transport.rejected and not transport.sent
    response = session.request.return_value.__enter__.return_value
    response.status_code = 200
    response.iter_content.return_value = iter((b"{}",))
    assert transport.request("https://trends.googleapis.com/fixture")[1] == b"{}"
    assert not session.request.call_args.kwargs["allow_redirects"]
    with pytest.raises(GraphError, match="transport_rejected"):
        transport.request("https://trends.googleapis.com/fixture")
    assert session.request.call_count == 1


def test_console_starts_at_hidden_key_and_reports_only_shape(monkeypatch, tmp_path, capsys):
    report_path = tmp_path / "fictional-status.json"
    stdin = SimpleNamespace(isatty=lambda: True)
    monkeypatch.setattr(sys, "stdin", stdin)
    monkeypatch.setattr(sys, "__stdin__", stdin)
    monkeypatch.setattr(sys, "argv", ["trends_preview", "--status-file", str(report_path)])
    monkeypatch.setenv("HISSIYAT_ENVIRONMENT", "development")
    monkeypatch.setattr("builtins.input", MagicMock(side_effect=AssertionError("No RUN prompt")))
    prompt = MagicMock(return_value="fictional.hidden.key")
    monkeypatch.setattr("app.trends_preview.getpass.getpass", prompt)
    graph = MagicMock(return_value=(FIXTURE["response"], {"query_attempted": True, "http_status": 200}))
    monkeypatch.setattr("app.trends_preview.single_graph", graph)
    monkeypatch.setattr("logging.disable", lambda _level: None)

    assert main() == 0
    prompt.assert_called_once()
    graph.assert_called_once_with("fictional.hidden.key")
    report = capsys.readouterr().out
    assert json.loads(report) == json.loads(report_path.read_text())
    safe = json.loads(report)
    assert safe["status"] == "completed" and safe["display"] == "withheld"
    assert safe["query_attempted"] is True and safe["structure"]["point_count"] == 5
    assert "fictional.hidden.key" not in report and "124.25" not in report


def test_noninteractive_console_stops_before_key_or_request(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(isatty=lambda: False))
    monkeypatch.setattr(sys, "argv", ["trends_preview"])
    prompt = MagicMock()
    graph = MagicMock()
    monkeypatch.setattr("app.trends_preview.getpass.getpass", prompt)
    monkeypatch.setattr("app.trends_preview.single_graph", graph)
    assert main() == 2
    assert json.loads(capsys.readouterr().out) == {"status": "interactive_console_required", "query_attempted": False}
    prompt.assert_not_called()
    graph.assert_not_called()


@pytest.mark.parametrize("graph_status", (200, 503))
def test_complete_console_with_installed_sdk_and_fictional_http(monkeypatch, capsys, graph_status):
    pytest.importorskip("googleapiclient.discovery")
    import requests
    from requests.adapters import HTTPAdapter

    key = "fictional-sdk-test-key"
    discovery = {
        "name": "trends", "version": "v1beta", "rootUrl": "https://trends.googleapis.com:443/", "servicePath": "",
        "schemas": {}, "parameters": {"key": {"type": "string", "location": "query"}},
        "methods": {"getGraph": {"id": "trends.getGraph", "path": "v1beta/test-graph", "httpMethod": "GET",
                                 "parameters": {"terms": {"type": "string", "location": "query", "required": True}}}},
    }
    calls = []

    def fictional_request(method, uri, **options):
        calls.append((method, uri, options))
        payload = discovery if len(calls) == 1 else FIXTURE["response"]
        response = MagicMock()
        response.__enter__.return_value.status_code = 200 if len(calls) == 1 else graph_status
        response.__enter__.return_value.headers = {"Content-Type": "application/json"}
        response.__enter__.return_value.iter_content.return_value = iter((json.dumps(payload).encode(),))
        return response

    session = MagicMock()
    session.__enter__.return_value = session
    session.request.side_effect = fictional_request
    monkeypatch.setattr(requests, "Session", lambda: session)
    monkeypatch.setattr("app.trends_preview.getpass.getpass", lambda _prompt: key)
    monkeypatch.setattr("logging.disable", lambda _level: None)
    stdin = SimpleNamespace(isatty=lambda: True)
    monkeypatch.setattr(sys, "stdin", stdin)
    monkeypatch.setattr(sys, "__stdin__", stdin)
    monkeypatch.setattr(sys, "argv", ["trends_preview"])
    monkeypatch.setenv("HISSIYAT_ENVIRONMENT", "development")

    assert main() == (0 if graph_status == 200 else 2)
    assert len(calls) == 2
    method, uri, options = calls[1]
    assert method == "GET" and urlsplit(uri).port == 443
    assert parse_qs(urlsplit(uri).query)["terms"] == ["career"]
    assert parse_qs(urlsplit(uri).query)["key"] == [key]
    assert options["allow_redirects"] is False and options["stream"] is True
    adapter = session.mount.call_args.args[1]
    assert isinstance(adapter, HTTPAdapter) and adapter.max_retries.total == 0
    report = capsys.readouterr().out
    assert key not in report and "124.25" not in report and "/v1beta/test-graph" not in report
    safe = json.loads(report)
    assert safe["query_attempted"] and safe["http_status"] == graph_status
    if graph_status == 200:
        assert safe["structure"]["point_count"] == 5
    else:
        assert safe["reason"] == "request_http_error"
