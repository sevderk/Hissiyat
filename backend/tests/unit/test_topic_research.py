from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
from unittest.mock import MagicMock
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
import pytest

from app.core import research
from app.core.config import Settings
from app.main import create_app

MARKER = "fictional-confidential-content"
ENDPOINT = "/api/v1/local/research"
HEADERS = {"X-Hissiyat-Local-Research": "1"}
SCOPE = {"mode": "topic", "query": "AI employment", "source": "bluesky", "start_date": "2026-11-05",
         "end_date": "2026-11-16", "language": "en", "geography": None}
LEMMY_SCOPE = {**SCOPE, "source": "lemmy", "language": None, "query": "public transit"}
LEMMY_FIXTURE = json.loads((Path(__file__).parents[1] / "fixtures" / "fictional_lemmy_search.json").read_text(encoding="utf-8"))
COMMENT_FIXTURE = json.loads((Path(__file__).parents[1] / "fixtures" / "fictional_lemmy_comments.json").read_text(encoding="utf-8"))
DISCUSSION_SCOPE = {**SCOPE, "source": "fictional", "query": "community services", "content": "mixed", "analyze_discussion": True}


def scope(**changes):
    return research.ResearchRequest.model_validate_json(json.dumps({**SCOPE, **changes}))


def post(key="fictional-test", date="2026-11-05T03:00:00+03:00", languages=None):
    return {"uri": f"at://did:plc:{'a' * 24}/app.bsky.feed.post/{key}",
            "author": {"displayName": MARKER, "description": "Based in Türkiye"},
            "record": {"$type": "app.bsky.feed.post", "createdAt": date, "text": MARKER, "langs": languages},
            "indexedAt": "2026-11-15T12:00:00Z"}


def mock_upstream(monkeypatch, payload):
    content = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    reply = MagicMock()
    reply.status = 200
    reply.read1.side_effect = BytesIO(content).read1
    opener = MagicMock()
    opener.open.return_value.__enter__.return_value = reply
    factory = MagicMock(return_value=opener)
    monkeypatch.setattr(research, "build_opener", factory)
    return opener, factory


def test_public_lookup_is_one_uncredentialed_request_with_exact_bounds(monkeypatch):
    opener, factory = mock_upstream(monkeypatch, {"posts": [], "cursor": "fictional-cursor"})
    assert research.run_research(scope(query="  AI  employment  "))["retrieved"] == 0
    opener.open.assert_called_once()
    request, = opener.open.call_args.args
    assert opener.open.call_args.kwargs == {"timeout": 8}
    assert request.get_method() == "GET" and request.get_header("Authorization") is None
    url = urlsplit(request.full_url)
    assert (url.scheme, url.netloc, url.path) == ("https", "public.api.bsky.app", "/xrpc/app.bsky.feed.searchPosts")
    assert parse_qs(url.query) == {"q": ["AI employment"], "lang": ["en"], "sort": ["latest"], "limit": ["25"],
                                  "since": ["2026-11-05"], "until": ["2026-11-17"]}
    proxy, redirects = factory.call_args.args
    assert proxy.proxies == {}
    assert redirects.redirect_request(None, None, 302, "", {}, "https://example.invalid") is None


def test_provider_normalization_checks_actual_dates_and_redacts_text_and_author(monkeypatch, caplog, capsys):
    earlier = post(languages=["Tr", "tr", "<script>"], date="2026-11-05T03:00:00+03:00")
    later = post("other", "2026-11-16T23:59:59Z")
    posts = [later, earlier, earlier, post("outside", "2026-11-17T00:00:00Z"), post("invalid", "2026-11-05"),
             {**post(), "uri": "javascript:alert(1)"}, post(".."), post("impossible", "2026-11-05T12:00:00+03:99")]
    mock_upstream(monkeypatch, {"posts": posts, "ignored": MARKER})
    result = research.run_research(scope(mode="event"))
    assert result["scope"]["mode"] == "event"
    assert (result["retrieved"], result["duplicates"], result["outside_dates"], result["invalid_records"]) == (8, 1, 1, 4)
    assert [record["published_at"] for record in result["records"]] == ["2026-11-05T00:00:00+00:00", "2026-11-16T23:59:59+00:00"]
    assert [record["languages"] for record in result["records"]] == [("tr",), ()]
    for record in result["records"]:
        assert record["country"] == "UNKNOWN" and record["geography_attribution"] == "unknown"
        assert record["reference"].startswith("https://bsky.app/profile/did:plc:")
        assert "text" not in record
    assert MARKER not in repr(research.normalize_post(earlier))
    assert MARKER not in json.dumps(result) + caplog.text + capsys.readouterr().out


def test_bluesky_applies_documented_restriction_and_adult_labels(monkeypatch):
    own = post("fictional-self-flagged")
    own["record"]["labels"] = {"values": [{"val": "sexual"}]}
    author = post("fictional-author-flagged")
    author["author"]["labels"] = [{"val": "!no-unauthenticated"}]
    moderated = {**post("fictional-moderator-flagged"), "labels": [{"val": "porn"}]}
    retracted = {**post("fictional-retracted"), "labels": [{"val": "porn", "neg": True}]}
    mock_upstream(monkeypatch, {"posts": [own, author, moderated, retracted, post()]})
    result = research.run_research(scope())
    assert result["excluded_records"] == 3 and len(result["records"]) == 2


@pytest.mark.parametrize("changes", [
    {"mode": "news"}, {"query": "\nAI employment"}, {"query": "𝄞"}, {"query": "x" * 121},
    {"start_date": 123}, {"start_date": "2026-11-05T01:00:00Z"}, {"start_date": "2026-11-30"},
    {"start_date": "2026-09-01"}, {"start_date": "2026-02-31"}, {"end_date": "2099-01-01"},
    {"geography": "TR"}, {"language": "de"}, {"source": "google_trends"}, {"source": "invalid"},
    {"custom_endpoint": "https://example.invalid"},
])
def test_query_and_capability_validation(changes):
    with pytest.raises(ValidationError):
        scope(**changes)


@pytest.mark.parametrize("mode,query,lang,expected", [
    ("topic", "bisiklet yolları", "tr", 2), ("event", "river festival", "en", 2),
    ("event", "unmatched fixture", None, 0),
])
def test_fictional_research_matches_locally(mode, query, lang, expected, monkeypatch):
    adapter = MagicMock(side_effect=AssertionError("Upstream lookup attempted"))
    monkeypatch.setattr(research, "fetch_bluesky", adapter)
    result = research.run_research(scope(mode=mode, query=query, language=lang, source="fictional"))
    assert result["capabilities"]["status"] == "synthetic"
    assert len(result["records"]) == result["retrieved"] == expected
    assert all(row["text"] and row["reference"] is None for row in result["records"])
    adapter.assert_not_called()


@pytest.mark.parametrize("body", [b"!not-json", b"[{}]", {"posts": "not an array"}, {"posts": [None] * 26},
                                  b"x" * (research.MAX_RESPONSE_BYTES + 1)],
                         ids=["invalid-json", "invalid-root", "invalid-posts", "too-many-posts", "oversize"])
def test_unusable_or_oversize_responses_are_controlled(monkeypatch, body):
    opener, _ = mock_upstream(monkeypatch, body)
    with pytest.raises(research.ResearchError, match="^invalid_response$"):
        research.fetch_bluesky(scope())
    opener.open.assert_called_once()


@pytest.mark.parametrize("failure,code", [
    (429, "rate_limited"), (401, "provider_auth_required"), (403, "provider_denied"),
    (302, "provider_unavailable"), (500, "provider_unavailable"),
    (TimeoutError(MARKER), "provider_timeout"), (URLError(TimeoutError(MARKER)), "provider_timeout"),
    (URLError(MARKER), "provider_unavailable"),
])
def test_transport_errors_do_not_retry_or_expose_body(monkeypatch, failure, code):
    opener, _ = mock_upstream(monkeypatch, b"")
    opener.open.side_effect = (HTTPError(f"https://example.invalid/{MARKER}", failure, MARKER, {}, BytesIO(MARKER.encode()))
                               if isinstance(failure, int) else failure)
    with pytest.raises(research.ResearchError, match=f"^{code}$") as error:
        research.fetch_bluesky(scope())
    assert error.value.upstream_status == (failure if isinstance(failure, int) else None)
    opener.open.assert_called_once()


def client(approval=None, environment="development", flag="1", peer="127.0.0.1", *, lemmy_approval=None):
    settings = Settings(_env_file=None, local_research=flag, environment=environment,
                        bluesky_approved_request=approval, lemmy_approved_request=lemmy_approval,
                        database_user=None, database_password=None)
    return TestClient(create_app(settings), base_url="http://127.0.0.1:8056", client=(peer, 50000))


def test_preview_and_one_shot_permission(monkeypatch):
    adapter = MagicMock(return_value=[post()])
    monkeypatch.setattr(research, "fetch_bluesky", adapter)
    request = {**SCOPE, "mode": "event"}
    with client(SecretStr(json.dumps(request))) as local:
        assert local.post(ENDPOINT, json=SCOPE, headers=HEADERS).json() == {"code": "approval_required"}
        assert local.post(ENDPOINT, json=request, headers={**HEADERS, "Origin": "https://example.invalid"}).status_code == 404
        assert local.post(ENDPOINT, json=request).status_code == 404
        assert local.post(ENDPOINT + "?query=fictional", json=request, headers=HEADERS).status_code == 400
        adapter.assert_not_called()
        response = local.post(ENDPOINT, json=request, headers=HEADERS)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store" and "set-cookie" not in response.headers
        assert MARKER not in response.text
        assert local.post(ENDPOINT, json=request, headers=HEADERS).status_code == 403
        assert ENDPOINT not in local.get("/openapi.json").json()["paths"]
    adapter.assert_called_once_with(scope(mode="event"))


def test_failed_attempt_consumes_approval_and_oversize_does_not(monkeypatch):
    adapter = MagicMock(side_effect=research.ResearchError("rate_limited", 429))
    monkeypatch.setattr(research, "fetch_bluesky", adapter)
    with client(SecretStr(json.dumps(SCOPE))) as local:
        response = local.post(ENDPOINT, json={**SCOPE, "query": "a" * 4100}, headers=HEADERS)
        assert response.status_code == 413
        assert local.post(ENDPOINT, json=SCOPE, headers=HEADERS).json() == {"code": "rate_limited"}
        assert local.post(ENDPOINT, json=SCOPE, headers=HEADERS).status_code == 403
    adapter.assert_called_once()


def test_route_not_available_in_production_or_to_external_peers(monkeypatch):
    adapter = MagicMock()
    monkeypatch.setattr(research, "fetch_bluesky", adapter)
    for disabled in (client(environment="production"), client(flag="0"), client(peer="192.0.2.1")):
        with disabled:
            assert disabled.post(ENDPOINT, json=SCOPE, headers=HEADERS).status_code == 404
    with client(SecretStr("invalid JSON")) as local:
        assert local.post(ENDPOINT, json=SCOPE, headers=HEADERS).json() == {"code": "approval_required"}
    adapter.assert_not_called()


@pytest.mark.parametrize("mode", ["topic", "event"])
def test_lemmy_one_local_search_and_metadata_only_result(monkeypatch, caplog, capsys, mode):
    opener, _ = mock_upstream(monkeypatch, LEMMY_FIXTURE)
    submission = scope(**{**LEMMY_SCOPE, "mode": mode})
    result = research.run_research(submission)
    opener.open.assert_called_once()
    request, = opener.open.call_args.args
    target = urlsplit(request.full_url)
    assert (target.scheme, target.hostname, target.path) == ("https", "lemmy.world", "/api/v3/search")
    assert request.get_method() == "GET" and request.get_header("Authorization") is None
    assert parse_qs(target.query) == {"q": ["public transit"], "type_": ["Posts"], "listing_type": ["Local"],
                                      "sort": ["New"], "limit": ["25"]}
    assert result["retrieved"] == 1 and result["scope"] == {**LEMMY_SCOPE, "mode": mode}
    assert result["capabilities"]["languages"] == []
    assert result["records"] == [{"source": "lemmy", "reference": "https://lemmy.world/post/2147483640",
        "published_at": "2026-11-11T12:00:00+00:00", "languages": (), "source_language_id": 37,
        "country": "UNKNOWN", "geography_attribution": "unknown"}]
    normalized, restricted = research.normalize_lemmy_post(LEMMY_FIXTURE["posts"][0])
    assert normalized is not None and MARKER in normalized.body and not restricted
    assert MARKER not in repr(normalized) + json.dumps(result) + caplog.text + capsys.readouterr().out


@pytest.mark.parametrize("key,field,value", [
    ("post", "nsfw", True), ("post", "nsfw", None), ("post", "nsfw", 0),
    ("community", "nsfw", True), ("community", "nsfw", None), ("community", "visibility", "LocalOnly"),
    ("community", "visibility", None), ("community", "hidden", True),
    ("post", "removed", True), ("post", "deleted", True),
    ("community", "removed", True), ("community", "deleted", True),
    ("post", "local", False), ("community", "local", False),
])
def test_lemmy_safety_and_visibility_exclusions(monkeypatch, key, field, value):
    fixture = deepcopy(LEMMY_FIXTURE)
    if value is None:
        fixture["posts"][0][key].pop(field)
    else:
        fixture["posts"][0][key][field] = value
    mock_upstream(monkeypatch, fixture)
    result = research.run_research(scope(**LEMMY_SCOPE))
    assert (result["retrieved"], result["excluded_records"], result["records"]) == (1, 1, [])


def test_lemmy_deduplicates_valid_records_and_checks_date_and_reference(monkeypatch):
    good = deepcopy(LEMMY_FIXTURE["posts"][0])
    def view(**changes):
        return {**good, "post": {**good["post"], **changes}}

    outside = view(published="2026-11-17T00:00:00Z")
    bad_link = view(ap_id="https://lemmy.world.example.invalid/post/2147483640")
    no_body_or_language = view(id=2147483641, ap_id="https://lemmy.world/post/2147483641", body=None, language_id=0)
    mock_upstream(monkeypatch, {"type_": "Posts", "posts": [good, good, outside, bad_link, no_body_or_language, view(published=None), {}]})
    result = research.run_research(scope(**LEMMY_SCOPE))
    assert (result["retrieved"], result["duplicates"], result["outside_dates"], result["invalid_records"]) == (7, 1, 1, 3)
    assert [record["source_language_id"] for record in result["records"]] == [37, None]


def test_lemmy_requires_post_search_response_and_accepts_empty_page(monkeypatch):
    mock_upstream(monkeypatch, {"type_": "Comments", "posts": []})
    with pytest.raises(research.ResearchError, match="^invalid_response$") as error:
        research.fetch_lemmy(scope(**LEMMY_SCOPE))
    assert error.value.upstream_status == 200
    mock_upstream(monkeypatch, {"type_": "Posts", "posts": []})
    assert research.run_research(scope(**LEMMY_SCOPE))["retrieved"] == 0


@pytest.mark.parametrize("changes", [
    {"language": "en"}, {"geography": "TR"}, {"query": "https://example.invalid/post/1"},
    {"query": "!topic@example.invalid"}, {"query": "%local%"},
])
def test_lemmy_rejects_unsupported_filters_and_lookup_queries(changes):
    with pytest.raises(ValidationError):
        scope(**{**LEMMY_SCOPE, **changes})


def test_lemmy_permit_consumed_before_upstream_access_error(monkeypatch):
    opener, _ = mock_upstream(monkeypatch, b"")
    opener.open.side_effect = HTTPError("https://lemmy.world/", 403, MARKER, {}, BytesIO(MARKER.encode()))
    approval = SecretStr(json.dumps(LEMMY_SCOPE))
    with client(lemmy_approval=approval) as local:
        assert local.post(ENDPOINT, json=SCOPE, headers=HEADERS).json() == {"code": "approval_required"}
        assert local.post(ENDPOINT, json={**LEMMY_SCOPE, "query": "another topic"}, headers=HEADERS).status_code == 403
        opener.open.assert_not_called()
        rejected = local.post(ENDPOINT, json=LEMMY_SCOPE, headers=HEADERS)
        assert rejected.status_code == 502 and rejected.headers["cache-control"] == "no-store"
        assert rejected.json() == {"code": "provider_denied", "upstream_status": 403}
        assert local.post(ENDPOINT, json=LEMMY_SCOPE, headers=HEADERS).status_code == 403
    opener.open.assert_called_once()


def test_lemmy_missing_wrong_or_ambiguous_approval_never_calls_provider(monkeypatch):
    adapter = MagicMock()
    monkeypatch.setattr(research, "fetch_lemmy", adapter)
    permit = SecretStr(json.dumps(LEMMY_SCOPE))
    bluesky_permit = SecretStr(json.dumps(SCOPE))
    for preview, status in ((client(), 403), (client(permit), 403),
                            (client(bluesky_permit, lemmy_approval=permit), 403),
                            (client(lemmy_approval=permit, environment="production"), 404),
                            (client(lemmy_approval=permit, peer="192.0.2.1"), 404)):
        with preview:
            assert preview.post(ENDPOINT, json=LEMMY_SCOPE, headers=HEADERS).status_code == status
    adapter.assert_not_called()


def test_lemmy_comment_lookup_uses_only_comments_and_keeps_thread_origin(monkeypatch):
    opener, _ = mock_upstream(monkeypatch, COMMENT_FIXTURE)
    result = research.run_research(scope(**LEMMY_SCOPE, content="comments"))
    opener.open.assert_called_once()
    request, = opener.open.call_args.args
    assert parse_qs(urlsplit(request.full_url).query) == {"q": ["public transit"], "type_": ["Comments"],
        "listing_type": ["Local"], "sort": ["New"], "limit": ["25"]}
    assert result["retrieved"] == 1 and result["scope"]["content"] == "comments"
    assert result["records"] == [{"source": "lemmy", "reference": "https://lemmy.world/comment/2147483630",
        "thread_reference": "https://lemmy.world/post/2147483640", "kind": "comment",
        "published_at": "2026-11-10T06:12:30+00:00", "languages": (), "source_language_id": 37,
        "country": "UNKNOWN", "geography_attribution": "unknown"}]
    assert MARKER not in json.dumps(result)


@pytest.mark.parametrize("container,key,change,reason", [
    ("comment", "deleted", True, "excluded_records"), ("comment", "local", False, "excluded_records"),
    ("comment", "removed", None, "excluded_records"), ("comment", "nsfw", True, "excluded_records"),
    ("post", "nsfw", True, "excluded_records"), ("post", "deleted", True, "excluded_records"),
    ("community", "visibility", "LocalOnly", "excluded_records"),
    ("comment", "published", None, "invalid_records"), ("comment", "post_id", 20, "invalid_records"),
    ("comment", "ap_id", "https://example.invalid/comment/2147483630", "invalid_records"),
    ("comment", "published", "2026-11-17T00:00:00Z", "outside_dates"),
])
def test_lemmy_comment_exclusions(monkeypatch, container, key, change, reason):
    fixture = deepcopy(COMMENT_FIXTURE)
    if change is None:
        fixture["comments"][0][container].pop(key)
    else:
        fixture["comments"][0][container][key] = change
    mock_upstream(monkeypatch, fixture)
    result = research.run_research(scope(**LEMMY_SCOPE, content="comments"))
    assert result[reason] == result["retrieved"] == 1 and result["records"] == []


def test_comment_deduplication_and_empty_results(monkeypatch):
    fixture = deepcopy(COMMENT_FIXTURE)
    fixture["comments"][0]["comment"]["language_id"] = None
    fixture["comments"] *= 2
    mock_upstream(monkeypatch, fixture)
    result = research.run_research(scope(**LEMMY_SCOPE, content="comments"))
    assert result["duplicates"] == 1 and result["records"][0]["source_language_id"] is None
    mock_upstream(monkeypatch, {**fixture, "comments": []})
    assert research.run_research(scope(**LEMMY_SCOPE, content="comments"))["retrieved"] == 0


def test_live_analysis_cannot_use_or_consume_metadata_permission(monkeypatch):
    opener, _ = mock_upstream(monkeypatch, COMMENT_FIXTURE)
    permitted = {**LEMMY_SCOPE, "content": "comments"}
    with client(lemmy_approval=SecretStr(json.dumps(permitted))) as local:
        denied = local.post(ENDPOINT, headers=HEADERS, json={**permitted, "analyze_discussion": True})
        assert denied.status_code == 403 and denied.json() == {"code": "analysis_permission_unverified"}
        wrong_content = local.post(ENDPOINT, headers=HEADERS, json=LEMMY_SCOPE)
        assert wrong_content.status_code == 403
        opener.open.assert_not_called()
        result = local.post(ENDPOINT, headers=HEADERS, json=permitted)
        assert result.status_code == 200 and "discussion_analysis" not in result.json()
    opener.open.assert_called_once()


def test_fictional_discussion_reuses_models_and_signals(monkeypatch):
    from app.core import discussion_analysis

    model = MagicMock(wraps=discussion_analysis.analyze_texts)
    monkeypatch.setattr(discussion_analysis, "analyze_texts", model)
    with client() as local:
        response = local.post(ENDPOINT, headers=HEADERS, json=DISCUSSION_SCOPE)
    assert response.status_code == 200
    result = response.json()
    analysis = result["discussion_analysis"]
    assert (result["retrieved"], len(analysis["evidence_rows"])) == (16, 16)
    assert sum(record.get("kind") == "comment" for record in result["records"]) == 10
    assert analysis["topics_status"] == "nmf_only"
    assert analysis["expression_signals"]["submitted_texts"] == 16
    assert analysis["expression_signals"]["emotions"]["frustration"] == 2
    assert analysis["expression_signals"]["needs"]["information"] == 3
    assert len(analysis["topics"]["methods"]["nmf"]["groups"]) == 2
    assert [call.args[2] for call in model.call_args_list] == ["both", "nmf"]


@pytest.mark.parametrize("language,count", [("en", 6), ("tr", 0)])
def test_discussion_under_threshold_keeps_expression_counts_without_clustering(monkeypatch, language, count):
    from app.core import discussion_analysis

    model = MagicMock()
    monkeypatch.setattr(discussion_analysis, "analyze_texts", model)
    result = research.run_research(scope(**{**DISCUSSION_SCOPE, "content": "posts", "language": language}))
    analysis = result["discussion_analysis"]
    assert analysis["topics_status"] == "insufficient_texts" and analysis["topics"] is None
    assert len(analysis["evidence_rows"]) == analysis["expression_signals"]["submitted_texts"] == count
    model.assert_not_called()
