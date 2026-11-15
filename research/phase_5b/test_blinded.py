"""Synthetic checks for the short blinded reviewer workflow."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from research.phase_4e import review
from research.phase_5b import blinded


class BlindTests(unittest.TestCase):
    def setUp(self):
        self.key = b"fictional-secret-key".ljust(32, b"0")
        self.items = [review.Item(f"{i:064x}", "A" if i < 40 else "B", f"Fictional title {i}", "Fictional body.")
                      for i in range(80)]
        self.first = review._state_for_items(self.items, "fictional", None)
        for index, item in enumerate(self.items):
            self.first["decisions"][item.review_id] = {
                "privacy": "suitable", "labels": {"career": "direct"}, "insufficient": False,
                "b_decision": None if index < 40 else ("include" if index < 76 else "generic_advice")
            }
        self.plan = blinded._plan(self.first, self.key)

    def test_deterministic_balanced_and_purposeful(self):
        self.assertEqual(self.plan, blinded._plan(self.first, self.key))
        selected = list(self.plan.values())
        self.assertEqual(sum(self.first["items"][item] == "A" for item in selected), 6)
        self.assertEqual(sum(self.first["items"][item] == "B" for item in selected), 6)
        self.assertEqual(sum(self.first["decisions"][item]["b_decision"] == "generic_advice" for item in selected), 1)
        self.assertFalse(set(selected) & set(list(self.first["items"])[:5]))
        self.assertFalse(set(selected) & self.plan.keys())
        self.assertNotEqual([self.first["items"][item] for item in selected], ["A"] * 6 + ["B"] * 6)

    def test_reconstruction_mismatch_stops_and_output_has_no_owner_decisions(self):
        with self.assertRaisesRegex(review.ReviewError, "^exact_review_linkage_failed$"):
            blinded._blind_items(self.items[::-1], self.first, self.plan)
        items = blinded._blind_items(self.items, self.first, self.plan)
        self.assertEqual([item.cohort for item in items], ["X"] * 12)
        self.assertEqual([item.review_id for item in items], list(self.plan))
        with TemporaryDirectory() as folder:
            directory = Path(folder)
            state = blinded._state(directory, self.first, self.key, self.plan)
            with patch.object(blinded, "_workspace", return_value=directory):
                blinded._save(directory, state)
            raw = (directory / blinded.FILE).read_text()
            for value in [item.review_id for item in self.items] + [
                "Fictional title", "Fictional body", "fictional-secret-key", '"career"', '"A"', '"B"'
            ]:
                self.assertNotIn(value, raw)
            self.assertEqual(json.loads(raw)["decisions"], {})
            self.assertEqual(blinded._state(directory, self.first, self.key, self.plan), state)
            with blinded._exclusive(directory):
                with self.assertRaisesRegex(review.ReviewError, "^blinded_workspace_in_use$"):
                    with blinded._exclusive(directory):
                        self.fail("Concurrent session accepted")
            self.first["decisions"][self.items[0].review_id]["labels"] = {"education": "direct"}
            with self.assertRaisesRegex(review.ReviewError, "^invalid_blinded_state$"):
                blinded._state(directory, self.first, self.key, self.plan)

    def test_only_collected_labels_compared_in_complete_independent_review(self):
        with self.assertRaisesRegex(review.ReviewError, "^independent_review_incomplete$"):
            blinded.summarize(self.first, {"decisions": {}}, self.plan)
        second = {"decisions": {}}
        for blind_id, first_id in self.plan.items():
            context = self.first["decisions"][first_id]["b_decision"] or "include"
            second["decisions"][blind_id] = {"privacy": "suitable", "labels": {"career": "direct"},
                                            "insufficient": False, "b_decision": context}
            blinded._validate(second["decisions"][blind_id])
        result = blinded.summarize(self.first, second, self.plan)
        self.assertEqual(result["privacy"], {"compared": 12, "agreed": 12, "percent": 100.0, "kappa": None})
        self.assertEqual(result["personal_uncertainty_B_only"],
                         {"compared": 6, "agreed": 6, "percent": 100.0, "kappa": 1.0})
        self.assertEqual(result["labels"].keys(), blinded.LABELS.keys())
        encoded = json.dumps(result)
        self.assertTrue(all(identifier not in encoded for identifier in self.plan))
        self.assertEqual(blinded.agreement([(True, False), (True, True), (False, False), (False, False)])["kappa"], .5)

    def test_window_has_only_neutral_controls_and_own_saved_state(self):
        import tkinter as tk

        try:
            root = tk.Tk()
        except tk.TclError:
            self.skipTest("Native desktop unavailable")
        root.withdraw()
        try:
            items = blinded._blind_items(self.items, self.first, self.plan)
            with TemporaryDirectory() as folder:
                state = blinded._state(Path(folder), self.first, self.key, self.plan)
            window = blinded.BlindWindow(root, items, state, lambda: None)
            for index in range(12):
                heading = str(window.heading["text"])
                self.assertEqual(heading, f"Soru {index + 1}/12  ·  Kaydedilen 0/12")
                self.assertEqual(window.privacy.get(), "")
                self.assertTrue(all(control.get() == review.EVIDENCE["none"] for control in window.labels.values()))
                self.assertEqual(window.b_choice.get(), "")
                window.next.invoke()
            self.assertEqual(window.labels.keys(), blinded.LABELS.keys())
            self.assertNotIn("B", window.context_caption)
            self.assertEqual(state["decisions"], {})
            window.privacy.set(review.PRIVACY["suitable"])
            window.apply_privacy()
            window.labels["education"].set(review.EVIDENCE["contextual"])
            window.b_choice.set(blinded.CONTEXT["unclear"])
            window.save_current()
            self.assertEqual(state["decisions"][items[-1].review_id]["labels"], {"education": "contextual"})
            window.previous.invoke()
            self.assertEqual(window.privacy.get(), "")
            window.next.invoke()
            self.assertEqual(window.b_choice.get(), blinded.CONTEXT["unclear"])
            self.assertEqual(len(state["decisions"]), 1)
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
