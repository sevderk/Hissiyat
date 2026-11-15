"""Fictional linkage, model-comparison, metric and output tests."""

from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import numpy as np

from research.phase_4c import prepare
from research.phase_4c.test_prepare import csv_bytes, fictional_row
from research.phase_4e import review, summarize
from research.phase_5a import experiment


def decision(cohort, label="career", b="include"):
    return {"privacy": "suitable", "labels": {label: "direct"}, "insufficient": False,
            "b_decision": b if cohort == "B" else None}


class ExperimentTests(unittest.TestCase):
    def test_reconstructs_only_reviewed_records_and_rejects_membership_changes(self):
        rows = [fictional_row(i) for i in range(10, 115)]
        payload = csv_bytes(rows)
        source_checks = {"expected_size": len(payload), "expected_digest": sha256(payload).hexdigest()}
        with patch.object(prepare, "TARGET", 45):
            items = review.review_items(payload, b"k" * 32, **source_checks)
        self.assertEqual([item.cohort for item in items], ["A"] * 40 + ["B"] * 40)
        saved = review._state_for_items(items, "fictional", None)
        for i, item in enumerate(items):
            saved["decisions"][item.review_id] = decision(item.cohort, b="generic_advice" if i >= 76 else "include")
        experiment._require_completed_review(saved)
        documents, labels = experiment.link_review(items, saved)
        self.assertEqual(len(documents), 80)
        self.assertEqual(len(labels), 80)
        self.assertEqual(len({document.group for document in documents}), 80)
        self.assertIn("do not want", documents[0].text)
        with self.assertRaisesRegex(experiment.ExperimentError, "^exact_review_linkage_failed$"):
            experiment.link_review(items[::-1], saved)
        with self.assertRaisesRegex(experiment.ExperimentError, "^exact_review_linkage_failed$"):
            experiment.link_review(items[:-1], saved)
        with self.assertRaisesRegex(experiment.ExperimentError, "^duplicate_reconstructed_review_id$"):
            experiment.link_review(items[:-1] + items[:1], saved)
        saved["decisions"][items[0].review_id]["privacy"] = "needs_review"
        with self.assertRaisesRegex(experiment.ExperimentError, "^review_contains_non_suitable_questions$"):
            experiment._require_completed_review(saved)

    def test_same_inputs_and_sensitivity_without_raw_output(self):
        themes = (
            "fictional algebra geometry calculus number equation proof learning mathematics theorem classroom education",
            "fictional instrument music concert harmony rhythm chords piano performance melody composition rehearsal",
            "fictional machine circuits voltage hardware motor sensors engineering technical manufacturing mechanic",
        )
        documents, decisions = [], []
        vectors = np.zeros((80, 384), dtype=np.float32)
        for i in range(80):
            topic = i % 3
            cohort = "A" if i < 40 else "B"
            documents.append(experiment.Document(themes[topic] + " shared experimental phrase", i, cohort))
            decisions.append(decision(cohort, b="generic_advice" if i >= 76 else "include"))
            vectors[i, topic] = 1
        original_fit = experiment.methods._fit

        def checked_fit(rows, k, embeddings=None):
            self.assertIn(k, (2, 3))
            if embeddings is not None:
                self.assertTrue(np.array_equal(embeddings, vectors[[row.group for row in rows]]))
            return original_fit(rows, k, embeddings)

        with (patch.object(experiment.methods, "_local_embeddings", return_value=vectors) as embed,
              patch.object(experiment.methods, "_fit", side_effect=checked_fit)):
            result = experiment.analyze(documents, decisions, Path("fictional-model"))
        self.assertEqual(embed.call_args.args[0], [row.text for row in documents])
        primary = result["primary"]["models"]
        sensitivity = result["human_judgment_selected_sensitivity"]["models"]
        for name in ("tfidf_nmf", "minilm_kmeans"):
            for k in ("2", "3"):
                self.assertEqual(len(primary[k][name]["sizes"]), int(k))
                self.assertEqual(sum(primary[k][name]["sizes"]) + primary[k][name]["unassigned"], 80)
                self.assertEqual(sum(sensitivity[k][name]["sizes"]) + sensitivity[k][name]["unassigned"], 76)
                self.assertEqual(primary[k][name]["resample_attempts"], 5)
        self.assertEqual(primary["3"]["between_methods"], {"ari": 1.0, "common_assigned": 80})
        self.assertEqual(sensitivity["3"]["between_methods"], {"ari": 1.0, "common_assigned": 76})
        payload = json.dumps(result)
        for theme in themes:
            self.assertNotIn(theme, payload)
        self.assertNotIn('"terms"', payload)
        self.assertNotIn('"review_id"', payload)

    def test_metrics_reject_degenerate_assignments_and_mask_small_cells(self):
        self.assertEqual(experiment._agreement(np.array([0, 0, 1, 1, -1]), np.array([1, 1, 0, 0, 1])),
                         {"ari": 1.0, "common_assigned": 4})
        self.assertEqual(experiment._agreement(np.array([0, 0, 0]), np.array([0, 0, 1])),
                         {"ari": None, "common_assigned": 3})
        rows = [experiment.Document("fictional text", i, "B") for i in range(7)]
        decisions = [decision("B") for _ in rows]
        decisions[0] = decision("B", label="emotion", b="generic_advice")
        alignment = experiment._alignment(rows, decisions, np.array([0] * 6 + [1]), 2)["B"]
        self.assertEqual(alignment[0]["labels"]["emotion"], "1-4")
        self.assertIsNone(alignment[0]["context_no_support"])
        self.assertEqual(alignment[1], {"cluster": 2, "n": 1})

    def test_safe_output_path_and_no_overwrite(self):
        with TemporaryDirectory() as folder:
            base = Path(folder).resolve()
            out = base / ("phase-4e-" + "a" * 32)
            out.mkdir()
            self.assertEqual(prepare._private_directory(out, base=base, phase="4e"), out)
            result = {"reconstructed": 80, "exact_review_linkage": True}
            path = summarize._write_summary(out, result, filename="methods-comparison.json")
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), result)
            with self.assertRaises(FileExistsError):
                summarize._write_summary(out, {}, filename="methods-comparison.json")
            with self.assertRaises(prepare.PreparationError):
                prepare._private_directory(out, base=base, phase="4e")


if __name__ == "__main__":
    unittest.main()
