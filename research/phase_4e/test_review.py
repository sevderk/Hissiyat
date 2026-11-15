"""Synthetic selection, validation, private storage and native UI checks."""

from contextlib import redirect_stdout
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from research.phase_4c import prepare
from research.phase_4c.test_prepare import csv_bytes, fictional_row
from research.phase_4e import review


def selection(rows, key=b"k" * 32):
    payload = csv_bytes(rows)
    return review.review_items(payload, key, expected_size=len(payload), expected_digest=sha256(payload).hexdigest())


class ReviewTests(unittest.TestCase):
    def test_subset_reconstructs_from_same_protocol_in_both_cohorts(self):
        rows = [fictional_row(i) for i in range(20, 80)]
        rows += [fictional_row(80, asker=20), fictional_row(81, asker=21)]
        with patch.object(prepare, "TARGET", 18), patch.object(review, "PER_COHORT", 6):
            first = selection(rows)
            second = selection(reversed(rows))
            other_key = selection(rows, key=b"x" * 32)
        self.assertEqual(first, second)
        self.assertEqual([item.cohort for item in first], ["A"] * 6 + ["B"] * 6)
        self.assertEqual(len({item.review_id for item in first}), 12)
        self.assertEqual(len({item.body for item in first}), 12)
        groups = {row["question_body"]: row["asker_author_id"] for row in rows}
        self.assertEqual(len({groups[item.body] for item in first}), 12)
        self.assertFalse({item.review_id for item in first} & {item.review_id for item in other_key})
        self.assertNotIn(first[0].body, repr(first))

    def test_privacy_filter_precedes_display_and_fails_closed(self):
        risky = fictional_row(10, question_title="My name is Fictionalperson.")
        linked = fictional_row(11, asker=10)
        safe = fictional_row(12, question_title=" <b>A fictional career decision</b> ")
        items = selection([linked, risky, safe])
        self.assertEqual([(item.title, item.body) for item in items],
                         [("<b>A fictional career decision</b>", safe["question_body"])])
        with self.assertRaisesRegex(review.ReviewError, "^source_stopped_for_privacy$"):
            selection([risky, linked])
        with self.assertRaisesRegex(prepare.PreparationError, "^source_integrity_mismatch$"):
            review.review_items(b"invalid", b"k" * 32)

    def test_annotation_validation_requires_only_supported_codes(self):
        valid = {"privacy": "suitable", "labels": {"career": "direct", "employment": "contextual"},
                 "insufficient": False, "b_decision": "include"}
        review.validate_decision(valid, "B")
        review.validate_decision({"privacy": "needs_review", "labels": {}, "insufficient": False,
                                  "b_decision": None}, "B")
        review.validate_decision({"privacy": "suitable", "labels": {}, "insufficient": True,
                                  "b_decision": "unclear"}, "B")
        for bad in (
            valid | {"privacy": "exclude"},
            valid | {"labels": {"emotion": "contextual"}},
            valid | {"b_decision": None},
            valid | {"insufficient": True},
            valid | {"comment": "A fictional excerpt"},
        ):
            with self.subTest(bad=bad), self.assertRaises(review.ReviewError):
                review.validate_decision(bad, "B")

    def test_annotations_resume_without_saving_text_or_source_ids(self):
        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            rows = [fictional_row(i) for i in range(10, 17)]
            with review._locked_key(directory) as key:
                items = selection(rows, key)
                state = review._state_for_items(items, "fictional", None)
                self.assertEqual(sum(saved for saved, _ in review.review_progress(state).values()), 0)
                state["decisions"][items[0].review_id] = {
                    "privacy": "exclude", "labels": {}, "insufficient": False, "b_decision": None
                }
                state["position"] = 1
                with patch.object(review, "_private_directory", return_value=directory):
                    review._store_state(directory, state)
                with self.assertRaisesRegex(review.ReviewError, "^review_workspace_in_use$"):
                    with review._locked_key(directory):
                        self.fail("Concurrent session was accepted")
            with review._locked_key(directory) as key:
                saved = review._read_state(directory, "fictional")
                self.assertEqual(review._state_for_items(selection(rows, key), "fictional", saved), state)
                self.assertEqual(review.review_progress(saved)["A"], (1, len(items)))
                with self.assertRaisesRegex(review.ReviewError, "^saved_review_selection_changed$"):
                    review._state_for_items(items[1:], "fictional", saved)
            self.assertEqual({file.name for file in directory.iterdir()}, {review.STATE_FILE, review.KEY_FILE})
            content = (directory / review.STATE_FILE).read_text(encoding="utf-8")
            for row in rows:
                for field in ("question_id", "asker_author_id", "question_title", "question_body"):
                    self.assertNotIn(row[field], content)
            with self.assertRaisesRegex(review.ReviewError, "^invalid_saved_review$"):
                review._read_state(directory, prepare.REFERENCE["publisher_sha256"])
            (directory / review.STATE_FILE).write_text('{"notes":"fictional hidden text"}', encoding="utf-8")
            with self.assertRaisesRegex(review.ReviewError, "^invalid_saved_review$"):
                review._read_state(directory, "fictional")

    def test_cleanup_preserves_previous_state_if_atomic_replace_fails(self):
        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            previous = directory / review.STATE_FILE
            previous.write_text("previous", encoding="utf-8")
            state = review._state_for_items(review.fictional_items(b"k" * 32), "fictional", None)
            with (patch.object(review, "_private_directory", return_value=directory),
                  patch.object(Path, "replace", side_effect=OSError),
                  self.assertRaises(OSError)):
                review._store_state(directory, state)
            self.assertEqual(previous.read_text(encoding="utf-8"), "previous")
            self.assertEqual(list(directory.iterdir()), [previous])

    def test_fictional_cli_never_downloads_and_emits_only_counts(self):
        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            with (patch.object(review.sys, "argv", ["review", "--fictional", "--workspace", str(directory)]),
                  patch.object(review, "_private_directory", return_value=directory),
                  patch.object(prepare, "_download") as download,
                  patch("research.phase_4e.window.launch") as launch,
                  redirect_stdout(StringIO()) as console):
                self.assertEqual(review.main(), 0)
            download.assert_not_called()
            launch.assert_called_once()
            self.assertEqual(console.getvalue().splitlines(), ["İnceleme oturumu. A 0/3, B 0/3."])
            self.assertEqual(json.loads((directory / review.STATE_FILE).read_text())["decisions"], {})

    def test_real_cli_rejects_nonlocal_session_before_download(self):
        with (patch.object(review.sys, "argv", [
                  "review", "--approved-careernet-v1.1", "--workspace", "fictional"
              ]),
              patch.object(review, "_require_local_session", side_effect=review.ReviewError("remote_windows_session")),
              patch.object(review, "_private_directory") as workspace,
              patch.object(prepare, "_download") as download,
              patch.object(review.sys, "stderr", new_callable=StringIO) as error):
            self.assertEqual(review.main(), 2)
            self.assertEqual(error.getvalue().splitlines(), ["İnceleme durdu (remote_windows_session)."])
        workspace.assert_not_called()
        download.assert_not_called()

    def test_native_window_navigation_save_and_privacy(self):
        import tkinter as tk
        from research.phase_4e.window import ReviewWindow

        try:
            root = tk.Tk()
        except tk.TclError:
            self.skipTest("Native desktop unavailable")
        root.withdraw()
        try:
            items = review.fictional_items(b"k" * 32)
            state = review._state_for_items(items, "fictional", None)
            saves = []
            window = ReviewWindow(root, items, state, lambda: saves.append(state["position"]))
            self.assertIn("Kurgusal deneme A1", window.question.get("1.0", "end"))
            self.assertNotIn("Kurgusal deneme A2", window.question.get("1.0", "end"))
            window.privacy.set(review.PRIVACY["needs_review"])
            window.apply_privacy()
            self.assertEqual(str(window.labels["education"]["state"]), "disabled")
            window.save_current()
            self.assertEqual(review.review_progress(state)["A"], (1, 3))
            window.next.invoke()
            self.assertIn("Kurgusal deneme A2", window.question.get("1.0", "end"))
            window.previous.invoke()
            self.assertEqual(window.privacy.get(), review.PRIVACY["needs_review"])
            for _ in range(3):
                window.next.invoke()
            self.assertEqual(window.item.cohort, "B")
            window.privacy.set(review.PRIVACY["suitable"])
            window.apply_privacy()
            window.labels["education"].set(review.EVIDENCE["direct"])
            window.labels["employment"].set(review.EVIDENCE["contextual"])
            window.b_choice.set(review.B_DECISIONS["include"])
            window.save_current()
            self.assertEqual(review.review_progress(state)["B"], (1, 3))
            self.assertEqual(state["decisions"][window.item.review_id]["labels"],
                             {"education": "direct", "employment": "contextual"})
            window.close()
            self.assertGreaterEqual(len(saves), 7)
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
