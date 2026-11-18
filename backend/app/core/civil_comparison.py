"""Compare frozen Civil Comments processing policies with aggregate output only."""

import argparse
from hashlib import sha256
import json
from pathlib import Path

from app.core import civil_comments as civil
from app.core.civil_study import QUESTIONS, study_scope
from app.core.discussion_analysis import analyze_discussion
from app.core.expression_evidence import LABELS, RULES, expression_evidence
from app.core.expression_signals import aggregate_expression_signals
from app.core.research import CIVIL_FIRST, CIVIL_LAST, ResearchError

COMMON_LABELS = LABELS[:9]


def legacy_counts(texts):
    signals = aggregate_expression_signals(texts)
    return {**signals["emotions"], **signals["needs"], **signals["experiences"]}


def record_key(record):
    # Deduplication gives each selected document a unique normalized body.
    # Linkage stays in memory and includes the source metadata of the chosen row.
    return (record.published_at, record.article_id, record.publication_id,
            " ".join(record.body.casefold().split()))


def expression_sets(texts, *, updated):
    if updated:
        report = expression_evidence(texts, list(range(len(texts))))
        return {label: {item["row"] for item in report["evidence"] if item["label"] == label} for label in LABELS}
    counts = [legacy_counts([text]) for text in texts]
    return {label: {row for row, result in enumerate(counts) if result[label]} for label in COMMON_LABELS}


def summarize_policy(payload, scope, model_directory, *, updated):
    records, metrics, document = civil.archive_sample(
        payload, scope, max_text_chars=8000 if updated else 500, collapse_whitespace=not updated,
    )
    records.sort(key=lambda record: record.published_at)
    analysis = analyze_discussion(records, model_directory, include_sensitivity=True)
    retained = [records[row] for row in analysis["evidence_rows"]]
    texts = [record.body for record in retained]
    sets = expression_sets(texts, updated=updated)
    evidence = analysis["expression_evidence"]
    matched, outside, invalid, duplicates, _ = metrics
    rules = {rule: len({item["row"] for item in evidence["evidence"] if item["rule"] == rule}) for rule in RULES}
    summary = {
        "matched": matched, "outside_dates": outside, "invalid": invalid, "duplicates": duplicates,
        "screening": document["screening"], "eligible": document["eligible"], "selected": len(records),
        "selected_characters": sum(len(record.body) for record in records),
        "selected_long_documents": sum(len(" ".join(record.body.split())) > 500 for record in records),
        "analyzed": len(retained), "characters": analysis["processing"]["characters"],
        "segments": analysis["processing"]["segments"], "processing_exclusions": analysis["processing"]["excluded"],
        "expression_method": "explicit_english_spans_v2" if updated else "explicit_english_rules_v1",
        "counts": {label: len(sets[label]) if label in sets else None for label in LABELS},
        "documents_with_expressions": len(set().union(*sets.values())),
        "evidence_spans": len(evidence["evidence"]) if updated else None,
        "abstentions": evidence["abstentions"] if updated else None,
        "late_evidence_documents": len({item["row"] for item in evidence["evidence"] if item["start"] >= 500}) if updated else None,
        "rule_documents": rules if updated else None,
        "topics_status": analysis["topics_status"], "topics": analysis["topics"],
        "sensitivity": analysis["sensitivity"],
    }
    return summary, records, retained, document


def paired_comparison(legacy_records, updated_records):
    legacy_keys = {record_key(record) for record in legacy_records}
    common = [record for record in updated_records if record_key(record) in legacy_keys]
    # Both rules see the same complete input here to isolate rule differences.
    texts = [record.body for record in common]
    old, new = expression_sets(texts, updated=False), expression_sets(texts, updated=True)
    return {
        "documents": len(texts),
        "legacy_detected_documents": len(set().union(*old.values())),
        "updated_detected_documents": len(set().union(*new.values())),
        "categories": {label: {
            "legacy": len(old[label]), "updated": len(new[label]),
            "retained": len(old[label] & new[label]), "gained": len(new[label] - old[label]),
            "lost": len(old[label] - new[label]),
        } for label in COMMON_LABELS},
        "new_categories": {label: len(new[label]) for label in LABELS[9:]},
    }


def compare_archive(payload, model_directory=None):
    if len(payload) != civil.ARCHIVE_BYTES or sha256(payload).hexdigest() != civil.SHA256:
        raise ResearchError("invalid_response", 502)
    questions = {}
    provenance = None
    for question, query in QUESTIONS.items():
        scope = study_scope(query)
        old, old_selected, old_analyzed, document = summarize_policy(payload, scope, model_directory, updated=False)
        new, new_selected, new_analyzed, _ = summarize_policy(payload, scope, model_directory, updated=True)
        old_keys = {record_key(record) for record in old_selected}
        new_keys = {record_key(record) for record in new_selected}
        assert old["matched"] == new["matched"]
        questions[question] = {
            "query": query, "legacy": old, "updated": new,
            "selection": {"shared": len(old_keys & new_keys), "legacy_only": len(old_keys - new_keys),
                          "updated_only": len(new_keys - old_keys)},
            "paired": paired_comparison(old_analyzed, new_analyzed),
        }
        if provenance is None:
            provenance = {key: document[key] for key in (
                "source", "license", "license_url", "artifact", "revision", "sha256", "examined", "retrieved_at",
            )}
    return {"schema_version": 1, "dataset": provenance,
            "study_window": [CIVIL_FIRST.isoformat(), CIVIL_LAST.isoformat()],
            "geography": "unknown", "article_context": "unavailable", "questions": questions}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--authorized-retrieval", action="store_true", help="One separately approved archive retrieval.")
    source.add_argument("--source-file", type=Path, help="An existing authorized, pinned local archive.")
    parser.add_argument("--model-dir", type=Path)
    args = parser.parse_args()
    try:
        if args.source_file:
            with args.source_file.open("rb") as stream:
                payload = stream.read(civil.ARCHIVE_BYTES + 1)
        else:
            payload = civil.download_archive()
        report = compare_archive(payload, args.model_dir)
    except ResearchError as error:
        print(json.dumps({"status": "stopped", "code": error.code, "http_status": error.upstream_status}))
        return 1
    except Exception:
        print(json.dumps({"status": "stopped", "code": "local_comparison_failed"}))
        return 1
    print(json.dumps(report, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
