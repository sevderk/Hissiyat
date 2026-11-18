import csv
import gzip
from hashlib import sha256
from io import BytesIO, StringIO
import json
from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from pydantic import SecretStr
import pytest

from app.core import civil_comments as civil, civil_study
from app.core.config import Settings
from app.core.research import ResearchError, ResearchRequest
from app.main import create_app


REQUEST = {"mode": "topic", "query": "work", "source": "civil_comments", "start_date": "2015-01-01",
           "end_date": "2017-12-31", "language": "en", "geography": None, "content": "comments",
           "analyze_discussion": True}


def scope(**changes):
    return ResearchRequest.model_validate_json(json.dumps({**REQUEST, **changes}))


def fictional_row(identifier=123, **changes):
    return {"id": str(identifier), "comment_text": "I worked with the fictional team. This is our work.",
            "created_date": "2016-05-31 23:12:23.123456-01", "article_id": "45", "publication_id": "6",
            "rating": "approved", "toxicity": "0.1", "toxicity_annotator_count": "4",
            **dict.fromkeys(civil.ZERO_SCORES, "0"), "unused_identity": "SYNTHETIC_NOT_FOR_DISPLAY", **changes}


def packed(rows):
    buffer = StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return gzip.compress(buffer.getvalue().encode())


def test_sample_is_bounded_stable_and_deduplicated():
    rows = [fictional_row(index, article_id=str(1 + index // 8),
                          comment_text=f"I used the fictional work service with class {index}.")
            for index in range(1, 241)]
    duplicate = fictional_row(999, comment_text=rows[0]["comment_text"])
    records, metrics, examined, eligible, screening = civil.select_sample([*rows, rows[0], duplicate], scope())
    assert (records, metrics, examined, eligible, screening) == civil.select_sample([duplicate, rows[0], *reversed(rows)], scope())
    assert (len(records), metrics, examined, eligible) == (100, (242, 0, 0, 2, 0), 242, 240)
    assert max(sum(other.article_id == record.article_id for other in records) for record in records) == 4


@pytest.mark.parametrize("changes", [
    {"sexual_explicit": "0.01"}, {"threat": "0.01"}, {"severe_toxicity": "0.01"}, {"obscene": "0.01"},
    {"toxicity": "0.2"}, {"toxicity": "nan"}, {"obscene": ""}, {"toxicity_annotator_count": "0"},
    {"rating": "rejected"}, {"comment_text": "The fictional work email with details is a@example.invalid."},
])
def test_safety_filters_fictional_rows(changes):
    assert civil.select_sample([fictional_row(**changes)], scope())[1] == (1, 0, 0, 0, 1)


def test_literal_topic_timestamp_and_missing_article_context():
    rows = [fictional_row(), fictional_row(124, comment_text="The fictional teams were at workshops."),
            fictional_row(125, created_date="2016-01-01 07:00:00"),
            fictional_row(126, created_date="2018-01-01 00:00:00+00")]
    accepted, metrics, examined, eligible, _ = civil.select_sample(rows, scope(mode="event", end_date="2016-06-01"))
    assert (metrics, examined, eligible) == ((3, 1, 1, 0, 0), 4, 1)
    assert accepted[0].published_at.isoformat() == "2016-06-01T00:12:23.123456+00:00"
    assert civil.source_time("2016-05-31 23:12:23+0060") is None
    assert civil.source_time("0001-01-01 00:00:00+23:00") is None
    missing = civil.select_sample([fictional_row(article_id="", publication_id="unknown")], scope())[0][0]
    assert missing.for_display() == {"source": "civil_comments", "reference": None, "kind": "comment",
        "thread_reference": None, "published_at": "2016-06-01T00:12:23.123456+00:00", "languages": ("en",),
        "country": "UNKNOWN", "geography_attribution": "unknown", "article_id": None, "publication_id": None}


def test_approved_scope_runs_full_fixture_flow_once_without_private_payload(monkeypatch):
    rows = [fictional_row(index, article_id=str(index), comment_text=(
        f"I used the fictional work library with training resources and class {index}."
        if index % 2 else f"I attended the fictional work team meeting for transport and schedule {index}."
    )) for index in range(1, 15)]
    archive = packed(rows)
    monkeypatch.setattr(civil, "ARCHIVE_ROWS", len(rows))
    monkeypatch.setattr(civil, "ARCHIVE_BYTES", len(archive))
    monkeypatch.setattr(civil, "SHA256", sha256(archive).hexdigest())

    class Response(BytesIO):
        status = 200
        headers = {"Content-Length": str(len(archive))}

    transport = MagicMock()
    transport.open.return_value = Response(archive)
    monkeypatch.setattr(civil, "build_opener", lambda *_: transport)
    settings = Settings(_env_file=None, local_research="1", environment="development",
                        civil_approved_request=SecretStr(json.dumps(REQUEST)))
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8070", client=("127.0.0.1", 50000)) as local:
        headers = {"X-Hissiyat-Local-Research": "1"}
        path = "/api/v1/local/research"
        assert local.post(path, json={**REQUEST, "query": "travel"}, headers=headers).status_code == 403
        transport.open.assert_not_called()
        result = local.post(path, json=REQUEST, headers=headers)
        assert result.status_code == 200 and result.headers["cache-control"] == "no-store"
        assert local.post(path, json=REQUEST, headers=headers).status_code == 403
    assert transport.open.call_count == 1
    assert transport.open.call_args.args[0].full_url == civil.URL
    result_data = result.json()
    assert result_data["capabilities"]["status"] == "historical"
    assert result_data["dataset_document"]["examined"] == result_data["dataset_document"]["eligible"] == 14
    assert result_data["discussion_analysis"]["topics_status"] == "nmf_only"
    assert result_data["discussion_analysis"]["expression_signals"]["experiences"]["reported"] == 14
    assert len(result_data["records"]) == 14
    assert all(row["reference"] is None and "text" not in row and row["country"] == "UNKNOWN"
               for row in result_data["records"])
    assert not any(term in result.text for term in ("SYNTHETIC_NOT_FOR_DISPLAY", "I used", "I attended"))


def test_archive_rejects_wrong_schema_count_and_corruption(monkeypatch):
    monkeypatch.setattr(civil, "ARCHIVE_ROWS", 2)
    incomplete = fictional_row()
    del incomplete["threat"]
    for archive in (b"fictional invalid gzip", packed([fictional_row()]), packed([incomplete, incomplete])):
        with pytest.raises(ResearchError, match="invalid_response"):
            civil.archive_sample(archive, scope())


@pytest.mark.parametrize("query", ["minimum wage |", "minimum wage || living wage", "minimum wage | MINIMUM WAGE", "jobs | living wage",
                                  "minimum wage | (living wage)"])
def test_historical_phrase_list_rejects_ambiguous_syntax(query):
    with pytest.raises(ValueError):
        scope(query=query)


def test_focused_study_has_one_download_and_independent_denominators(monkeypatch, capsys):
    rows = [
        fictional_row(101, comment_text="The minimum wage and living wage are distinct proposals for the town."),
        fictional_row(102, article_id="46", comment_text="The program would create jobs for this town."),
        fictional_row(103, comment_text="The minimum wages and jobs were listed for this fictional report."),
        fictional_row(104, comment_text="The minimum weekly wage and the living budget are part of this work."),
        fictional_row(105, comment_text="The minimum wage applies to this program." + " For this program." * 500),
        fictional_row(106, comment_text="With the proposed plan I need advice about how to find a job."),
        fictional_row(107, comment_text="The school was testing a program for job opportunities.", threat="0.25"),
    ]
    monkeypatch.setattr(civil, "ARCHIVE_ROWS", len(rows))
    download = MagicMock(return_value=packed(rows))
    monkeypatch.setattr(civil_study, "download_archive", download)
    monkeypatch.setattr("sys.argv", ["civil_study"])
    with pytest.raises(SystemExit) as stopped:
        civil_study.main()
    assert stopped.value.code == 2
    download.assert_not_called()
    capsys.readouterr()
    monkeypatch.setattr("sys.argv", ["civil_study", "--authorized-retrieval"])
    assert civil_study.main() == 0
    download.assert_called_once_with()
    output = capsys.readouterr().out
    assert "distinct proposals" not in output and "evidence_rows" not in output
    report = json.loads(output)
    assert report["dataset"]["examined"] == 7
    wages, jobs = report["questions"].values()
    assert (wages["matched"], wages["eligible"], wages["selected"]) == (2, 1, 1)
    assert wages["selected_phrase_counts"]["minimum wage"] == wages["selected_phrase_counts"]["living wage"] == 1
    assert wages["screening"]["length"] == 1
    assert (jobs["matched"], jobs["eligible"], jobs["analyzed"], jobs["distinct_articles"]) == (3, 2, 2, 2)
    assert jobs["screening"]["safety_labels"] == 1
    assert jobs["topics_status"] == jobs["sensitivity"]["status"] == "insufficient_texts"


def test_study_sensitivity_has_a_prespecified_minimum(monkeypatch):
    from app.core import discussion_analysis

    grouping = MagicMock(return_value=("comparison", {}))
    monkeypatch.setattr(discussion_analysis, "group_discussion", grouping)
    rows = [fictional_row(index, article_id=str(index),
            comment_text=f"The fictional work team has a training project with group {index}.") for index in range(1, 25)]
    records = civil.select_sample(rows, scope())[0]
    for count, expected_k in [(11, []), (23, [2]), (24, [2, 3])]:
        grouping.reset_mock()
        discussion_analysis.analyze_discussion(records[:count], include_sensitivity=True)
        assert [call.args[1] for call in grouping.call_args_list] == expected_k
