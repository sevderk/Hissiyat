"""Synthetic checks for the private aggregate review report."""

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from research.phase_4e import review, summarize


class AggregateTests(unittest.TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.directory = Path(self.folder.name)
        self.review_file = self.directory / review.STATE_FILE
        self.items = review.fictional_items(b"s" * 32)
        self.state = review._state_for_items(self.items, "fictional", None)
        for item, decision in zip(self.items, (
            self.decision(labels={"education": "direct", "career": "contextual"}),
            self.decision(insufficient=True),
            self.decision(privacy="exclude"),
            self.decision(labels={"education": "contextual"}, b_decision="include"),
            self.decision(insufficient=True, b_decision="unclear"),
            self.decision(labels={"information": "direct"}, b_decision="generic_advice"),
        ), strict=True):
            self.state["decisions"][item.review_id] = decision

    @staticmethod
    def decision(privacy="suitable", labels=None, insufficient=False, b_decision=None):
        return {"privacy": privacy, "labels": labels or {}, "insufficient": insufficient, "b_decision": b_decision}

    def run_summary(self, state):
        self.review_file.write_text(json.dumps(state), encoding="utf-8")
        with patch.object(review, "PER_COHORT", 3):
            return summarize.summarize(self.directory, source="fictional")

    def test_counts_evidence_and_denominators(self):
        result = self.run_summary(self.state)
        a, b = (result["cohorts"][cohort] for cohort in ("A", "B"))
        self.assertEqual(a["completed"], 3)
        self.assertEqual(a["privacy"], {"suitable": 2, "needs_review": 0, "exclude": 1})
        self.assertEqual(a["label_percentage_denominator"], 2)
        self.assertEqual(a["labels"]["education"], {"count": 1, "direct": 1, "contextual": 0, "percent": 50.0})
        self.assertEqual(a["labels"]["career"], {"count": 1, "direct": 0, "contextual": 1, "percent": 50.0})
        self.assertEqual(a["labels"]["insufficient"], {"count": 1, "direct": None, "contextual": None, "percent": 50.0})
        self.assertEqual(b["relevance"]["personal_uncertainty_supported"], 1)
        self.assertEqual(b["relevance"]["personal_uncertainty_not_supported"], 1)
        self.assertEqual(b["relevance"]["unclear"], 1)
        self.assertEqual(b["relevance"]["supported_percent"], 33.33)
        self.assertEqual(b["relevance"]["eligible_completed_denominator"], 3)

    def test_privacy_blocked_b_is_not_assessed(self):
        self.state["decisions"][self.items[5].review_id] = self.decision(privacy="needs_review")
        result = self.run_summary(self.state)["cohorts"]["B"]
        self.assertEqual(result["privacy"]["needs_review"], 1)
        self.assertEqual(result["relevance"]["not_assessed_due_to_privacy"], 1)
        self.assertEqual(result["relevance"]["personal_uncertainty_not_supported"], 0)
        self.assertEqual(result["relevance"]["supported_percent"], 50.0)
        for item in self.items[3:]:
            self.state["decisions"][item.review_id] = self.decision(privacy="exclude")
        result = self.run_summary(self.state)["cohorts"]["B"]
        self.assertIsNone(result["relevance"]["supported_percent"])
        self.assertIsNone(result["labels"]["education"]["percent"])

    def test_rejects_incomplete_invalid_and_duplicate_records(self):
        incomplete = deepcopy(self.state)
        incomplete["decisions"].pop(self.items[0].review_id)
        with self.assertRaisesRegex(review.ReviewError, "^expected_40_complete_reviews_per_cohort$"):
            self.run_summary(incomplete)

        invalid = deepcopy(self.state)
        invalid["decisions"][self.items[0].review_id]["b_decision"] = "include"
        with self.assertRaisesRegex(review.ReviewError, "^invalid_saved_review$"):
            self.run_summary(invalid)

        raw = json.dumps(self.state).replace('"education": "direct"', '"education": "contextual", "education": "direct"')
        self.review_file.write_text(raw, encoding="utf-8")
        with self.assertRaisesRegex(review.ReviewError, "^invalid_saved_review$"):
            summarize.summarize(self.directory, source="fictional")

    def test_report_has_no_row_material_and_never_reads_key(self):
        key_path = self.directory / review.KEY_FILE
        key_path.write_text("Fictional secret sentinel", encoding="utf-8")
        original_open = Path.open
        reads = []

        def guard(path, *args, **kwargs):
            reads.append(path.name)
            if path == key_path:
                self.fail("The aggregate read a key")
            return original_open(path, *args, **kwargs)

        with patch.object(Path, "open", guard):
            result = self.run_summary(self.state)
        self.assertEqual(reads, [review.STATE_FILE, review.STATE_FILE])
        path = summarize._write_summary(self.directory, result)
        output = path.read_text(encoding="utf-8")
        for item in self.items:
            for value in (item.review_id, item.title, item.body, "Fictional secret sentinel"):
                self.assertNotIn(value, output)
        with self.assertRaises(FileExistsError):
            summarize._write_summary(self.directory, result)
        self.assertEqual(json.loads(output), result)


if __name__ == "__main__":
    unittest.main()
