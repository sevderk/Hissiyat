"""Exercise the preparation path with fictional CSV rows and no network."""

from contextlib import redirect_stdout
import csv
from functools import partial
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from research.phase_4c import prepare


def fictional_row(number, *, asker=None, **changes):
    tag = chr(97 + number // 26) + chr(97 + number % 26)
    vocabulary = " ".join(f"imaginary{tag}{letter}" for letter in "abcdefghijklmnop")
    return {
        "question_id": str(81_000_000 + number),
        "asker_author_id": str(94_000_000 + (number if asker is None else asker)),
        "question_title": "I am not sure about the career choice",
        "question_body": f"I would like to compare the options, but I do not want to rush into a decision. {vocabulary}.",
        "question_added_at": "Sept. 18, 2022 03:20 pm",
        "answer_body": "FICTIONAL_UNUSED_ANSWER_FIELD",
        "asker_location": "FICTIONAL_UNUSED_LOCATION_FIELD",
        "ScenarioLabels": "FICTIONAL_UNUSED_LABEL_FIELD",
    } | changes


def csv_bytes(rows, *, header=None):
    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=sorted(prepare.EXPECTED_HEADER if header is None else header))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def run_preparation(rows):
    payload = csv_bytes(rows)
    return prepare.prepare(payload, expected_size=len(payload), expected_digest=sha256(payload).hexdigest())


class PreparationTest(unittest.TestCase):
    def test_checksum_is_verified_before_csv_and_errors_do_not_echo_input(self):
        secret = b"FICTIONAL_CHECKSUM_ERROR_VALUE"
        with patch.object(prepare, "_read_questions") as parser:
            with self.assertRaisesRegex(prepare.PreparationError, "^source_integrity_mismatch$"):
                prepare.prepare(secret, expected_size=len(secret), expected_digest="0" * 64)
            with self.assertRaisesRegex(prepare.PreparationError, "^source_integrity_mismatch$"):
                prepare.prepare(secret, expected_size=len(secret) + 1)
        parser.assert_not_called()

    def test_mismatched_header_and_malformed_csv_fail_closed(self):
        unexpected = csv_bytes([], header={"FICTIONAL_UNKNOWN_COLUMN"})
        broken = csv_bytes([]) + b'"unclosed fictional field'
        malformed_utf8 = csv_bytes([]) + b"\xff"
        for payload, reason in ((unexpected, "source_header_mismatch"), (broken, "invalid_source_csv"),
                                (malformed_utf8, "invalid_source_csv")):
            with self.subTest(reason=reason), self.assertRaisesRegex(prepare.PreparationError, f"^{reason}$"):
                prepare.prepare(payload, expected_size=len(payload), expected_digest=sha256(payload).hexdigest())

    def test_selection_is_order_independent_and_askers_do_not_cross_cohorts(self):
        rows = [fictional_row(i) for i in range(10, 23)]
        rows += [fictional_row(24, asker=10), fictional_row(25, asker=11)]
        with patch.object(prepare, "TARGET", 4):
            aggregate, membership, texts, flags = run_preparation(rows)
            shuffled, _, shuffled_texts, _ = run_preparation(reversed(rows))
        self.assertEqual(aggregate, shuffled)
        self.assertEqual([(r["title"], r["body"]) for r in texts],
                         [(r["title"], r["body"]) for r in shuffled_texts])
        self.assertEqual(aggregate["cohorts"]["A_general"]["selected"], 4)
        self.assertEqual(aggregate["cohorts"]["B_provisional"]["candidate_count"], 4)
        self.assertEqual(aggregate["cross_cohort_overlap"], {"question_id": 0, "asker_id": 0})
        self.assertEqual(len({r["asker_id"] for r in membership}), 8)
        self.assertEqual(len({r["question_id"] for r in membership}), 8)
        self.assertEqual({r["question_id"] for r in membership}, {r["question_id"] for r in texts})
        self.assertEqual(flags, ())
        self.assertTrue(all(r["status"] == prepare.REVIEW_STATUS and r["screened"]
                            and not r["human_review_eligible"] and not r["nlp_ready"] for r in membership))
        self.assertEqual(aggregate["selected_not_nlp_ready"], 8)
        self.assertEqual(aggregate["nlp_ready"], 0)
        for private in (json.dumps(membership), json.dumps(texts)):
            for row in rows:
                self.assertNotIn(row["question_id"], private)
                self.assertNotIn(row["asker_author_id"], private)

    def test_row_deduplication_conflicts_quality_and_date_handling(self):
        same = fictional_row(10)
        conflicting = fictional_row(11)
        rows = [
            same, same | {"answer_body": "A second fictional answer"},
            conflicting, conflicting | {"question_title": "A conflicting fictional title"},
            fictional_row(12, question_added_at="Feb 30, 2024 12:00 AM"),
            fictional_row(13, question_added_at=""),
            fictional_row(14, question_title="Short", question_body=""),
            fictional_row(15, asker_author_id=""),
            fictional_row(16, question_title="Kurgusal bir soru", question_body="örnek " * 40),
            fictional_row(17, question_added_at="2019-10-01"),
        ]
        aggregate, _, _, _ = run_preparation(rows)
        self.assertEqual(aggregate["frame"]["answer_level_rows"], 10)
        self.assertEqual(aggregate["frame"]["distinct_question_ids"], 8)
        self.assertEqual(aggregate["frame"]["conflicting_question_ids"], 1)
        self.assertEqual(aggregate["frame"]["repeated_identical_answer_rows"], 1)
        self.assertEqual(aggregate["quality"]["excluded_language_uncertain"], 1)
        self.assertEqual(aggregate["quality"]["excluded_missing_asker"], 1)
        self.assertEqual(aggregate["quality"]["excluded_short_or_empty"], 1)
        self.assertEqual(aggregate["timestamp_status"],
                         {"local_time_unknown_zone": 4, "invalid_or_ambiguous": 1, "missing": 1, "date_only": 1})
        self.assertIn("unknown_date", aggregate["cohorts"]["A_general"]["strata"])
        self.assertEqual(prepare._source_calendar("March 5, 2025 12:00 AM"),
                         ("local_time_unknown_zone", "2025-03-05T00:00:00"))

    def test_duplicates_and_near_duplicates_are_removed_from_both_cohorts(self):
        same = fictional_row(10)
        almost = fictional_row(13, question_body=same["question_body"] + " invented.")
        aggregate, _, texts, _ = run_preparation([
            same, fictional_row(11, question_body=same["question_body"]), almost, fictional_row(14),
        ])
        self.assertEqual(aggregate["duplicates"], {
            "exact_duplicate_questions": 2, "near_duplicate_questions": 3,
            "near_duplicate_pairs": 2, "excluded_duplicate_questions": 3,
        })
        self.assertEqual(len(texts), 1)
        self.assertEqual(aggregate["cohorts"]["B_provisional"]["candidate_count"], 0)

    def test_screening_excludes_private_cues_and_maintains_text_semantics(self):
        rows = [
            fictional_row(10, question_title="My name is Fictionalperson"),
            fictional_row(11, question_title='<a href="https://fictional.example">Private profile</a>'),
            fictional_row(12, question_title="I am a high school sophomore"),
            fictional_row(13, question_title="I live in Inventedplace"),
            fictional_row(14, question_title="I go to Invented Academy"),
            fictional_row(15, question_title="I was diagnosed with a fictitious disorder"),
            fictional_row(16, question_title="<b>I'm not</b> sure about a career in axolotl care"),
        ]
        aggregate, memberships, texts, flags = run_preparation(rows)
        self.assertEqual(aggregate["quality"]["excluded_privacy"], 6)
        self.assertEqual({code for flag in flags for code in flag["reason_codes"]},
                         {"contact", "name_cue", "possible_minor", "location_cue", "school_cue", "sensitive_experience"})
        self.assertTrue(all(not flag["nlp_ready"] for flag in flags))
        self.assertTrue({row["question_id"] for row in flags}.isdisjoint(row["question_id"] for row in memberships))
        self.assertEqual(len(texts), 1)
        self.assertEqual(texts[0]["title"], "I'm not sure about a career in axolotl care")
        serialized = json.dumps((aggregate, memberships, texts, flags))
        for marker in ("Fictionalperson", "fictional.example", "Inventedplace",
                       "Invented Academy", "fictitious disorder", "FICTIONAL_UNUSED"):
            self.assertNotIn(marker, serialized)

    def test_high_risk_combination_stops_before_sampling_and_stores_only_safe_artifacts(self):
        rows = [fictional_row(10, question_title="I am 15 years old. Contact me at imaginary@example.invalid."),
                fictional_row(11)]
        with patch.object(prepare.sampling, "_general") as chooser:
            aggregate, membership, texts, flags = run_preparation(rows)
        chooser.assert_not_called()
        self.assertEqual(aggregate["status"], "stopped_for_privacy")
        self.assertEqual(aggregate["privacy_flags"], {"contact": 1, "possible_minor": 1})
        self.assertEqual((membership, texts, flags), ((), (), ()))
        self.assertEqual(prepare._console_summary(aggregate)["high_risk_combination"], "1-4")
        with TemporaryDirectory() as directory:
            root = Path(directory)
            prepare._store_outputs(root, {}, aggregate, membership, texts, flags)
            self.assertEqual({path.name for path in root.iterdir()}, {"provenance.json", "aggregate.json"})
            self.assertNotIn("imaginary@example.invalid", (root / "aggregate.json").read_text())

    def test_conflicting_question_variants_cannot_hide_privacy_risk(self):
        row = fictional_row(10, question_title="I am 15 years old.")
        conflicting = row | {"question_title": "Contact me at imaginary@example.invalid."}
        with patch.object(prepare.sampling, "_general") as chooser:
            aggregate, membership, texts, flags = run_preparation([row, conflicting, fictional_row(11)])
        chooser.assert_not_called()
        self.assertEqual(aggregate, {"status": "stopped_for_privacy",
                                    "privacy_flags": {"contact": 1, "possible_minor": 1},
                                    "high_risk_combination": 1})
        self.assertEqual((membership, texts, flags), ((), (), ()))

    def test_private_path_rejects_nonempty_wrong_base_and_repository_paths(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            target = root / f"phase-4c-{'a' * 32}"
            target.mkdir()
            self.assertEqual(prepare._private_directory(target, base=root), target)
            with self.assertRaises(prepare.PreparationError):
                prepare._private_directory(target, base=root.parent)
            sibling = root / "sibling"
            sibling.mkdir()
            with self.assertRaises(prepare.PreparationError):
                prepare._private_directory(sibling / ".." / target.name, base=root)
            (target / "fictional.txt").touch()
            with self.assertRaises(prepare.PreparationError):
                prepare._private_directory(target, base=root)
        repo = Path(prepare.__file__).resolve().parents[2]
        with TemporaryDirectory(dir=repo, prefix="phase-4c-") as directory:
            with self.assertRaises(prepare.PreparationError):
                prepare._private_directory(Path(directory), base=repo)

    def test_acl_change_after_download_prevents_any_output(self):
        payload = csv_bytes([fictional_row(10)])
        run_synthetic = partial(prepare.prepare, expected_size=len(payload), expected_digest=sha256(payload).hexdigest())
        with TemporaryDirectory() as directory:
            output = Path(directory)
            with (patch.object(prepare, "_private_directory", return_value=output),
                  patch.object(prepare, "_check_windows_access", side_effect=[
                      None, prepare.PreparationError("private_output_permissions_not_verified")
                  ]) as acl,
                  patch.object(prepare, "_download", return_value=payload) as download,
                  patch.object(prepare, "prepare", side_effect=run_synthetic),
                  patch.object(prepare.sys, "argv", ["prepare.py", "--approved-careernet-v1.1", str(output)]),
                  redirect_stdout(StringIO()) as console):
                self.assertEqual(prepare.main(), 2)
                self.assertEqual(acl.call_count, 2)
                download.assert_called_once()
            self.assertEqual(list(output.iterdir()), [])
            self.assertEqual(json.loads(console.getvalue()), {
                "status": "stopped", "reason": "private_output_permissions_not_verified"
            })

    def test_cleanup_attempts_all_created_files_and_reports_failure(self):
        with TemporaryDirectory() as directory:
            output = Path(directory)
            retained = output / "privacy_flags.json"
            preexisting = output / "untouched.txt"
            preexisting.touch()
            unlink = Path.unlink

            def fail_one(path, *args, **kwargs):
                if path == retained:
                    raise PermissionError("fictional details")
                return unlink(path, *args, **kwargs)

            with (patch.object(Path, "unlink", autospec=True, side_effect=fail_one),
                  self.assertRaisesRegex(prepare.PreparationError, "^private_output_cleanup_failed$")):
                prepare._store_outputs(output, {}, {"status": "prepared_pending_human_review"},
                                       (), (object(),), ())
            self.assertEqual(set(output.iterdir()), {retained, preexisting})

    def test_cli_gate_precedes_download_and_console_contains_only_aggregate(self):
        payload = csv_bytes([fictional_row(10)])
        run_synthetic = partial(prepare.prepare, expected_size=len(payload), expected_digest=sha256(payload).hexdigest())
        with TemporaryDirectory() as directory:
            output = Path(directory)
            with (patch.object(prepare, "_private_directory", return_value=output),
                  patch.object(prepare, "_check_windows_access") as acl,
                  patch.object(prepare, "_download", return_value=payload) as download,
                  patch.object(prepare, "prepare", side_effect=run_synthetic),
                  patch.object(prepare.sys, "argv", ["prepare.py"]),
                  redirect_stdout(StringIO()) as console):
                self.assertEqual(prepare.main(), 2)
                download.assert_not_called()
                acl.assert_not_called()
                prepare.sys.argv += ["--approved-careernet-v1.1", str(output)]
                acl.side_effect = prepare.PreparationError("private_output_permissions_not_verified")
                self.assertEqual(prepare.main(), 2)
                download.assert_not_called()
                acl.side_effect = None
                self.assertEqual(prepare.main(), 0)
                download.assert_called_once()
            lines = [json.loads(line) for line in console.getvalue().splitlines()]
            self.assertEqual([line["status"] for line in lines],
                             ["explicit_owner_approval_required", "stopped", "prepared_pending_human_review"])
            self.assertNotIn("I would like", console.getvalue())
            self.assertNotIn("81000010", console.getvalue())
            self.assertEqual({path.name for path in output.iterdir()},
                             {"aggregate.json", "provenance.json", "candidate_text.json",
                              "membership.json", "privacy_flags.json"})


if __name__ == "__main__":
    unittest.main()
