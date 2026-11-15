"""Validate a completed coded review and emit cohort-level results only."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from research.phase_4c import prepare
from research.phase_4e import review


def _percentage(count, denominator):
    return round(100 * count / denominator, 2) if denominator else None


def summarize(directory, *, source=prepare.REFERENCE["publisher_sha256"]):
    state = review._read_state(directory, source)
    if state is None:
        raise review.ReviewError("missing_saved_review")
    progress = review.review_progress(state)
    if any(saved != review.PER_COHORT or total != review.PER_COHORT for saved, total in progress.values()):
        raise review.ReviewError("expected_40_complete_reviews_per_cohort")

    cohorts = {}
    for cohort in ("A", "B"):
        decisions = [state["decisions"][identifier] for identifier, group in state["items"].items()
                     if group == cohort]
        privacy = Counter(decision["privacy"] for decision in decisions)
        suitable = [decision for decision in decisions if decision["privacy"] == "suitable"]
        evidence = Counter((label, kind) for decision in suitable for label, kind in decision["labels"].items())
        labels = {}
        for label in review.LABELS:
            direct, contextual = evidence[label, "direct"], evidence[label, "contextual"]
            labels[label] = {"count": direct + contextual, "direct": direct, "contextual": contextual,
                             "percent": _percentage(direct + contextual, len(suitable))}
        insufficient = sum(decision["insufficient"] for decision in suitable)
        labels["insufficient"] = {"count": insufficient, "direct": None, "contextual": None,
                                  "percent": _percentage(insufficient, len(suitable))}
        cohorts[cohort] = {
            "completed": len(decisions), "privacy": {key: privacy[key] for key in review.PRIVACY},
            "eligible_for_research_consideration": len(suitable),
            "label_percentage_denominator": len(suitable), "labels": labels,
        }
        if cohort == "B":
            contextual_review = Counter(decision["b_decision"] for decision in suitable)
            supported = contextual_review["include"]
            not_supported = sum(contextual_review[key] for key in ("generic_advice", "outside_scope", "hypothetical"))
            cohorts[cohort]["relevance"] = {
                "decisions": {key: contextual_review[key] for key in review.B_DECISIONS},
                "personal_uncertainty_supported": supported,
                "personal_uncertainty_not_supported": not_supported,
                "unclear": contextual_review["unclear"],
                "invalid": 0, "not_assessed_due_to_privacy": len(decisions) - len(suitable),
                "eligible_completed_denominator": len(suitable),
                "supported_percent": _percentage(supported, len(suitable)),
            }

    return {
        "schema": "hissiyat_careernet_review_summary_v1",
        "source_sha256": source, "codebook": review.CODEBOOK,
        "delete_by_utc": datetime.fromisoformat(state["delete_by_utc"]).astimezone(timezone.utc).isoformat(),
        "cohorts": cohorts,
        "limitations": {
            "reviewers": 1, "early_codebook_calibration_assistance": True,
            "independent_reference_labels": False, "inter_rater_reliability_measured": False,
            "A_design": "author_identifier_balanced", "B_design": "provisionally_uncertainty_enriched",
            "population_prevalence_inference": False,
        },
    }


def _write_summary(directory, result, *, filename="review-summary.json"):
    path = directory / filename
    file = path.open("x", encoding="utf-8")
    try:
        with file:
            json.dump(result, file, ensure_ascii=True, indent=2)
            file.write("\n")
    except (Exception, KeyboardInterrupt):
        path.unlink(missing_ok=True)
        raise
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--output-directory", required=True, type=Path)
    arguments = parser.parse_args()
    try:
        directory = review._private_directory(arguments.workspace)
        result = summarize(directory)
        output = prepare._private_directory(arguments.output_directory, phase="4e")
        prepare._check_windows_access(output, verify_files=True)
        path = _write_summary(output, result)
        try:
            prepare._check_windows_access(output, verify_files=True)
        except (Exception, KeyboardInterrupt):
            path.unlink(missing_ok=True)
            raise
        print(json.dumps(result, ensure_ascii=True))
        return 0
    except (review.ReviewError, prepare.PreparationError) as error:
        print(json.dumps({"status": "stopped", "reason": error.args[0]}))
    except (Exception, KeyboardInterrupt):
        print('{"status":"stopped","reason":"local_execution_failed"}')
    return 2


if __name__ == "__main__":
    sys.exit(main())
