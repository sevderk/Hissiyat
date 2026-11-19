"""Fictional CSV aggregates and the already committed historical report; no retrieval."""
from copy import deepcopy
import json
from unittest.mock import MagicMock
from io import BytesIO

from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.imported_evidence import CsvSummary, csv_evidence, historical_evidence
from app.core.local_interpretation import InterpretationError, check_numbers
from app.core import local_interpretation as ai
from app.main import create_app


def summary():
    def point(day, value):
        return {"date": f"2026-09-{day:02}", "value": value, "periods": 1}
    return {"source": "csv", "url": "https://trends.google.com/trends/explore?date=2026-09-01%202026-10-31&geo=TR&q=fictional%20library",
        "region": "TR", "mode": "topic", "sha256": "a" * 64, "interval": "daily", "observations": 4,
        "observed": 2, "missing": 1, "suppressed": 1, "ambiguous_zero": 1,
        "first_period": "2026-09-01", "last_period": "2026-09-04",
        "peak": point(2, 10), "trough": point(1, 0), "first": point(1, 0), "last": point(2, 10), "change": 10}


def parse(value):
    return CsvSummary.model_validate_json(json.dumps(value))


def test_csv_origin_scale_geo_dates_and_aggregate_only_package():
    package = csv_evidence(parse(summary()))
    assert package.scope.source == "google_trends_csv" and package.scope.geography == "TR"
    assert package.scope.date_unit == "day" and package.scope.start_date == "2026-09-01"
    assert package.fictional is False  # User-supplied attribution, never independently verified origin.
    assert package.facts[0].values["missing"] == package.facts[0].values["suppressed"] == package.facts[0].values["ambiguous_zero"] == 1
    origin = next(f for f in package.facts if f.metric == "csv_origin")
    assert origin.values["attribution"] == "user_supplied" and origin.values["measurement"] == "request_relative_0_to_100"
    assert not any(key in package.model_dump_json() for key in ('csv_base64', '"points"', 'api_key'))
    assert [f.id for f in package.facts] == [f.id for f in csv_evidence(parse(summary())).facts]


@pytest.mark.parametrize("change", [
    lambda v: v.update(region="US"), lambda v: v.update(observed=3), lambda v: v.update(change=99),
    lambda v: v["peak"].update(value=101), lambda v: v["peak"].update(date="2025-01-01"),
    lambda v: v.update(last_period="2026-02-30"), lambda v: v.update(ambiguous_zero=0),
    lambda v: v.update(url=v["url"].replace('trends.google.com', 'example.invalid')),
    lambda v: v.update(url=v["url"] + '&q=forged'), lambda v: v.update(raw_text="FICTIONAL_PRIVATE"),
])
def test_invalid_client_metadata_counts_and_structures_are_rejected(change):
    value = deepcopy(summary()); change(value)
    with pytest.raises((ValueError, ValidationError)):
        parse(value)


def test_no_observed_values_abstains_and_does_not_fabricate_extremes():
    value = summary()
    value.update(observed=0, missing=4, suppressed=0, ambiguous_zero=0, peak=None, trough=None, first=None, last=None, change=None)
    package = csv_evidence(parse(value))
    assert package.status == "insufficient"
    assert not any(f.metric in ('csv_extremes', 'csv_change') for f in package.facts)


@pytest.mark.parametrize("question,old,new,shared,hits", [("wages", 65, 100, 35, 2), ("job_opportunities", 42, 76, 42, 1)])
def test_pinned_historical_report_preserves_policy_denominators_and_weak_clusters(question, old, new, shared, hits):
    package = historical_evidence(question)
    assert package.scope.start_date == '2015-01-01' and package.scope.end_date == '2017-12-31'
    assert package.scope.geography == 'UNKNOWN' and package.scope.analyzed_documents == new
    coverage = next(f for f in package.facts if f.metric == 'historical_coverage')
    assert coverage.values['legacy'] == old and coverage.values['updated'] == new and coverage.values['shared'] == shared
    expressions = next(f for f in package.facts if f.metric == 'historical_expressions')
    assert expressions.values['updated'] == hits and expressions.values['paired_updated'] == 0
    assert any(f.metric == 'topic_validity' and f.kind == 'insufficient' for f in package.facts)
    check_numbers(f'The rules matched {hits} of {new} documents.', expressions)
    with pytest.raises(InterpretationError):
        check_numbers(f'The rules matched {new} of {hits} documents.', expressions)
    serialized = package.model_dump_json()
    assert 'author_id' not in serialized and '"text"' not in serialized


def test_index_units_cannot_be_reported_as_search_counts():
    fact = next(f for f in csv_evidence(parse(summary())).facts if f.metric == 'csv_extremes')
    check_numbers('The peak index is 10.', fact)
    with pytest.raises(InterpretationError): check_numbers('The peak is 10 searches.', fact)
    with pytest.raises(InterpretationError): check_numbers('The peak is 10%.', fact)


def test_local_evidence_route_reuses_existing_authorization_and_never_accepts_historical_numbers(monkeypatch):
    settings = Settings(_env_file=None, environment='development', local_research='1', local_interpretation='1',
        database_name=None, database_user=None, database_password=None)
    app = create_app(settings)
    model = MagicMock()
    monkeypatch.setattr('app.api.v1.local_interpretation.generate_interpretation', model)
    with TestClient(app, base_url='http://127.0.0.1:8064', client=('127.0.0.1', 50000)) as client:
        path='/api/v1/local/evidence'; headers={'X-Hissiyat-Local-Research':'1'}
        body={'source':'historical','question':'wages'}
        assert client.post(path,json=body).status_code == 404
        assert client.post(path,json=body,headers={**headers,'Origin':'https://example.invalid'}).status_code == 404
        assert client.post(path,json={**body,'counts':999},headers=headers).status_code == 400
        response=client.post(path,json=body,headers=headers)
        assert response.status_code == 200 and response.headers['cache-control']=='no-store'
        assert app.state.interpretation_evidence.package_id==response.json()['package_id']
        assert client.post(path,json=summary(),headers=headers).status_code == 200
        model.assert_not_called()
    with TestClient(create_app(settings.model_copy(update={'environment':'production'}))) as client:
        assert client.post('/api/v1/local/evidence',json=body).status_code==404


@pytest.mark.parametrize('problem', ['none', 'wrong_keys', 'swapped_counts'])
def test_historical_named_model_fields_bind_facts_without_order_or_metadata_trust(monkeypatch, problem):
    class TransportReply(BytesIO):
        status=200
    package=historical_evidence('wages')
    draft={'overview':'The historical samples contain 65 legacy and 100 updated documents.',
        'findings':{
            'historical_clusters':'Exploratory: Updated ARI is -0.002; thematic validity is unverified.',
            'historical_expressions':'Exploratory: Wording rules matched 2 of 100 updated documents.',
            'historical_coverage':'The legacy sample contains 65 and the updated sample 100 documents.'},
        'uncertainty':'Thematic validity has no independent assessment.',
        'question':'What independent evidence could assess thematic validity?'}
    if problem=='wrong_keys':draft['findings']['forged_metric']=draft['findings'].pop('historical_clusters')
    if problem=='swapped_counts':draft['findings']['historical_expressions']='Exploratory: Wording rules matched 100 of 2 documents.'
    transport=MagicMock()
    transport.open.return_value=TransportReply(json.dumps({'model':ai.MODEL_ALIAS,'choices':[{
        'finish_reason':'stop','message':{'content':json.dumps(draft)}}]}).encode())
    monkeypatch.setattr(ai,'build_opener',lambda *_:transport)
    if problem!='none':
        with pytest.raises(InterpretationError):ai.generate_interpretation(package,'en',8091)
    else:
        result=ai.generate_interpretation(package,'en',8091)
        assert [f['evidence_id'] for f in result['result']['findings']]==['E02','E03','E04']
        assert result['result']['overview']['evidence_id']=='E02'
        payload=result['result']
        payload['findings'][2]['interpretation']='Exploratory: Reliable themes are established.'
        with pytest.raises(InterpretationError):ai.validate_interpretation(payload,package,'en')
        payload['findings'][2]['interpretation']='Exploratory: Updated ARI is -0.002 and validity is unverified.'
        payload['findings'][1]['interpretation']='Exploratory: These rule matches demonstrate widespread emotions.'
        with pytest.raises(InterpretationError):ai.validate_interpretation(payload,package,'en')
    assert transport.open.call_count==1
