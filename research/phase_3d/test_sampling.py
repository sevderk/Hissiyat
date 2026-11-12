from hashlib import sha256
import json
import unittest

from research.phase_3d.sampling import SamplingError, sample_synthetic


GENERAL = "Which subjects appear in the fictional orbital college catalogue?"
UNCERTAIN = "I am unsure whether to take a fictional lunar job or finish my degree."


def question(number, *, asker=None, title=GENERAL, body="", created_at=None):
    return {
        "question_id": f"synthetic-question-{number}",
        "asker_id": f"synthetic-asker-{number if asker is None else asker}",
        "title": title,
        "body": body,
        "created_at": created_at,
    }


def sample(rows, **options):
    return sample_synthetic(rows, **({"min_words": 1} | options))


class SamplingTests(unittest.TestCase):
    def test_answer_expansion_deduplicates_question_ids(self):
        rows = [question(1), question(1, title=f" {GENERAL} "), question(2)]
        report = sample(rows).aggregate
        self.assertEqual(report["input"]["row_count"], 3)
        self.assertEqual(report["input"]["unique_question_ids"], 2)
        self.assertEqual(report["frame_reason_counts"]["repeated_identical_rows"], 1)
        self.assertEqual(report["general"]["selected"], 2)

    def test_conflicting_records_are_quarantined_as_a_whole(self):
        for changed in (question(1, body=UNCERTAIN), question(1, asker=2),
                        question(1, created_at="2024-08-20")):
            with self.subTest(field_count=len(changed)):
                rows = [question(1), changed, question(1), question(3)]
                result = sample(rows)
                self.assertEqual(result.aggregate["frame_reason_counts"]["conflicting_question_id"], 1)
                self.assertEqual(result.aggregate["frame_reason_counts"]["repeated_identical_rows"], 1)
                self.assertEqual([m.question_id for m in result.general_membership], ["synthetic-question-3"])

    def test_general_draw_has_one_question_per_asker(self):
        result = sample([question(1), question(2, asker=1), question(3)], general_target=3)
        self.assertEqual(result.aggregate["general"]["shortfall"], 1)
        self.assertEqual(result.aggregate["general"]["reason_counts"]["alternate_same_asker"], 1)
        self.assertEqual({m.asker_id for m in result.general_membership}, {"synthetic-asker-1", "synthetic-asker-3"})
        self.assertEqual(sorted(m.within_asker_frame_size for m in result.general_membership), [1, 2])

    def test_same_seed_keeps_both_draws_stable_when_input_is_reordered(self):
        rows = [question(i, asker=i // 2, title=UNCERTAIN,
                         created_at=f"{2019 + i % 6}-06-15") for i in range(40)]
        options = {"seed": 5, "general_target": 5, "enriched_target": 6, "temporal_strata": True}
        original = sample(rows, **options)
        self.assertEqual(original, sample(rows, **options))
        self.assertEqual(original, sample(list(reversed(rows)), **options))
        self.assertEqual(len(original.enriched_candidates), 6)

    def test_different_seeds_can_change_selected_questions(self):
        rows = [question(i) for i in range(30)]
        a = sample(rows, seed=1, general_target=5)
        b = sample(rows, seed=2, general_target=5)
        self.assertNotEqual({m.question_id for m in a.general_membership},
                            {m.question_id for m in b.general_membership})
        self.assertEqual(a.aggregate["input"], b.aggregate["input"])

    def test_enrichment_reports_shortfall_without_filling_with_general_advice(self):
        rows = [question(i) for i in range(20)]
        result = sample(rows, general_target=2, enriched_target=5)
        self.assertEqual(result.enriched_candidates, ())
        self.assertEqual(result.aggregate["uncertainty_enriched_candidates"]["candidate_shortfall"], 5)
        self.assertEqual(result.aggregate["uncertainty_enriched_candidates"]["reason_counts"]
                         ["no_uncertainty_screen_signal"], 20)

    def test_no_question_or_asker_overlaps_between_cohorts(self):
        rows = [question(i, asker=i // 2, title=UNCERTAIN) for i in range(4)]
        result = sample(rows, general_target=1, enriched_target=2)
        self.assertEqual(result.aggregate["overlap"], {"question_ids": 0, "asker_ids": 0})
        self.assertNotEqual(result.general_membership[0].asker_id, result.enriched_candidates[0].asker_id)
        enriched = result.aggregate["uncertainty_enriched_candidates"]
        self.assertEqual(enriched["review_status"], "pending_context_review")
        self.assertEqual(enriched["candidate_shortfall"], 1)
        self.assertEqual(enriched["reason_counts"], {
            "no_uncertainty_screen_signal": 0, "general_question_overlap_excluded": 1,
            "general_asker_overlap_excluded": 1, "alternate_same_asker": 1,
            "candidate_not_drawn": 0, "pending_context_review": 1,
        })

    def test_timestamp_strata_distinguish_missing_ambiguous_and_naive(self):
        values = [None, "03/04/2024", "2024-02-30", "2022-12-31T23:30:00-00:00",
                  "2024-01-01T00:30:00+00:99", "2022-12-31T23:30:00",
                  "2023-01-01T00:30:00+01:00", "2023-01-02"]
        result = sample([question(i, created_at=value) for i, value in enumerate(values)], temporal_strata=True)
        self.assertEqual(result.aggregate["eligible_timestamp_status_counts"], {
            "missing": 1, "invalid_or_ambiguous": 4, "local_time_unknown_zone": 1,
            "offset_datetime": 1, "date_only": 1,
        })
        members = {member.question_id: member.stratum for member in result.general_membership}
        self.assertEqual(members["synthetic-question-5"], "2020-2022")
        self.assertEqual(members["synthetic-question-6"], "2023-2025")
        self.assertEqual(members["synthetic-question-3"], "unknown_date")
        self.assertEqual(members["synthetic-question-4"], "unknown_date")

    def test_general_manifest_records_conditional_stratum_probabilities(self):
        dates = ["2018-01-01"] * 6 + ["2021-01-01"] * 2 + [None]
        result = sample([question(i, created_at=when) for i, when in enumerate(dates)],
                        general_target=5, temporal_strata=True)
        self.assertEqual(result.aggregate["general"]["strata"], {
            "2011-2019": {"representative_frame_size": 6, "draw_size": 3},
            "2020-2022": {"representative_frame_size": 2, "draw_size": 1},
            "unknown_date": {"representative_frame_size": 1, "draw_size": 1},
        })

    def test_small_draw_falls_back_to_an_unstratified_design(self):
        result = sample([question(1, created_at="2016-01-01"), question(2)],
                        general_target=1, temporal_strata=True)
        self.assertTrue(result.aggregate["design"]["temporal_strata_requested"])
        self.assertFalse(result.aggregate["general"]["temporal_strata_used"])
        self.assertEqual(result.aggregate["general"]["strata"], {
            "all": {"representative_frame_size": 2, "draw_size": 1},
        })

    def test_empty_text_and_short_repeated_title_have_distinct_reasons(self):
        result = sample([question(1, title="", body=" "), question(2, title="Short text", body="Short text")],
                        min_words=3)
        self.assertEqual(result.aggregate["frame_reason_counts"], {
            "repeated_identical_rows": 0, "conflicting_question_id": 0, "empty_question_text": 1,
            "below_minimum_words": 1, "eligible_question": 0,
        })
        self.assertEqual(result.general_membership, ())

    def test_missing_malformed_or_extra_fields_fail_with_fixed_codes(self):
        malformed = [
            ({k: v for k, v in question(1).items() if k != "body"}, "invalid_row_schema"),
            (question(1) | {"answer": "fixture-secret"}, "invalid_row_schema"),
            (question(1) | {"question_id": "fixture-secret"}, "expected_synthetic_question_id"),
            (question(1) | {"asker_id": None}, "expected_synthetic_asker_id"),
            (question(1) | {"title": None}, "invalid_question_text"),
            (question(1) | {"created_at": 2032}, "invalid_timestamp_field"),
        ]
        for row, code in malformed:
            with self.subTest(code=code), self.assertRaisesRegex(SamplingError, f"^{code}$"):
                sample([row])

    def test_invalid_sampling_options_fail_closed(self):
        for options in ({"seed": True}, {"general_target": 0}, {"enriched_target": 201},
                        {"temporal_strata": "yes"}, {"min_words": 0}):
            with self.subTest(options=options), self.assertRaisesRegex(SamplingError, "^invalid_sampling_options$"):
                sample([], **options)

    def test_manifest_records_reference_and_separate_synthetic_fingerprint(self):
        row = question(1, title="Fictional title")
        result = sample([row])
        manifest = result.aggregate
        canonical = b'["synthetic-question-1","synthetic-asker-1","Fictional title","",null]'
        self.assertEqual(manifest["schema"], "hissiyat_phase_3d_sampling_v1")
        self.assertEqual(manifest["input"]["kind"], "synthetic")
        self.assertEqual(manifest["input"]["canonical_row_multiset_sha256"], sha256(canonical).hexdigest())
        self.assertNotEqual(manifest["input"], sample([row, row]).aggregate["input"])
        self.assertEqual(manifest["reference_dataset_not_processed"], {
            "publisher": "Renaissance Philanthropy", "version": "v1.1", "license": "CC BY 4.0",
            "source": "https://github.com/RenaissancePhilanthropy/careernet-data/releases/tag/v1.1",
            "filename": "general_public_v1.1.csv",
            "publisher_sha256": "4e1583b68348ef741ca4abd8e52dec323c6cfc0bf761b15047c308370afb3017",
        })

    def test_aggregate_output_never_copies_private_values_or_merges_cohorts(self):
        marker = "confidential fictional text"
        rows = [question(i, asker=i // 2, title=UNCERTAIN, body=marker, created_at="2097-11-23") for i in range(12)]
        result = sample(rows, general_target=2, enriched_target=3, temporal_strata=True)
        aggregate = result.aggregate
        self.assertEqual(aggregate["general"]["selected"], 2)
        self.assertEqual(aggregate["uncertainty_enriched_candidates"]["candidate_count"], 3)
        for cohort in ("general", "uncertainty_enriched_candidates"):
            self.assertEqual(sum(aggregate[cohort]["reason_counts"].values()), 12)
        for output in (json.dumps(aggregate), repr(result), repr(result.general_membership),
                       repr(result.enriched_candidates)):
            for secret in (marker, UNCERTAIN, "synthetic-question-", "synthetic-asker-", "2097-11-23"):
                self.assertNotIn(secret, output)


if __name__ == "__main__":
    unittest.main()
