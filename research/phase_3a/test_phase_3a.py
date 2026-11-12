"""Synthetic regressions for the Phase 3A experiment."""

from contextlib import redirect_stderr, redirect_stdout
from hashlib import sha256
from io import BytesIO, StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

from research.phase_3a.corpus import (
    MAX_WORKBOOK_BYTES, MAX_XML_BYTES, CorpusError, Response, _xml, prepare, read_workbook,
)
from research.phase_3a.experiment import (
    DOI, PRIVACY_REVIEW_DECISION, PRIVACY_REVIEW_SCHEMA, PUBLIC_TERMS, SOURCE,
    _canonical_download_time, _local_external, _method, _tfidf, _verified_corpus, main,
)


GENERIC = (
    "I do not feel confident during group discussion because the language practice "
    "and writing support from teachers help students learn during the course"
)


def synthetic_workbook(
    path, response, *, formula=False, external=False, questions=2, xml_prefixes=None, compression=ZIP_DEFLATED,
):
    main_ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    response_xml = "<f>0</f><v>0</v>" if formula else f"<is><t>{escape(response)}</t></is>"
    external_link = '<Relationship Id="r2" TargetMode="External" Target="https://example.test"/>' if external else ""
    parts = {
        "xl/workbook.xml": (
            f'<workbook xmlns="{main_ns}" xmlns:r="{rel_ns}"><sheets>'
            '<sheet name="Synthetic" sheetId="1" r:id="r1"/></sheets></workbook>'
        ),
        "xl/_rels/workbook.xml.rels": (
            '<Relationships><Relationship Id="r1" Target="worksheets/sheet1.xml"/>'
            f"{external_link}</Relationships>"
        ),
        "xl/worksheets/sheet1.xml": (
            f'<worksheet xmlns="{main_ns}"><sheetData>'
            '<row r="1"><c r="B1" t="inlineStr"><is><t>Synthetic theme</t></is></c>'
            '<c r="C1" t="inlineStr"><is><t>What is the synthetic prompt?</t></is></c>'
            f'<c r="D1" t="inlineStr">{response_xml}</c></row>' + "".join(
                f'<row r="{index}"><c r="C{index}" t="inlineStr"><is><t>Synthetic question {index}?</t></is></c></row>'
                for index in range(2, questions + 1)
            ) + "</sheetData></worksheet>"
        ),
    }
    with ZipFile(path, "w", compression) as archive:
        for name, content in parts.items():
            encoding, prefix = (xml_prefixes or {}).get(name, ("utf-8", ""))
            archive.writestr(name, (prefix + content).encode(encoding))


def synthetic_manifest(**fields):
    return {
        "doi": DOI, "version": 1, "license": "CC BY 4.0", "source": SOURCE,
        "downloaded_utc": "2026-01-02T03:04:05Z",
        **fields,
    }


def synthetic_snapshot(directory, responses, *, compression=ZIP_DEFLATED):
    inputs = directory / "inputs"
    inputs.mkdir()
    files = []
    for group, response in enumerate(responses):
        path = inputs / f"synthetic-{group}.xlsx"
        synthetic_workbook(path, response, questions=24, compression=compression)
        payload = path.read_bytes()
        files.append(
            {"local_name": path.name, "file_id": f"synthetic-{group}", "bytes": len(payload),
             "publisher_sha256": sha256(payload).hexdigest()}
        )
    return synthetic_manifest(files=files)


def synthetic_review(directory, manifest, **fields):
    review = {
        "schema": PRIVACY_REVIEW_SCHEMA, "decision": PRIVACY_REVIEW_DECISION,
        "doi": DOI, "version": 1, "expires_utc": "2999-01-01T00:00:00Z",
        "files": manifest["files"], **fields,
    }
    path = directory / "review.json"
    payload = json.dumps(review).encode("utf-8")
    path.write_bytes(payload)
    return path, sha256(payload).hexdigest()


def invoke(directory, manifest, *, review=None, embedding=False):
    provenance = directory / "provenance.json"
    provenance.write_text(json.dumps(manifest), encoding="utf-8")
    output = directory / "results.json"
    args = [
        "experiment", "--inputs", str(directory / "inputs"), "--provenance", str(provenance),
        "--output", str(output), "--source-revision", "a" * 40,
    ]
    if embedding:
        args.extend(["--model-dir", str(directory / "models")])
    if review is not None:
        path, digest = review
        args.extend(["--review-record", str(path), "--trusted-review-sha256", digest])
    stdout, stderr = StringIO(), StringIO()
    with patch("sys.argv", args), redirect_stdout(stdout), redirect_stderr(stderr):
        result = main()
    return result, output, stdout.getvalue(), stderr.getvalue()


class CorpusTests(unittest.TestCase):
    def test_workbook_selects_responses_and_accounts_for_missing(self):
        with TemporaryDirectory() as directory:
            workbook = Path(directory) / "synthetic.xlsx"
            synthetic_workbook(workbook, GENERIC)
            rows, questions = read_workbook(workbook, 7, expected_questions=2)
        self.assertEqual([(row.group, row.question) for row in rows], [(7, 1), (7, 2)])
        self.assertEqual(rows[0].text, GENERIC)
        self.assertNotIn("synthetic prompt", repr(rows))
        self.assertNotIn(GENERIC, repr(rows))
        self.assertIsNone(rows[1].text)
        self.assertEqual(len(questions), 2)

    def test_formula_and_external_link_rejected(self):
        for flags, code in [
            ({"formula": True}, "formula_in_input_columns"),
            ({"external": True}, "external_workbook_relationship"),
        ]:
            with self.subTest(code=code), TemporaryDirectory() as directory:
                workbook = Path(directory) / "synthetic.xlsx"
                synthetic_workbook(workbook, GENERIC, **flags)
                with self.assertRaisesRegex(CorpusError, code):
                    read_workbook(workbook, 0, expected_questions=2)

    def test_changed_workbook_layout_rejected(self):
        with TemporaryDirectory() as directory:
            workbook = Path(directory) / "synthetic.xlsx"
            synthetic_workbook(workbook, GENERIC)
            with self.assertRaisesRegex(CorpusError, "unexpected_question_structure"):
                read_workbook(workbook, 0)

    def test_filter_is_deterministic_and_preserves_negation_and_group(self):
        rows = [
            Response(0, 1, GENERIC + " FictionalUniqueToken"),
            Response(1, 1, GENERIC),
            Response(2, 1, GENERIC),
            Response(2, 2, GENERIC),
            Response(3, 1, "not sure"),
            Response(3, 2, None),
            Response(3, 3, "ruido " * 20),
            Response(3, 4, GENERIC + " https://example.test"),
        ]
        first, report = prepare(rows)
        self.assertEqual((first, report), prepare(rows))
        self.assertEqual([item.group for item in first], [0, 1, 2, 2])
        self.assertTrue(all("not" in item.text.split() for item in first))
        self.assertIn("FictionalUniqueToken", first[0].text)
        self.assertEqual(report["excluded_before_secondary"], {
            "missing": 1, "under_15": 1, "language": 1, "private_context": 1,
        })
        self.assertEqual(report["exact_repeated_occurrences"], 2)
        self.assertEqual(report["subsets"]["15"]["retained"], 4)
        self.assertEqual(report["subsets"]["15"]["groups"], 3)
        self.assertEqual(report["subsets"]["30"]["retained"], 0)
        words = report["secondary_word_counts"]
        self.assertEqual(words["retained_before_normalization"], words["retained_after_normalization"])
        self.assertEqual(report["words"], words["excluded_after_normalization"] + words["retained_after_normalization"])

    def test_direct_identifier_stops_without_leaking_value(self):
        marker = "synthetic-address@example.test"
        with self.assertRaisesRegex(CorpusError, "^possible_direct_identifier$") as stopped:
            prepare([Response(0, 1, marker)])
        self.assertFalse(marker in str(stopped.exception))

    def test_recognizable_obfuscated_emails_stop(self):
        for marker in (
            "cedar at example dot test",
            "cedar [at] example [dot] test",
            "cedar (at) example.test",
            "cedar @ example dot test",
            "cedar\u200b＠example.test",
        ):
            with self.subTest(), self.assertRaisesRegex(CorpusError, "^possible_direct_identifier$") as stopped:
                prepare([Response(0, 1, marker)])
            self.assertFalse(marker in str(stopped.exception))

    def test_repeated_contact_stops_across_three_workbook_groups(self):
        marker = "cedar at example dot test"
        responses = [Response(group, 1, f"{GENERIC} {marker}") for group in range(3)]
        with self.assertRaisesRegex(CorpusError, "^possible_direct_identifier$"):
            prepare(responses)

    def test_recognizable_phone_formats_stop(self):
        for marker in ("+1 (202) 555-0142", "202.555.0143", "two zero two five five five zero one four four"):
            with self.subTest(), self.assertRaisesRegex(CorpusError, "^possible_direct_identifier$") as stopped:
                prepare([Response(0, 1, marker)])
            self.assertFalse(marker in str(stopped.exception))

    def test_unicode_dash_variants_stop_phone_numbers(self):
        for dash in ("\u2010", "\u2011", "\u2012", "\u2013", "\u2014", "\u2212", "\uff0d"):
            phone = f"202{dash}555{dash}0142"
            with self.subTest(), self.assertRaisesRegex(CorpusError, "^possible_direct_identifier$") as stopped:
                prepare([Response(0, 1, f"{GENERIC} {phone}")])
            self.assertFalse(phone in str(stopped.exception))

    def test_unicode_spacing_and_mixed_separators_stop_phone_numbers(self):
        for phone in ("202\u00a0555\u20070142", "+1\u202f(202)\u2009555\u20110142", "202.555\u22120142"):
            with self.subTest(), self.assertRaisesRegex(CorpusError, "^possible_direct_identifier$") as stopped:
                prepare([Response(0, 1, f"{GENERIC} {phone}")])
            self.assertFalse(phone in str(stopped.exception))

    def test_benign_numeric_text_keeps_its_typographic_punctuation(self):
        text = f"{GENERIC}. In the academic year 2024–2025, I read 5–7 pages; each copy cost 12.50."
        rows, report = prepare([Response(0, 1, text)])
        self.assertEqual(rows[0].text, text)
        self.assertEqual(report["subsets"]["15"]["retained"], 1)

    def test_phone_like_year_range_with_contact_cue_still_stops(self):
        with self.assertRaisesRegex(CorpusError, "^privacy_review_required$"):
            prepare([Response(0, 1, f"{GENERIC} and call me at the academic year 2024–2025")])

    def test_suspicious_contact_requires_review_without_echo(self):
        marker = "reach me via the fictional blue channel"
        with self.assertRaisesRegex(CorpusError, "^privacy_review_required$") as stopped:
            prepare([Response(0, 1, marker)])
        self.assertFalse(marker in str(stopped.exception))

    def test_rare_negation_and_nonidentifying_meaning_survive(self):
        positive = "I did enjoy the class because the materials and the teachers can help us learn how to work in the course"
        negative = positive.replace("did enjoy", "did not enjoy")
        unusual = positive + " with counterfactual reasoning and déjà vu"
        rows, report = prepare([Response(0, 1, negative), Response(1, 1, positive), Response(2, 1, unusual)])
        self.assertNotEqual(rows[0].text, rows[1].text)
        self.assertIn("not", rows[0].text.split())
        self.assertIn("counterfactual reasoning and déjà vu", rows[2].text)
        self.assertEqual(report["subsets"]["15"]["retained"], 3)

    def test_repository_paths_rejected(self):
        with self.assertRaisesRegex(CorpusError, "expected_private_local_path"):
            _local_external(Path(__file__))

    def test_cli_suppresses_raw_exception(self):
        stderr = StringIO()
        with (
            patch("sys.argv", ["experiment", "--inputs", "x", "--provenance", "x", "--output", "x", "--source-revision", "a" * 40]),
            patch("research.phase_3a.experiment.run", side_effect=ValueError("synthetic confidential value")),
            redirect_stderr(stderr),
        ):
            self.assertEqual(main(), 2)
        self.assertNotIn("synthetic confidential value", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())


class XmlSecurityTests(unittest.TestCase):
    def test_utf16_internal_entity_expansion_regression(self):
        buffer = BytesIO()
        xml = (
            '<?xml version="1.0" encoding="UTF-16"?>'
            '<!DOCTYPE record [<!ENTITY probe "SYNTHETIC">]><record>&probe;</record>'
        )
        with ZipFile(buffer, "w") as archive:
            archive.writestr("synthetic.xml", xml.encode("utf-16"))
        with ZipFile(buffer) as archive, self.assertRaisesRegex(CorpusError, "^unsafe_xml$"):
            _xml(archive, "synthetic.xml")

    def test_dtd_and_entities_rejected_across_xlsx_parts_and_encodings(self):
        cases = (
            ("xl/workbook.xml", "utf-16", '<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE workbook [<!ENTITY probe "synthetic">]>'),
            ("xl/worksheets/sheet1.xml", "utf-8", "<!DOCTYPE worksheet>"),
            ("xl/_rels/workbook.xml.rels", "utf-8", '<!DOCTYPE Relationships SYSTEM "https://example.test/synthetic.dtd">'),
            ("xl/worksheets/sheet1.xml", "utf-8", '<!DOCTYPE worksheet [<!ENTITY probe SYSTEM "file:///synthetic-unopened">]>'),
        )
        for part, encoding, prefix in cases:
            with self.subTest(part=part, encoding=encoding), TemporaryDirectory() as directory:
                path = Path(directory) / "synthetic.xlsx"
                synthetic_workbook(path, GENERIC, xml_prefixes={part: (encoding, prefix)})
                with self.assertRaisesRegex(CorpusError, "^unsafe_xml$") as stopped:
                    read_workbook(path, 0, expected_questions=2)
                self.assertFalse("synthetic-unopened" in str(stopped.exception))

    def test_valid_utf16_and_ordinary_xml_escaping(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.xlsx"
            answer = GENERIC + " & <ordinary XML>"
            synthetic_workbook(path, answer, xml_prefixes={
                "xl/worksheets/sheet1.xml": ("utf-16", '<?xml version="1.0" encoding="UTF-16"?>'),
            })
            rows, _ = read_workbook(path, 0, expected_questions=2)
        self.assertEqual(rows[0].text, answer)

    def test_shared_string_entities_are_rejected(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.xlsx"
            synthetic_workbook(path, GENERIC)
            with ZipFile(path, "a") as archive:
                archive.writestr(
                    "xl/sharedStrings.xml",
                    '<!DOCTYPE sst [<!ENTITY probe "SYNTHETIC">]><sst>&probe;</sst>',
                )
            with self.assertRaisesRegex(CorpusError, "^unsafe_xml$"):
                read_workbook(path, 0, expected_questions=2)

    def test_malformed_archive_and_xml_fail_without_source_text(self):
        marker = "SYNTHETIC_MALFORMED_MARKER"
        with TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.xlsx"
            path.write_text(marker, encoding="utf-8")
            with self.assertRaisesRegex(CorpusError, "^malformed_workbook$"):
                read_workbook(path, 0)
            synthetic_workbook(path, GENERIC, xml_prefixes={"xl/workbook.xml": ("utf-8", marker)})
            with self.assertRaisesRegex(CorpusError, "^malformed_xml$") as stopped:
                read_workbook(path, 0)
            self.assertFalse(marker in str(stopped.exception))

    def test_size_and_expansion_limits_remain_active(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.xlsx"
            path.write_bytes(b"x" * (MAX_WORKBOOK_BYTES + 1))
            with self.assertRaisesRegex(CorpusError, "^workbook_size_limit$"):
                read_workbook(path, 0)
            synthetic_workbook(path, GENERIC)
            with ZipFile(path, "a", ZIP_DEFLATED) as archive:
                archive.writestr("xl/sharedStrings.xml", b" " * (MAX_XML_BYTES + 1))
            with self.assertRaisesRegex(CorpusError, "^workbook_expansion_limit$"):
                read_workbook(path, 0)


class ManifestTests(unittest.TestCase):
    def test_valid_utc_and_offset_timestamps_are_canonical(self):
        cases = {
            "2026-01-02T03:04:05Z": "2026-01-02T03:04:05Z",
            "2026-01-02T03:04:05+00:00": "2026-01-02T03:04:05Z",
            "2026-01-02T00:04:05+03:30": "2026-01-01T20:34:05Z",
            "2026-01-02T03:04:05.12-01:00": "2026-01-02T04:04:05.120000Z",
        }
        for candidate, expected in cases.items():
            with self.subTest():
                self.assertEqual(_canonical_download_time(candidate), expected)

    def test_invalid_dates_ambiguous_offsets_and_types_are_rejected(self):
        for candidate in (
            "2026-02-30T03:04:05Z", "2026-01-02T03:04:05", "2026-01-02",
            "2026-01-02T03:04:05-00:00", "2026-01-02T03:04:05+00:60", "0001-01-01T00:00:00+01:00",
            "SYNTHETIC_MANIFEST_MARKER", None, 123, True, [], {"time": "synthetic"},
        ):
            with self.subTest(), self.assertRaisesRegex(CorpusError, "^invalid_download_timestamp$"):
                _canonical_download_time(candidate)

    def test_invalid_manifest_value_reaches_neither_model_nor_outputs(self):
        marker = "SYNTHETIC_MANIFEST_MARKER"
        with TemporaryDirectory() as temporary, patch("research.phase_3a.experiment._method") as method:
            result, output, stdout, stderr = invoke(Path(temporary), synthetic_manifest(downloaded_utc=marker))
            self.assertEqual(result, 2)
            self.assertFalse(output.exists())
        method.assert_not_called()
        self.assertEqual(stderr, "Research run stopped: invalid_download_timestamp\n")
        self.assertFalse(marker in stdout + stderr)

    def test_duplicate_timestamp_field_is_ambiguous_and_rejected(self):
        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            manifest = directory / "provenance.json"
            manifest.write_text(
                '{"downloaded_utc":"2026-01-01T00:00:00Z","downloaded_utc":"2026-01-02T00:00:00Z"}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(CorpusError, "^duplicate_manifest_field$"):
                _verified_corpus(directory / "inputs", manifest)

    def test_missing_review_attestation_stops_before_workbook_access(self):
        with TemporaryDirectory() as temporary, patch("research.phase_3a.experiment.read_workbook") as reader:
            directory = Path(temporary)
            manifest = synthetic_snapshot(directory, [GENERIC] * 10)
            result, output, stdout, stderr = invoke(directory, manifest)
            self.assertFalse(output.exists())
        reader.assert_not_called()
        self.assertEqual(result, 2)
        self.assertEqual(stdout, "")
        self.assertEqual(stderr, "Research run stopped: privacy_review_required\n")

    def test_rejected_synthetic_workbook_value_has_no_output_or_model_call(self):
        marker = "cedar at example dot test"
        with TemporaryDirectory() as temporary, patch("research.phase_3a.experiment._method") as method:
            directory = Path(temporary)
            manifest = synthetic_snapshot(directory, [f"{GENERIC} {marker}"] * 3 + [GENERIC] * 7)
            result, output, stdout, stderr = invoke(
                directory, manifest, review=synthetic_review(directory, manifest), embedding=True,
            )
            self.assertFalse(output.exists())
        method.assert_not_called()
        self.assertEqual(result, 2)
        self.assertEqual(stderr, "Research run stopped: possible_direct_identifier\n")
        self.assertFalse(marker in stdout + stderr)


class TrustedReviewTests(unittest.TestCase):
    def assert_stopped(self, directory, manifest, error, *, review=None, marker=None, before_parse=True):
        with (
            patch("research.phase_3a.experiment._method") as method,
            patch("research.phase_3a.experiment._local_embeddings") as embeddings,
            patch("research.phase_3a.experiment.read_workbook", wraps=read_workbook) as reader,
        ):
            result, output, stdout, stderr = invoke(directory, manifest, review=review, embedding=True)
        method.assert_not_called()
        embeddings.assert_not_called()
        if before_parse:
            reader.assert_not_called()
        self.assertEqual(result, 2)
        self.assertFalse(output.exists())
        self.assertEqual(stdout, "")
        self.assertEqual(stderr, f"Research run stopped: {error}\n")
        if marker is not None:
            self.assertFalse(marker in stdout + stderr)

    def test_unchanged_snapshot_with_independent_review_is_accepted(self):
        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            manifest = synthetic_snapshot(directory, [GENERIC] * 10)
            review = synthetic_review(directory, manifest)
            manifest["files"].reverse()
            with patch("research.phase_3a.experiment._method", return_value=({}, {})) as method:
                result, output, stdout, stderr = invoke(directory, manifest, review=review)
                report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual((result, stderr), (0, ""))
            self.assertEqual(method.call_count, 1)
            self.assertEqual(report["corpus"]["workbook_groups"], 10)
            self.assertFalse(review[1] in stdout or GENERIC in stdout)

    def test_changed_workbook_and_refreshed_manifest_cannot_extend_old_review(self):
        marker = "SYNTHETIC_UNREVIEWED_RESPONSE"
        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            manifest = synthetic_snapshot(directory, [GENERIC] * 10)
            review = synthetic_review(directory, manifest)
            entry = manifest["files"][0]
            path = directory / "inputs" / entry["local_name"]
            synthetic_workbook(path, f"{GENERIC} {marker}", questions=24)
            self.assert_stopped(directory, manifest, "workbook_integrity_mismatch", review=review, marker=marker)

            payload = path.read_bytes()
            entry.update(bytes=len(payload), publisher_sha256=sha256(payload).hexdigest())
            self.assert_stopped(directory, manifest, "privacy_review_inventory_mismatch", review=review, marker=marker)

            synthetic_review(directory, manifest)
            self.assert_stopped(directory, manifest, "privacy_review_integrity_mismatch", review=review, marker=marker)

    def test_same_size_substitution_is_rejected(self):
        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            manifest = synthetic_snapshot(directory, [GENERIC] * 10, compression=ZIP_STORED)
            review = synthetic_review(directory, manifest)
            entry = manifest["files"][0]
            path = directory / "inputs" / entry["local_name"]
            synthetic_workbook(
                path, GENERIC.replace("confident", "uncertain"), questions=24, compression=ZIP_STORED,
            )
            self.assertEqual(path.stat().st_size, entry["bytes"])
            self.assertNotEqual(sha256(path.read_bytes()).hexdigest(), entry["publisher_sha256"])
            self.assert_stopped(directory, manifest, "workbook_integrity_mismatch", review=review)

    def test_added_and_missing_files_invalidate_exact_inventory(self):
        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            manifest = synthetic_snapshot(directory, [GENERIC] * 10)
            review = synthetic_review(directory, manifest)
            extra = directory / "inputs" / "synthetic-extra.xlsx"
            synthetic_workbook(extra, GENERIC, questions=24)
            self.assert_stopped(directory, manifest, "workbook_inventory_mismatch", review=review)
            extra.unlink()
            (directory / "inputs" / manifest["files"][0]["local_name"]).unlink()
            self.assert_stopped(directory, manifest, "workbook_inventory_mismatch", review=review)

    def test_invalid_absent_or_expired_review_record_is_rejected(self):
        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            manifest = synthetic_snapshot(directory, [GENERIC] * 10)
            review = synthetic_review(directory, manifest, expires_utc="2000-01-01T00:00:00Z")
            self.assert_stopped(directory, manifest, "privacy_review_expired", review=review)
            review = synthetic_review(directory, manifest, expires_utc="SYNTHETIC_PRIVATE_FIELD")
            self.assert_stopped(directory, manifest, "invalid_privacy_review", review=review, marker="SYNTHETIC_PRIVATE_FIELD")
            review = synthetic_review(directory, manifest, files=[])
            self.assert_stopped(directory, manifest, "invalid_privacy_review", review=review)
            review[0].unlink()
            self.assert_stopped(directory, manifest, "invalid_privacy_review", review=review)

    def test_manifest_approval_fields_cannot_select_or_replace_trust(self):
        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            manifest = synthetic_snapshot(directory, [GENERIC] * 10)
            review = synthetic_review(directory, manifest)
            manifest.update(
                approved=True, privacy_review=PRIVACY_REVIEW_DECISION,
                review_record=str(review[0]), trusted_review_sha256=review[1],
            )
            self.assert_stopped(directory, manifest, "privacy_review_required")
            self.assert_stopped(directory, manifest, "invalid_privacy_review", review=(review[0], "SYNTHETIC_BAD_PIN"))

    def test_review_must_be_separate_from_input_directory_and_manifest(self):
        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            manifest = synthetic_snapshot(directory, [GENERIC] * 10)
            review_path, digest = synthetic_review(directory, manifest)
            embedded = directory / "inputs" / "review.json"
            review_path.replace(embedded)
            self.assert_stopped(directory, manifest, "expected_separate_privacy_review", review=(embedded, digest))
            self.assert_stopped(
                directory, manifest, "expected_separate_privacy_review", review=(directory / "provenance.json", digest),
            )

    def test_parser_receives_the_verified_bytes_even_if_disk_content_changes(self):
        marker = "SYNTHETIC_REPLACEMENT_AFTER_VERIFICATION"
        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            manifest = synthetic_snapshot(directory, [GENERIC] * 10)
            review = synthetic_review(directory, manifest)
            path = directory / "inputs" / manifest["files"][0]["local_name"]
            verified = path.read_bytes()

            def parse(payload, group):
                if group == 0:
                    synthetic_workbook(path, f"{GENERIC} {marker}", questions=24)
                    self.assertEqual(payload, verified)
                return read_workbook(payload, group)

            with (
                patch("research.phase_3a.experiment.read_workbook", side_effect=parse),
                patch("research.phase_3a.experiment._method", return_value=({}, {})) as method,
            ):
                result, output, stdout, stderr = invoke(directory, manifest, review=review)
            self.assertEqual((result, stderr), (0, ""))
            self.assertEqual(method.call_args.args[0][0].text, GENERIC)

    def test_review_does_not_override_repeated_unicode_contact_stop(self):
        phone = "202\u2011555\u20110142"
        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            manifest = synthetic_snapshot(directory, [f"{GENERIC} {phone}"] * 3 + [GENERIC] * 7)
            review = synthetic_review(directory, manifest)
            self.assert_stopped(
                directory, manifest, "possible_direct_identifier", review=review, marker=phone, before_parse=False,
            )


class MethodTests(unittest.TestCase):
    def test_tfidf_retains_negation_observed_once(self):
        positive = GENERIC.replace("do not feel", "do feel")
        rows, _ = prepare([Response(0, 1, GENERIC), Response(1, 1, positive), Response(2, 1, positive)])
        matrix, terms = _tfidf(rows)
        column = list(terms).index("not")
        self.assertGreater(matrix[0, column], 0)
        self.assertEqual(matrix[1, column], 0)

    def test_both_paths_receive_the_same_reviewed_ordered_records(self):
        with (
            TemporaryDirectory() as temporary,
            patch("research.phase_3a.experiment._method", side_effect=[({}, {"synthetic": True}), ({}, {})]) as method,
            patch("research.phase_3a.experiment._local_embeddings", return_value=object()) as embeddings,
        ):
            directory = Path(temporary)
            manifest = synthetic_snapshot(directory, [f"{GENERIC} Synthetic group {i}" for i in range(10)])
            manifest["downloaded_utc"] = "2026-01-02T03:04:05+03:00"
            manifest["extra"] = "SYNTHETIC_UNLISTED_FIELD"
            result, output, stdout, stderr = invoke(
                directory, manifest, review=synthetic_review(directory, manifest), embedding=True,
            )
            report = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual((result, stderr), (0, ""))
        classical_rows, classical_vectors, _ = method.call_args_list[0].args
        embedding_rows, embedding_vectors, _ = method.call_args_list[1].args
        self.assertIs(classical_rows, embedding_rows)
        self.assertEqual([row.group for row in classical_rows], list(range(10)))
        self.assertIsNone(classical_vectors)
        self.assertIs(embedding_vectors, embeddings.return_value)
        self.assertEqual(embeddings.call_args.args[0], [row.text for row in classical_rows])
        self.assertEqual(report["dataset"]["downloaded_utc"], "2026-01-02T00:04:05Z")
        self.assertEqual(report, json.loads(stdout))
        self.assertFalse("SYNTHETIC_UNLISTED_FIELD" in stdout or GENERIC in stdout)

    def test_nmf_comparison_aggregates_and_omits_unapproved_terms(self):
        from threadpoolctl import threadpool_limits

        base = "I learn and do not stop because the class can help us in the course"
        rows, _ = prepare([
            Response(group, question, (base + " " + topic) * 2)
            for group in range(4)
            for question, topic in enumerate((
                "language learning language practice communication repeatedsecret",
                "writing assignments writing feedback support repeatedsecret",
                "support peers confidence classmates participation repeatedsecret",
            ), 1)
        ])
        with threadpool_limits(limits=2):
            report, _ = _method(rows, None, common_prompts=True)
        fit = report["subsets"]["30"]["2"]
        self.assertEqual(fit["status"], "ran")
        self.assertEqual(sum(fit["sizes"]) + fit["zero_input_rows"], 12)
        self.assertEqual(fit["leave_one_workbook_out_attempts"], 4)
        self.assertTrue(all(term in PUBLIC_TERMS for terms in fit["terms"] for term in terms))
        self.assertNotIn("repeatedsecret", str(report))

    def test_methods_do_not_force_tiny_sample(self):
        rows, _ = prepare([Response(group, 1, GENERIC) for group in range(3)])
        report, fits = _method(rows, None, common_prompts=True)
        self.assertFalse(fits)
        self.assertEqual(report["subsets"]["15"]["2"]["status"], "insufficient_rows_groups_or_terms")


if __name__ == "__main__":
    unittest.main()
