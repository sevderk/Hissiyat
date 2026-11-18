import csv
import gzip
from hashlib import sha256
from io import StringIO
import json
from unittest.mock import MagicMock

import pytest

from app.core import civil_comments as civil, civil_comparison as comparison, discussion_analysis
from app.core.research import ResearchError


def fictional_row(identifier, text, **changes):
    return {"id": str(identifier), "comment_text": text, "created_date": "2016-05-31 12:00:00+00",
            "article_id": str(identifier), "publication_id": "1", "rating": "approved", "toxicity": "0.1",
            "toxicity_annotator_count": "4", **dict.fromkeys(civil.ZERO_SCORES, "0"), **changes}


def archive(monkeypatch, rows):
    buffer = StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    payload = gzip.compress(buffer.getvalue().encode())
    monkeypatch.setattr(civil, "ARCHIVE_ROWS", len(rows))
    monkeypatch.setattr(civil, "ARCHIVE_BYTES", len(payload))
    monkeypatch.setattr(civil, "SHA256", sha256(payload).hexdigest())
    return payload


def rows():
    short = [fictional_row(index,
        f"The fictional minimum wage report was for project {index} and "
        + ("library training. " if index % 2 else "transport schedule. ")
        + "I have been worried about the proposal. I need help now.")
        for index in range(1, 15)]
    long = [fictional_row(index,
        f"The fictional minimum wage and job opportunities report was for project {index}.\n\n"
        + "The fictional team described the library service and the transport schedule. " * 10
        + "I cannot access the form. I chose this plan because the library was accessible.")
        for index in range(15, 29)]
    return short + long + [short[0], fictional_row(900,
        "The fictional minimum wage was listed for the program. " * 180)]


def test_same_population_length_coverage_paired_rules_and_no_raw_output(monkeypatch):
    payload = archive(monkeypatch, rows())
    report = comparison.compare_archive(payload)
    result = report["questions"]["wages"]
    old, new = result["legacy"], result["updated"]
    assert old["matched"] == new["matched"] == 30
    assert (old["eligible"], new["eligible"], old["selected"], new["selected"]) == (14, 28, 14, 28)
    assert (old["screening"]["length"], new["screening"]["length"]) == (15, 1)
    assert old["duplicates"] == new["duplicates"] == 1
    assert new["characters"] > old["characters"]
    assert old["analyzed"] == old["selected"] and new["analyzed"] == new["selected"]
    assert new["segments"] > new["analyzed"] and new["selected_long_documents"] == 14
    assert result["selection"] == {"shared": 14, "legacy_only": 0, "updated_only": 14}
    paired = result["paired"]
    assert paired["documents"] == 14
    assert paired["categories"]["worry"]["lost"] == 14
    assert paired["categories"]["support"]["gained"] == 14
    assert old["counts"]["problem"] is None and new["counts"]["problem"] == 14
    assert new["late_evidence_documents"] == 14
    assert new["topics_status"] == "nmf_only" and set(new["topics"]["separation"]) == {"nmf"}
    assert report["geography"] == "unknown" and report["article_context"] == "unavailable"
    encoded = json.dumps(report)
    for forbidden in ["fictional team", "I cannot", '"evidence_rows":', '"comment_text":', '"article_id":',
                      '"start":', '"body":', '"text":']:
        assert forbidden not in encoded


def test_selection_is_order_independent_with_same_article_cap_and_sample_limit(monkeypatch):
    monkeypatch.setattr(discussion_analysis, "group_discussion", lambda *args: ("insufficient_variation", None))
    source_rows = [fictional_row(index,
        f"The fictional minimum wage and living wage were listed for this project {index}.", article_id=str(1 + index // 6))
        for index in range(1, 181)]
    first = comparison.compare_archive(archive(monkeypatch, source_rows))["questions"]
    second = comparison.compare_archive(archive(monkeypatch, list(reversed(source_rows))))["questions"]
    assert first == second
    result = first["wages"]
    assert result["legacy"]["selected"] == result["updated"]["selected"] == 100
    assert result["selection"] == {"shared": 100, "legacy_only": 0, "updated_only": 0}
    assert result["legacy"]["counts"]["support"] == result["updated"]["counts"]["support"] == 0


def test_policy_screening_order_and_legacy_whitespace_are_explicit(monkeypatch):
    source_rows = [
        fictional_row(1, "The fictional minimum wage was listed. " * 18, rating="rejected"),
        fictional_row(2, "The fictional minimum wage was listed.\n" + " " * 600 + "I need help with the form."),
        fictional_row(3, "The fictional minimum wage was listed with mail a@example.invalid."),
    ]
    result = comparison.compare_archive(archive(monkeypatch, source_rows))["questions"]["wages"]
    assert result["legacy"]["screening"]["length"] == 1
    assert result["updated"]["screening"]["moderation"] == 1
    assert result["legacy"]["screening"]["privacy_or_markup"] == result["updated"]["screening"]["privacy_or_markup"] == 1
    assert result["paired"]["documents"] == 1
    assert result["legacy"]["characters"] < result["updated"]["characters"]


def test_bad_checksum_stops_before_analysis(monkeypatch):
    payload = archive(monkeypatch, rows())
    analyze = MagicMock()
    monkeypatch.setattr(comparison, "summarize_policy", analyze)
    with pytest.raises(ResearchError, match="invalid_response"):
        comparison.compare_archive(payload[:-1] + b"x")
    analyze.assert_not_called()


def test_cli_requires_approval_retrieves_once_and_sanitizes_failures(monkeypatch, capsys):
    payload = archive(monkeypatch, rows())
    download = MagicMock(return_value=payload)
    monkeypatch.setattr(civil, "download_archive", download)
    monkeypatch.setattr("sys.argv", ["civil_comparison"])
    with pytest.raises(SystemExit):
        comparison.main()
    download.assert_not_called()
    capsys.readouterr()
    monkeypatch.setattr("sys.argv", ["civil_comparison", "--authorized-retrieval"])
    assert comparison.main() == 0
    download.assert_called_once_with()
    assert json.loads(capsys.readouterr().out)["schema_version"] == 1
    download.reset_mock()
    download.side_effect = RuntimeError("SYNTHETIC_SECRET_OR_PRIVATE_TEXT")
    assert comparison.main() == 1
    assert json.loads(capsys.readouterr().out) == {"status": "stopped", "code": "local_comparison_failed"}
    download.assert_called_once_with()
