"""Exercise the preparation path with fictional CSV rows and no network."""

from contextlib import redirect_stdout
import csv
from datetime import datetime, timezone
from functools import partial
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from research.phase_4c import prepare


RUN_TIME = datetime(2026, 11, 14, 10, tzinfo=timezone.utc)


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
        enriched_draw = prepare.sampling._enriched
        selections = []

        def observe_selection(eligible, general, seed, target):
            enriched, stats = enriched_draw(eligible, general, seed, target)
            selections.append(([row.question_id for row in general], [row.question_id for row in enriched]))
            self.assertEqual(len({row.asker_id for row in general + enriched}), 8)
            groups = {row.question_id: row.asker_id for row in eligible}
            for row in rows:
                self.assertNotEqual(groups[row["question_id"]], row["asker_author_id"])
            self.assertEqual(groups[rows[0]["question_id"]], groups[rows[-2]["question_id"]])
            self.assertEqual(groups[rows[1]["question_id"]], groups[rows[-1]["question_id"]])
            return enriched, stats

        with (patch.object(prepare, "TARGET", 4),
              patch.object(prepare.sampling, "_enriched", side_effect=observe_selection)):
            aggregate = run_preparation(rows)
            shuffled = run_preparation(reversed(rows))
        self.assertEqual(aggregate, shuffled)
        self.assertEqual(selections[0], selections[1])
        self.assertEqual(aggregate["cohorts"]["A_general"]["selected"], 4)
        self.assertEqual(aggregate["cohorts"]["B_provisional"]["candidate_count"], 4)
        self.assertEqual(aggregate["cross_cohort_overlap"], {"question_id": 0, "asker_id": 0})
        self.assertEqual(aggregate["selected_not_nlp_ready"], 8)
        self.assertEqual(aggregate["requires_human_privacy_review_selected"], 8)
        self.assertEqual(aggregate["nlp_ready"], 0)
        self.assertEqual(aggregate["human_review_eligible"], 0)
        serialized = json.dumps(aggregate)
        for row in rows:
            for field in ("question_id", "asker_author_id", "question_title", "question_body"):
                self.assertNotIn(row[field], serialized)

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
        aggregate = run_preparation(rows)
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
        aggregate = run_preparation([
            same, fictional_row(11, question_body=same["question_body"]), almost, fictional_row(14),
        ])
        self.assertEqual(aggregate["duplicates"], {
            "exact_duplicate_questions": 2, "near_duplicate_questions": 3,
            "near_duplicate_pairs": 2, "excluded_duplicate_questions": 3,
        })
        self.assertEqual(aggregate["cohorts"]["A_general"]["selected"], 1)
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
        with patch.object(prepare.sampling, "_general", wraps=prepare.sampling._general) as general:
            aggregate = run_preparation(rows)
        texts = [row.title for row in general.call_args.args[0]]
        self.assertEqual(aggregate["quality"]["excluded_privacy"], 6)
        self.assertEqual(aggregate["excluded_privacy_questions"], 6)
        self.assertEqual(set(aggregate["privacy_flags"]),
                         {"contact", "name_cue", "possible_minor", "location_cue", "school_cue", "sensitive_experience"})
        self.assertEqual(texts, ["I'm not sure about a career in axolotl care"])
        serialized = json.dumps(aggregate)
        for marker in ("Fictionalperson", "fictional.example", "Inventedplace",
                       "Invented Academy", "fictitious disorder", "FICTIONAL_UNUSED", "axolotl"):
            self.assertNotIn(marker, serialized)

    def test_one_high_risk_question_and_its_author_group_are_excluded_before_sampling(self):
        risky = fictional_row(10, question_title="I am 15 years old. Contact me at imaginary@example.invalid.")
        linked = fictional_row(11, asker=10)
        safe = [fictional_row(i) for i in range(12, 21)]
        rows = [linked, risky, risky | {"answer_body": "Second fictional answer"}, *safe]
        with (patch.object(prepare, "TARGET", 4),
              patch.object(prepare.sampling, "_general", wraps=prepare.sampling._general) as chooser):
            aggregate = run_preparation(rows)
        self.assertEqual({r.question_id for r in chooser.call_args.args[0]}, {r["question_id"] for r in safe})
        self.assertEqual(aggregate["status"], "screening_complete_pending_human_review")
        self.assertEqual(aggregate["frame"]["repeated_identical_answer_rows"], 1)
        self.assertEqual(aggregate["privacy_flags"], {"contact": 1, "possible_minor": 1})
        self.assertEqual(aggregate["flagged_privacy_questions"], 1)
        self.assertEqual(aggregate["excluded_privacy_questions"], 2)
        self.assertEqual(aggregate["excluded_privacy_asker_groups"], 1)
        self.assertEqual(aggregate["quality"]["excluded_linked_asker"], 1)
        self.assertEqual(aggregate["cohorts"]["A_general"]["selected"], 4)
        self.assertEqual(aggregate["cohorts"]["B_provisional"]["candidate_count"], 4)
        self.assertEqual(aggregate["requires_human_privacy_review_selected"], 8)
        self.assertEqual(aggregate["nlp_ready"], 0)
        self.assertEqual(aggregate["cross_cohort_overlap"], {"question_id": 0, "asker_id": 0})
        self.assertEqual(prepare._console_summary(aggregate)["high_risk_combination"], "1-4")
        with TemporaryDirectory() as directory:
            root = Path(directory)
            prepare._store_outputs(root, {}, aggregate)
            self.assertEqual({path.name for path in root.iterdir()}, {"provenance.json", "aggregate.json"})
            saved = (root / "aggregate.json").read_text()
            self.assertNotIn("imaginary@example.invalid", saved)
            self.assertNotIn(linked["question_id"], saved)
            self.assertNotIn(linked["asker_author_id"], saved)

    def test_conflicting_question_variants_cannot_hide_privacy_risk(self):
        row = fictional_row(10, question_title="I am 15 years old.")
        conflicting = row | {"question_title": "Contact me at imaginary@example.invalid.",
                             "asker_author_id": fictional_row(11)["asker_author_id"]}
        linked = [fictional_row(12, asker=10), fictional_row(13, asker=11)]
        safe = fictional_row(14)
        with patch.object(prepare.sampling, "_general", wraps=prepare.sampling._general) as chooser:
            aggregate = run_preparation([*linked, row, conflicting, safe])
        self.assertEqual([r.question_id for r in chooser.call_args.args[0]], [safe["question_id"]])
        self.assertEqual(aggregate["frame"]["source_asker_groups"], 3)
        self.assertEqual(aggregate["frame"]["conflicting_question_ids"], 1)
        self.assertEqual(aggregate["excluded_privacy_questions"], 3)
        self.assertEqual(aggregate["excluded_privacy_asker_groups"], 2)
        self.assertEqual(aggregate["privacy_flags"], {"contact": 1, "possible_minor": 1})
        self.assertEqual(aggregate["high_risk_combination"], 1)

    def test_indirect_identity_cues_exclude_questions_before_selection(self):
        rows = [fictional_row(10, question_title="I intern at Imaginary Observatory."),
                fictional_row(11, question_title="I was born on a date that I can share."),
                fictional_row(12)]
        aggregate = run_preparation(rows)
        self.assertEqual(aggregate["privacy_flags"], {"indirect_identity_cue": 2})
        self.assertEqual(aggregate["excluded_privacy_questions"], 2)
        self.assertEqual(aggregate["cohorts"]["A_general"]["selected"], 1)

    def test_widespread_high_risk_or_sensitive_experiences_still_stop(self):
        for title in ("I am 15 years old. Contact me at imaginary@example.invalid.",
                      "I was diagnosed with a fictitious disorder."):
            rows = [fictional_row(i, question_title=title) for i in range(10, 20)] + [fictional_row(20)]
            with self.subTest(title=title), patch.object(prepare.sampling, "_general") as chooser:
                aggregate = run_preparation(rows)
            chooser.assert_not_called()
            self.assertEqual(aggregate["status"], "stopped_for_privacy")
            self.assertEqual(aggregate["privacy_stop_reason"], "widespread_risk")
            self.assertEqual(aggregate["flagged_privacy_questions"], 10)
            self.assertNotIn("cohorts", aggregate)

    def test_small_entirely_unsafe_pool_stops_before_sampling(self):
        rows = [fictional_row(10, question_title="I am a high school sophomore."),
                fictional_row(11, question_title="I was diagnosed with a fictitious disorder.")]
        with patch.object(prepare.sampling, "_general") as chooser:
            aggregate = run_preparation(rows)
        chooser.assert_not_called()
        self.assertEqual(aggregate["status"], "stopped_for_privacy")
        self.assertEqual(aggregate["privacy_stop_reason"], "no_eligible_questions_after_filtering")
        self.assertEqual(aggregate["excluded_privacy_questions"], 2)
        self.assertNotIn("cohorts", aggregate)

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
                  patch.object(prepare, "datetime", wraps=datetime) as clock,
                  patch.object(prepare.sys, "argv", ["prepare.py", "--approved-careernet-v1.1", str(output)]),
                  redirect_stdout(StringIO()) as console):
                clock.now.return_value = RUN_TIME
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
            retained = output / "aggregate.json"
            preexisting = output / "untouched.txt"
            preexisting.touch()
            unlink = Path.unlink

            def fail_one(path, *args, **kwargs):
                if path == retained:
                    raise PermissionError("fictional details")
                return unlink(path, *args, **kwargs)

            with (patch.object(Path, "unlink", autospec=True, side_effect=fail_one),
                  self.assertRaisesRegex(prepare.PreparationError, "^private_output_cleanup_failed$")):
                prepare._store_outputs(output, {}, {"invalid_for_json": object()})
            self.assertEqual(set(output.iterdir()), {retained, preexisting})

    def test_cli_gate_precedes_download_and_console_contains_only_aggregate(self):
        payload = csv_bytes([fictional_row(10), fictional_row(11, question_title="My name is Fictionalperson")])
        run_synthetic = partial(prepare.prepare, expected_size=len(payload), expected_digest=sha256(payload).hexdigest())
        with TemporaryDirectory() as directory:
            output = Path(directory)
            with (patch.object(prepare, "_private_directory", return_value=output),
                  patch.object(prepare, "_check_windows_access") as acl,
                  patch.object(prepare, "_download", return_value=payload) as download,
                  patch.object(prepare, "prepare", side_effect=run_synthetic),
                  patch.object(prepare, "datetime", wraps=datetime) as clock,
                  patch.object(prepare.sys, "argv", ["prepare.py"]),
                  redirect_stdout(StringIO()) as console):
                clock.now.return_value = RUN_TIME
                self.assertEqual(prepare.main(), 2)
                download.assert_not_called()
                acl.assert_not_called()
                prepare.sys.argv += ["--approved-careernet-v1.1", str(output)]
                acl.side_effect = prepare.PreparationError("private_output_permissions_not_verified")
                self.assertEqual(prepare.main(), 2)
                download.assert_not_called()
                acl.side_effect = None
                prepare.sys.argv += ["--retain-until", "2027-02-28"]
                self.assertEqual(prepare.main(), 0)
                download.assert_called_once()
            lines = [json.loads(line) for line in console.getvalue().splitlines()]
            self.assertEqual([line["status"] for line in lines],
                             ["explicit_owner_approval_required", "stopped", "screening_complete_pending_human_review"])
            self.assertNotIn("I would like", console.getvalue())
            self.assertNotIn("81000010", console.getvalue())
            self.assertEqual({path.name for path in output.iterdir()},
                             {"aggregate.json", "provenance.json"})
            for path in output.iterdir():
                saved = path.read_text(encoding="utf-8")
                for marker in ("I would like", "Fictionalperson", "81000010", "94000010", "FICTIONAL_UNUSED"):
                    self.assertNotIn(marker, saved)
            provenance = json.loads((output / "provenance.json").read_text(encoding="utf-8"))
            self.assertEqual(provenance["delete_private_records_by_utc"], "2027-02-28T21:00:00+00:00")
            self.assertEqual(provenance["retention_scope"], "provenance_and_aggregate_only")
            self.assertTrue(provenance["manual_deletion_required"])

    def test_aggregate_retention_defaults_to_30_days_and_never_passes_pilot_cutoff(self):
        self.assertEqual(prepare._retention_deadline(RUN_TIME), datetime(2026, 12, 14, 10, tzinfo=timezone.utc))
        limit = datetime(2027, 2, 28, 21, tzinfo=timezone.utc)
        self.assertEqual(prepare._retention_deadline(datetime(2027, 2, 20, tzinfo=timezone.utc)), limit)
        self.assertEqual(prepare._retention_deadline(RUN_TIME, "2027-02-28"), limit)
        for invalid in ("2027-03-01", "20270228", "28.02.2027"):
            with self.subTest(date=invalid), self.assertRaisesRegex(prepare.PreparationError, "^invalid_retention_date$"):
                prepare._retention_deadline(RUN_TIME, invalid)
        with self.assertRaisesRegex(prepare.PreparationError, "^retention_deadline_elapsed$"):
            prepare._retention_deadline(limit, "2027-02-28")

    def test_invalid_retention_stops_before_download(self):
        with (patch.object(prepare, "_private_directory") as directory,
              patch.object(prepare, "_download") as download,
              patch.object(prepare, "datetime", wraps=datetime) as clock,
              patch.object(prepare.sys, "argv", [
                  "prepare.py", "--approved-careernet-v1.1", "fictional", "--retain-until", "2027-03-01"
              ]),
              redirect_stdout(StringIO()) as console):
            clock.now.return_value = RUN_TIME
            self.assertEqual(prepare.main(), 2)
        directory.assert_not_called()
        download.assert_not_called()
        self.assertEqual(json.loads(console.getvalue()), {"status": "stopped", "reason": "invalid_retention_date"})

    def test_privacy_stop_does_not_extend_retention(self):
        payload = csv_bytes([
            fictional_row(10, question_title="I am 15 years old. Contact me at imaginary@example.invalid.")
        ])
        run_synthetic = partial(prepare.prepare, expected_size=len(payload), expected_digest=sha256(payload).hexdigest())
        with TemporaryDirectory() as directory:
            output = Path(directory)
            with (patch.object(prepare, "_private_directory", return_value=output),
                  patch.object(prepare, "_check_windows_access"),
                  patch.object(prepare, "_download", return_value=payload),
                  patch.object(prepare, "prepare", side_effect=run_synthetic),
                  patch.object(prepare, "datetime", wraps=datetime) as clock,
                  patch.object(prepare.sys, "argv", [
                      "prepare.py", "--approved-careernet-v1.1", str(output), "--retain-until", "2027-02-28"
                  ]),
                  redirect_stdout(StringIO()) as console):
                clock.now.return_value = RUN_TIME
                self.assertEqual(prepare.main(), 3)
            self.assertEqual(json.loads(console.getvalue())["status"], "stopped_for_privacy")
            self.assertNotIn("imaginary@example.invalid", console.getvalue())
            self.assertEqual({path.name for path in output.iterdir()}, {"aggregate.json", "provenance.json"})
            provenance = json.loads((output / "provenance.json").read_text(encoding="utf-8"))
            self.assertEqual(provenance["delete_private_records_by_utc"], "2026-12-14T10:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
