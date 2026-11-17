from builtins import open as open_file
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from threading import Event
from unittest.mock import patch

from fastapi.testclient import TestClient
import pytest

pytest.importorskip("sklearn", reason="The opt-in flow uses requirements-analysis.txt")

from app.core.local_text_analysis import DISPLAY_TERMS, MAX_BODY_BYTES, analyze_texts
from app.core.config import Settings
from app.main import create_app

EXAMPLES = json.loads((Path(__file__).resolve().parents[3] /
                       "frontend/src/lib/local-analysis-examples.json").read_text(encoding="utf-8"))
PATH = "/api/v1/local/text-analysis"
HEADERS = {"X-Hissiyat-Local-Analysis": "1"}
BASE = "http://127.0.0.1:8000"
PEER = ("127.0.0.1", 50001)
PRIVATE = "zzconfidentialmarker@example.invalid"


def settings(environment="development", opted_in="1"):
    return Settings(_env_file=None, environment=environment, local_text_analysis=opted_in,
                    local_analysis_model_dir=None, database_name=None, database_user=None, database_password=None)


@pytest.fixture
def client():
    with patch("app.main.Database", side_effect=AssertionError("Unexpected database access")):
        with TestClient(create_app(settings()), base_url=BASE, client=PEER, headers=HEADERS) as browser:
            yield browser


@pytest.mark.parametrize("collection", tuple(EXAMPLES))
@pytest.mark.parametrize("k", (2, 3))
def test_both_domains_and_group_counts_are_deterministic(client, collection, k):
    payload = {"k": k, "texts": EXAMPLES[collection]}
    first = client.post(PATH, json=payload)
    second = client.post(PATH, json=payload)
    assert first.status_code == second.status_code == 200
    assert first.headers["Cache-Control"] == "no-store"
    assert first.json() == second.json()
    result = first.json()
    assert set(result) == {"groups", "unassigned", "iteration_limit"}
    assert len(result["groups"]) == k
    assert sum(group["size"] for group in result["groups"]) + result["unassigned"] == len(payload["texts"])
    for group in result["groups"]:
        assert group["size"] > 0
        assert set(group) == {"size", "keywords"}
        assert set(group["keywords"]) <= DISPLAY_TERMS


def test_replacing_texts_changes_groups_with_the_same_number_of_inputs():
    texts = EXAMPLES["technology"]
    changed = texts[:2] + texts[5:] + [texts[6], texts[8], texts[9]]
    assert len(texts) == len(changed)
    baseline, modified = (analyze_texts(batch, 3)["methods"]["nmf"] for batch in (texts, changed))
    assert sorted(group["size"] for group in baseline["groups"]) != sorted(group["size"] for group in modified["groups"])


def test_empty_vocabulary_rows_are_reported_as_unassigned():
    result = analyze_texts(EXAMPLES["technology"] + ["the and or"], 3)["methods"]["nmf"]
    assert result["unassigned"] == 1


@pytest.mark.parametrize("payload", [
    {}, {"k": 1, "texts": EXAMPLES["career"]}, {"k": 4, "texts": EXAMPLES["career"]},
    {"k": 2.0, "texts": EXAMPLES["career"]}, {"k": "2", "texts": EXAMPLES["career"]},
    {"k": 2, "texts": []}, {"k": 2, "texts": [PRIVATE] * 11},
    {"k": 2, "texts": [PRIVATE] * 101}, {"k": 2, "texts": [" "] * 12},
    {"k": 2, "texts": [42] * 12}, {"k": 2, "texts": [PRIVATE * 20] * 12},
    {"k": 2, "texts": EXAMPLES["career"], "unexpected": PRIVATE},
    {"k": 2, "texts": EXAMPLES["career"], "method": PRIVATE},
    {"k": 2, "texts": EXAMPLES["career"], "include_signals": "true"},
])
def test_invalid_inputs_return_only_a_safe_code(client, payload):
    response = client.post(PATH, json=payload)
    assert response.status_code == 400
    assert response.json() == {"code": "invalid_input"}
    assert PRIVATE not in response.text


@pytest.mark.parametrize("texts", [["the or and"] * 12, ["same identical text"] * 12])
def test_unusable_inputs_explain_insufficient_variation(client, texts):
    response = client.post(PATH, json={"texts": texts, "k": 2})
    assert response.status_code == 422
    assert response.json() == {"code": "insufficient_variation"}


def test_chunked_body_is_bounded_without_content_length(client):
    def chunks():
        yield PRIVATE.encode()
        yield b"x" * MAX_BODY_BYTES

    with patch("app.api.v1.local_text_analysis.analyze_texts", side_effect=AssertionError("Unexpected analysis")):
        response = client.post(PATH, content=chunks(), headers={"Content-Type": "application/json"})
    assert response.status_code == 413
    assert response.json() == {"code": "too_large"}


def test_repeated_private_marker_is_not_disclosed_or_persisted(client, caplog, capsys, monkeypatch, tmp_path):
    analyze_texts(EXAMPLES["career"], 3)  # Load numerical libraries before auditing writes.
    monkeypatch.chdir(tmp_path)
    with patch("builtins.open", wraps=open_file) as opened:
        response = client.post(PATH, json={"k": 3, "include_signals": True,
                                          "texts": [f"I am worried about {PRIVATE}. {text}" for text in EXAMPLES["career"]]})
    assert response.status_code == 200
    assert response.json()["expression_signals"]["emotions"]["worry"] == len(EXAMPLES["career"])
    assert "private" not in response.text and "zzconfidentialmarker" not in response.text
    assert PRIVATE not in caplog.text and PRIVATE not in "".join(capsys.readouterr())
    assert list(tmp_path.iterdir()) == []
    for call in opened.call_args_list:
        mode = call.kwargs.get("mode", call.args[1] if len(call.args) > 1 else "r")
        assert not any(flag in mode for flag in "wax+")


def test_duplicate_documents_do_not_count_as_three_sources_for_keyword_disclosure(client):
    sentences = ["Library workshops offer project resources."] * 6 + ["Training schedule changed after work."] * 6
    response = client.post(PATH, json={"k": 2, "texts": sentences})
    assert response.status_code == 200
    assert sorted(group["size"] for group in response.json()["groups"]) == [6, 6]
    assert all(group["keywords"] == [] for group in response.json()["groups"])


def test_unexpected_model_error_is_sanitized_and_busy_lock_resets(client, caplog):
    payload = {"k": 2, "texts": EXAMPLES["technology"]}
    with patch("app.api.v1.local_text_analysis.analyze_texts", side_effect=RuntimeError(PRIVATE)):
        response = client.post(PATH, json=payload)
    assert response.status_code == 503
    assert response.json() == {"code": "unavailable"}
    assert PRIVATE not in caplog.text
    assert client.post(PATH, json=payload).status_code == 200


def test_concurrent_analysis_does_not_queue_another_fit(client):
    entered, release = Event(), Event()
    payload = {"k": 2, "texts": EXAMPLES["technology"]}

    def slow_fit(texts, k, method, directory):
        entered.set()
        assert release.wait(5)
        return analyze_texts(texts, k, method, directory)

    with patch("app.api.v1.local_text_analysis.analyze_texts", side_effect=slow_fit):
        with ThreadPoolExecutor(max_workers=1) as worker:
            running = worker.submit(client.post, PATH, json=payload)
            try:
                assert entered.wait(5)
                second = client.post(PATH, json=payload)
                assert second.status_code == 429
                assert second.json() == {"code": "busy"}
            finally:
                release.set()
            assert running.result(timeout=5).status_code == 200


@pytest.mark.parametrize(("environment", "opted_in"), [("development", "0"), ("production", "1"), ("test", "1")])
def test_api_is_absent_outside_enabled_development(environment, opted_in):
    with TestClient(create_app(settings(environment, opted_in)), base_url=BASE, client=PEER, headers=HEADERS) as client:
        assert client.post(PATH, json={}).status_code == 404
        assert client.post(PATH, json={"k": 2, "texts": EXAMPLES["career"], "include_signals": True}).status_code == 404
        assert PATH not in client.get("/openapi.json").json()["paths"]


@pytest.mark.parametrize("headers", [
    {"Host": "external.invalid"}, {"Origin": BASE}, {"Sec-Fetch-Site": "same-origin"},
    {"X-Hissiyat-Local-Analysis": ""}, {"X-Forwarded-For": "127.0.0.1"},
])
def test_direct_browser_and_untrusted_host_requests_are_rejected(client, headers):
    assert client.post(PATH, json={}, headers=headers).status_code == 404


def test_remote_peer_is_rejected_even_with_local_host_and_explicit_header():
    with TestClient(create_app(settings()), base_url=BASE, client=("192.0.2.10", 50001), headers=HEADERS) as client:
        assert client.post(PATH, json={}).status_code == 404


@pytest.mark.parametrize("collection", tuple(EXAMPLES))
@pytest.mark.parametrize("k", (2, 3))
def test_method_modes_use_the_same_submission_and_are_deterministic(client, collection, k):
    import numpy as np

    texts = EXAMPLES[collection]
    mock_vectors = np.eye(3, dtype=np.float32)[np.arange(len(texts)) % 3]
    with patch("app.core.local_text_analysis._encoder") as loader:
        loader.return_value.encode.return_value = mock_vectors
        payload = {"texts": texts, "k": k, "include_signals": True}
        nmf = client.post(PATH, json={**payload, "method": "nmf"}).json()
        loader.assert_not_called()
        minilm = client.post(PATH, json={**payload, "method": "minilm"}).json()
        comparison = client.post(PATH, json={**payload, "method": "both"})
        assert comparison.status_code == 200
        result = comparison.json()
        assert client.post(PATH, json={**payload, "method": "both"}).json() == result
        assert result["methods"] == {**nmf["methods"], **minilm["methods"]}
        assert result["expression_signals"] == nmf["expression_signals"] == minilm["expression_signals"]
        assert result["expression_signals"]["submitted_texts"] == len(texts)
        assert nmf["agreement"] is minilm["agreement"] is None
        assert result["agreement"]["common_assigned"] == len(texts)
        assert -1 <= result["agreement"]["ari"] <= 1
        for called in loader.return_value.encode.call_args_list:
            assert called.args == (texts,)
        for method in result["methods"].values():
            assert len(method["groups"]) == k
            assert sum(group["size"] for group in method["groups"]) + method["unassigned"] == len(texts)
            assert all(set(group["keywords"]) <= DISPLAY_TERMS for group in method["groups"])


def test_comparison_excludes_nmf_unassigned_texts(client):
    import numpy as np

    texts = EXAMPLES["technology"] + ["the and or"]
    with patch("app.core.local_text_analysis._encoder") as loader:
        loader.return_value.encode.return_value = np.eye(3, dtype=np.float32)[np.arange(len(texts)) % 3]
        result = client.post(PATH, json={"texts": texts, "k": 3, "method": "both"}).json()
    assert result["methods"]["nmf"]["unassigned"] == 1
    assert result["methods"]["minilm"]["unassigned"] == 0
    assert result["agreement"]["common_assigned"] == len(texts) - 1


def test_minilm_descriptors_suppress_private_terms_and_duplicate_support(client):
    import numpy as np

    texts = [f"library resources workshop {PRIVATE}"] * 6 + [f"training schedule work {PRIVATE}"] * 6
    with patch("app.core.local_text_analysis._encoder") as loader:
        loader.return_value.encode.return_value = np.repeat(np.eye(2, dtype=np.float32), 6, axis=0)
        response = client.post(PATH, json={"texts": texts, "k": 2, "method": "minilm"})
    assert response.status_code == 200
    assert all(group["keywords"] == [] for group in response.json()["methods"]["minilm"]["groups"])
    assert PRIVATE not in response.text


def test_distinct_text_and_embedding_degeneracy_are_rejected(client):
    import numpy as np

    with patch("app.core.local_text_analysis._encoder") as loader:
        duplicate = client.post(PATH, json={"texts": ["Same"] * 12, "k": 3, "method": "minilm"})
        assert duplicate.status_code == 422
        loader.assert_not_called()
        loader.return_value.encode.return_value = np.ones((len(EXAMPLES["career"]), 3), dtype=np.float32)
        degenerate = client.post(PATH, json={"texts": EXAMPLES["career"], "k": 3, "method": "minilm"})
    assert degenerate.status_code == 422


def test_missing_model_has_safe_error_without_network_or_fallback(client):
    payload = {"texts": EXAMPLES["career"], "k": 3, "method": "minilm"}
    with patch("socket.socket.connect") as connect:
        response = client.post(PATH, json=payload)
        connect.assert_not_called()
    assert response.status_code == 503
    assert response.json() == {"code": "model_unavailable"}
    assert client.post(PATH, json={**payload, "method": "nmf"}).status_code == 200


def test_minilm_asset_integrity_rejects_malformed_and_replaced_files(tmp_path):
    from hashlib import sha1

    from app.core import minilm

    model_file = tmp_path / "model.onnx"
    tokenizer_file = tmp_path / "tokenizer.json"
    with pytest.raises(minilm.ModelUnavailable):
        minilm.MiniLMEncoder(tmp_path)
    tokenizer = b"dummy tokenizer text"
    tokenizer_file.write_bytes(tokenizer)
    model_file.write_bytes(b"bad model bytes")
    blob = sha1(f"blob {len(tokenizer)}\0".encode() + tokenizer).hexdigest()
    with (patch.object(minilm, "TOKENIZER_BYTES", len(tokenizer)),
          patch.object(minilm, "MODEL_BYTES", len(b"bad model bytes"))):
        with pytest.raises(minilm.ModelUnavailable, match="^model_integrity_mismatch$"):
            minilm.MiniLMEncoder(tmp_path)
        with patch.object(minilm, "TOKENIZER_BLOB", blob):
            with pytest.raises(minilm.ModelUnavailable, match="^model_integrity_mismatch$"):
                minilm.MiniLMEncoder(tmp_path)


def test_ari_ignores_cluster_number_and_unassigned_rows():
    import numpy as np

    from app.core.topic_model import grouping_agreement

    left = np.array([0, 0, 1, 1, -1, 1])
    right = np.array([1, 1, 0, 0, 1, -1])
    assert grouping_agreement(left, right) == {"ari": 1, "common_assigned": 4}
    assert grouping_agreement(left, np.zeros(6)) == {"ari": None, "common_assigned": 5}
