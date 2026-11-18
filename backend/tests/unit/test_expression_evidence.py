import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.core import discussion_analysis, local_text_analysis
from app.core.expression_evidence import expression_evidence
from app.core.minilm import ModelUnavailable
from app.core.research import Record
from app.core.text_segments import MAX_COLLECTION_CHARS, segment_collection, segment_document
from datetime import UTC, datetime


@pytest.mark.parametrize("text,expected", [
    ("I am worried about this service.", {"worry"}),
    ("I'm worried about this service.", {"worry"}),
    ("I am not worried about this service.", set()),
    ("I cannot access the booking form.", {"problem"}),
    ("I can access the booking form.", set()),
    ("I do not need help with this.", set()),
    ("I need guidance on this form and I am frustrated.", {"guidance", "frustration"}),
    ("Could someone explain this form?", {"information"}),
    ("Could someone explain this form if the service fails?", set()),
    ("The staff said I am worried about this form.", set()),
    ('The staff said, "I am worried. I need help with this form."', set()),
    ("I am worried about this form, but I need help with the website.", {"worry", "support"}),
    ("I used the service because the website was accessible.", {"reported", "reason"}),
    ("People used the service because the website was accessible.", set()),
    ("I might need guidance on this form.", set()),
    ("I was frustrated because the clerk said the site was closed.", {"frustration"}),
    ("> I am worried about the service.\nI need help with the form.", {"support"}),
    ("I am worried about the service? I need information for the test.", {"information"}),
    ("The guidance was useful. My colleague needs help with the form.", set()),
])
def test_conservative_expressions_have_original_matching_spans(text, expected):
    result = expression_evidence([text], [4], disclose_text=True)
    assert {label for label, count in result["counts"].items() if count} == expected
    for item in result["evidence"]:
        assert item["row"] == 4
        assert item["text"] == text[item["start"]:item["end"]]
        assert item["rule"] and item["start"] < item["end"]


def test_quotes_across_chunks_duplicates_unicode_and_long_tail_are_preserved():
    repeated = "I am worried about the service. "
    quoted = '"I am worried. ' + "The fictional service was listed. " * 30 + 'I need help."'
    tail = "The fictional report was available. " * 30 + "I cannot access the form. I used this because it was available."
    text = "A fictional person called İpek visited the 🏛 office. " + repeated * 2 + quoted + "\n" + tail
    report = expression_evidence([text], [0], disclose_text=True)
    assert report["counts"]["worry"] == report["counts"]["problem"] == report["counts"]["reason"] == 1
    assert report["counts"]["support"] == 0 and report["abstentions"]["quoted"] > 0
    assert any(item["start"] > 500 and item["label"] == "problem" for item in report["evidence"])
    assert all(text[item["start"]:item["end"]] == item["text"] for item in report["evidence"])
    private = expression_evidence([text], [0])
    assert all("text" not in item for item in private["evidence"])
    assert len(expression_evidence([repeated * 100], [0])["evidence"]) == 64


def test_segmentation_keeps_every_character_and_bounds_processing():
    text = ("A fictional paragraph preserves its complete context. " * 18 + "\n\n") * 3
    spans = segment_document(text)
    assert spans[0][0] == 0 and spans[-1][1] == len(text)
    assert all(left[1] == right[0] for left, right in zip(spans, spans[1:]))
    assert "".join(text[start:end] for start, end in spans) == text
    assert len(spans) > 1 and max(end-start for start,end in spans) <= 400
    for documents in [["x" * 8001], ["x" * 401], [text] * (MAX_COLLECTION_CHARS // len(text) + 1)]:
        with pytest.raises(ValueError):
            segment_collection(documents)


def test_minilm_aggregates_all_segments_into_one_document_vector():
    text = "The library was accessible. " * 30 + "I need guidance on transport."
    encoder = MagicMock()
    def encode(parts, **options):
        assert options["reject_truncation"]
        return np.array([[0.0, 1.0] if "transport" in piece else [1.0, 0.0] for piece in parts])
    encoder.encode.side_effect = encode
    with patch.object(local_text_analysis, "_encoder", return_value=encoder):
        vectors = local_text_analysis._document_vectors([text], None)
    assert vectors.shape == (1, 2) and vectors[0, 0] > 0 and vectors[0, 1] > 0
    assert "".join(encoder.encode.call_args.args[0]) == text


def test_long_discussion_retains_document_denominator_and_separation():
    sources = json.loads((Path(__file__).parents[3] / "frontend/src/lib/local-analysis-examples.json").read_text())["technology"]
    texts = [text + " The original document retains the full context of this fictional service." * 9 for text in sources]
    records = [Record("fictional", None, datetime(2026, 11, 10, tzinfo=UTC), text, ("en",)) for text in texts]
    result = discussion_analysis.analyze_discussion(records)
    assert result["processing"]["documents"] == result["expression_signals"]["submitted_texts"] == len(texts)
    assert result["processing"]["segments"] > len(texts)
    assert result["processing"]["characters"] == sum(map(len, texts))
    assert result["topics_status"] == "nmf_only"
    assert sum(group["size"] for group in result["topics"]["methods"]["nmf"]["groups"]) == len(texts)
    assert set(result["topics"]["separation"]) == {"nmf"}
    public = [Record("civil_comments", None, record.published_at, record.body, ("en",), kind="comment")
              for record in records]
    findings = discussion_analysis.analyze_discussion(public)
    assert all("text" not in item for item in findings["expression_evidence"]["evidence"])


def test_token_overflow_abstains_instead_of_truncating():
    from app.core.minilm import MiniLMEncoder

    encoder = MiniLMEncoder.__new__(MiniLMEncoder)
    encoder._tokenizer = MagicMock()
    encoder._tokenizer.encode_batch.return_value = [MagicMock(overflowing=[object()])]
    encoder._session = MagicMock()
    with pytest.raises(ModelUnavailable, match="segment_token_budget_exceeded"):
        encoder.encode(["The complete document must be processed."], reject_truncation=True)
    encoder._session.run.assert_not_called()


def test_separation_uses_assigned_documents_and_preserves_unavailable_score():
    matrix = np.array([[1.0, 0.0], [0.99, 0.01], [0.0, 1.0], [0.01, 0.99], [0.5, 0.5]])
    score = local_text_analysis._separation(matrix, np.array([0, 0, 1, 1, -1]))
    assert score > 0.9
    assert score == local_text_analysis._separation(matrix[:4], np.array([0, 0, 1, 1]))
    assert local_text_analysis._separation(matrix, np.zeros(5, dtype=int)) is None
