"""Run the two prespecified historical questions after separate owner authorization."""

import argparse
from collections import Counter
import json
from pathlib import Path
import re
from statistics import median
from unicodedata import normalize

from app.core.civil_comments import archive_sample, download_archive, phrase_pattern
from app.core.discussion_analysis import analyze_discussion
from app.core.research import CIVIL_FIRST, CIVIL_LAST, ResearchError, ResearchRequest, civil_query_phrases

QUESTIONS = {
    "wages": "minimum wage | living wage | hourly wages | low wages",
    "job_opportunities": "job opportunities | job creation | create jobs | creating jobs | find a job | finding a job | looking for work",
}


def study_scope(query: str) -> ResearchRequest:
    return ResearchRequest.model_validate({
        "mode": "topic", "query": query, "source": "civil_comments", "language": "en", "content": "comments",
        "analyze_discussion": True, "start_date": CIVIL_FIRST.isoformat(), "end_date": CIVIL_LAST.isoformat(),
    })


def run_study(payload: bytes | bytearray, model_directory=None) -> dict:
    results = {}
    provenance = None
    for question, query in QUESTIONS.items():
        scope = study_scope(query)
        records, metrics, document = archive_sample(payload, scope)
        records.sort(key=lambda record: record.published_at)
        analysis = analyze_discussion(records, model_directory, include_sensitivity=True)
        matched, outside, invalid, duplicates, excluded = metrics
        phrases = {phrase: re.compile(phrase_pattern(phrase)) for phrase in civil_query_phrases(scope.query)}
        selected_phrases = dict.fromkeys(phrases, 0)
        for record in records:
            text = normalize("NFC", record.body.casefold())
            for phrase, pattern in phrases.items():
                selected_phrases[phrase] += bool(pattern.search(text))
        results[question] = {
            "match_type": "any_exact_phrase", "selected_phrase_counts": selected_phrases,
            "matched": matched, "outside_dates": outside, "invalid": invalid, "duplicates": duplicates,
            "excluded": excluded, "screening": document["screening"], "eligible": document["eligible"],
            "selected": len(records), "analyzed": len(analysis["evidence_rows"]),
            "distinct_articles": len({record.article_id for record in records if record.article_id is not None}),
            "distinct_publications": len({record.publication_id for record in records if record.publication_id is not None}),
            "unknown_article": sum(record.article_id is None for record in records),
            "unknown_publication": sum(record.publication_id is None for record in records),
            "first": records[0].published_at.date().isoformat() if records else None,
            "last": records[-1].published_at.date().isoformat() if records else None,
            "months": dict(Counter(record.published_at.strftime("%Y-%m") for record in records)),
            "selected_median_characters": median(len(record.body) for record in records) if records else None,
            "topics_status": analysis["topics_status"], "topics": analysis["topics"],
            "expression_signals": analysis["expression_signals"], "sensitivity": analysis["sensitivity"],
        }
        if provenance is None:
            provenance = {key: document[key] for key in (
                "source", "license", "artifact", "revision", "sha256", "examined", "retrieved_at"
            )}
    return {"dataset": provenance, "study_window": [CIVIL_FIRST.isoformat(), CIVIL_LAST.isoformat()],
            "article_context": "unavailable", "geography": "unknown", "questions": results}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorized-retrieval", action="store_true", help="One explicit owner approval for this retrieval.")
    parser.add_argument("--model-dir", type=Path)
    args = parser.parse_args()
    if not args.authorized_retrieval:
        parser.error("A separately authorized retrieval is required.")
    try:
        payload = download_archive()
        result = run_study(payload, args.model_dir)
    except ResearchError as exc:
        print(json.dumps({"status": "stopped", "code": exc.code, "http_status": exc.upstream_status}))
        return 1
    except Exception:
        print(json.dumps({"status": "stopped", "code": "local_study_failed"}))
        return 1
    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
