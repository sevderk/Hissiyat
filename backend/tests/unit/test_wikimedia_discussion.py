from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient
from pydantic import SecretStr
import pytest

from app.core import research
from app.core.config import Settings
from app.core.wikimedia_discussion import parse_discussion, plain_english
from app.main import create_app


FIXTURE = json.loads((Path(__file__).parents[1] / "fixtures" / "fictional_wikimedia_discussion.json").read_text(encoding="utf-8"))
SCOPE = {"source": "wikimedia", "mode": "topic", "query": research.WIKI_TITLE, "content": "comments",
         "language": None, "geography": None, "analyze_discussion": True,
         "start_date": "2001-01-01", "end_date": "2026-11-17"}


def scope(**changes):
    return research.ResearchRequest.model_validate_json(json.dumps({**SCOPE, **changes}))


def test_one_request_uses_actual_discussion_contract_and_omits_text_and_identity(monkeypatch):
    class Response(BytesIO):
        status = 200

    transport = MagicMock()
    transport.open.return_value = Response(json.dumps(FIXTURE).encode())
    monkeypatch.setattr(research, "build_opener", lambda *_: transport)
    settings = Settings(_env_file=None, local_research="1", environment="development", database_name=None, database_user=None,
                        database_password=None, wikimedia_approved_request=SecretStr(json.dumps(SCOPE)))
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8070", client=("127.0.0.1", 50000)) as local:
        headers = {"X-Hissiyat-Local-Research": "1"}
        assert local.post("/api/v1/local/research", json={**SCOPE, "analyze_discussion": False}, headers=headers).status_code == 403
        transport.open.assert_not_called()
        result = local.post("/api/v1/local/research", json=SCOPE, headers=headers)
        assert result.status_code == 200 and result.headers["cache-control"] == "no-store"
        assert local.post("/api/v1/local/research", json=SCOPE, headers=headers).status_code == 403
    transport.open.assert_called_once()
    request, = transport.open.call_args.args
    url = urlsplit(request.full_url)
    assert (url.scheme, url.netloc, url.path) == ("https", "en.wikipedia.org", "/w/api.php")
    assert parse_qs(url.query) == {"action": ["discussiontoolspageinfo"], "page": [research.WIKI_TITLE],
        "format": ["json"], "formatversion": ["2"], "prop": ["threaditemshtml|transcludedfrom"],
        "threaditemsflags": ["excludesignatures"], "maxlag": ["5"]}
    assert request.get_header("User-agent") == "HissiyatResearch/0.1 (https://github.com/sevderk/Hissiyat)"
    result_json = result.json()
    document = result_json["source_document"]
    assert (document["license"], document["license_url"], document["history"], document["page"]) == (
        "CC BY-SA 4.0", research.WIKI_LICENSE, research.WIKI_HISTORY, research.WIKI_PAGE)
    assert [row["published_at"] for row in result_json["records"]] == ["2026-11-02T11:00:00+00:00", "2026-11-03T12:00:00+00:00"]
    assert all(row["kind"] == "comment" and row["country"] == "UNKNOWN" and row["reference"] == research.WIKI_PAGE
               for row in result_json["records"])
    analysis = result_json["discussion_analysis"]
    assert analysis["topics_status"] == "insufficient_texts" and analysis["evidence_rows"] == [0, 1]
    assert analysis["expression_signals"]["needs"]["information"] == 1
    assert analysis["expression_signals"]["experiences"]["reported"] == 1
    assert not any(marker in result.text for marker in ("FictionalEditor", "FictionalReply", "I need information", "othercontent"))


@pytest.mark.parametrize("fragment", [
    "<p>I need you to read the <a href='//elsewhere.invalid'>description</a>.</p>",
    "<p>I need information for the test. Contact me at a@example.invalid.</p>",
    "<p>I need information for the test and this is not closed.",
    "<blockquote>I need details about the service.</blockquote>",
    "<p>I used this for the test (UTC).</p>",
    "<p>Copied from this site with the format for our class.</p>",
])
def test_plain_text_checks_reject_unsafe_or_ambiguous_content(fragment):
    assert plain_english(fragment) is None


def test_transclusions_timestamps_and_conflicting_ids_are_not_guessed():
    sample = deepcopy(FIXTURE)
    module = sample["discussiontoolspageinfo"]
    comment = module["threaditemshtml"][0]["replies"][0]
    reply = comment["replies"][0]
    reply.pop("timestamp")
    module["transcludedfrom"][comment["id"]] = "Talk:Other"
    records, counts = parse_discussion(sample, scope())
    assert records == [] and counts == (2, 0, 1, 0, 1)
    module["threaditemshtml"][0]["replies"].append(deepcopy(comment))
    records, counts = parse_discussion(sample, scope())
    assert records == [] and counts == (4, 0, 2, 2, 0)


def test_missing_and_ambiguous_discussions_have_controlled_outcomes():
    with pytest.raises(research.ResearchError, match="discussion_missing"):
        parse_discussion({"error": {"code": "nosuchrevid", "info": "fictional private message"}}, scope())
    ambiguous = deepcopy(FIXTURE)
    ambiguous["discussiontoolspageinfo"]["threaditemshtml"][0]["type"] = "comment"
    with pytest.raises(research.ResearchError, match="invalid_response"):
        parse_discussion(ambiguous, scope())
    assert parse_discussion({"discussiontoolspageinfo": {"threaditemshtml": [], "transcludedfrom": []}}, scope()) == ([], (0, 0, 0, 0, 0))
