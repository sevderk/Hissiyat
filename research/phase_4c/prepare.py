"""Prepare pinned CareerNet candidates locally, before human review or NLP."""

from collections import Counter, defaultdict
import csv
from dataclasses import replace
from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
import html
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import unicodedata
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from research.phase_3d import sampling


REFERENCE = sampling.CAREERNET_REFERENCE
SIZE = 17_511_450
URL = "https://github.com/RenaissancePhilanthropy/careernet-data/releases/download/v1.1/" + REFERENCE["filename"]
SOURCE_FIELDS = ("question_id", "asker_author_id", "question_title", "question_body", "question_added_at")
EXPECTED_HEADER = frozenset("""
    answer_id answer_body answer_added_at answer_score answerer_id answerer_location
    question_id question_title question_body question_added_at question_score asker_author_id
    asker_location question_tagnames question_views ScenarioLabels correctness completeness
    coherency explore_options take_action understanding_purpose validation_support find_resources
    navigate_constraints compare_options unclear_goal soc_code Split reasoning_label
""".split())
SCHEMA = "hissiyat_careernet_preparation_v3"
SEED = 42
MIN_WORDS = 30
TARGET = 200
MAX_ROWS = 10_000
MAX_QUESTIONS = 4_000
RETENTION_DAYS = 30
PILOT_LAST_DAY = date(2027, 2, 28)
PILOT_LOCAL_TIME = timezone(timedelta(hours=3))
MARKUP = re.compile(r"</?[A-Za-z][A-Za-z0-9:-]*(?:\s[^<>]{0,480})?\s*/?>")
ID = re.compile(r"[1-9][0-9]{0,17}")
MONTH_NAMES = "january february march april may june july august september october november december".split()
MONTHS = {name: index for index, month in enumerate(MONTH_NAMES, 1) for name in (month, month[:3])}
MONTHS["sept"] = 9
SOURCE_DATE = re.compile(
    r"([A-Za-z]+)\.? (\d{1,2}), (\d{4}),? (1[0-2]|0?[1-9]):([0-5]\d) (AM|PM)", re.IGNORECASE
)
ENGLISH = frozenset("""
    a an and are as at be but by can could do for from had has have how i if in is it
    me my not of on or our should so that the their them they this to was we were what
    when where which will with would you your
""".split())
RISK_PATTERNS = {
    "contact": re.compile(
        r"(?<![\w.%+-])[\w.%+-]{1,64} *(?:@|\[at\]|\(at\)| at ) *"
        r"[\w-]{1,63}(?:\.[\w-]{1,63}){0,5} *(?:\.|\[dot\]|\(dot\)| dot ) *[a-z]{2,24}\b"
        r"|(?<!\w)(?:\+?1[ .-]?)?(?:\(\d{3}\)[ .-]?\d{3}|\d{3}[-.]\d{3})[-. ]\d{4}\b"
        r"|\b(?:call|text|email|message|contact|reach) me (?:at|on|via)\b"
        r"|(?<!\w)@[\w.]{2,}|https?://|www\.", re.IGNORECASE,
    ),
    "name_cue": re.compile(r"\b(?:my (?:full |legal )?name is|i go by)\s+\w", re.IGNORECASE),
    "school_cue": re.compile(
        r"\b(?:[A-Z][a-z'-]+\s+){1,4}(?:High School|Middle School|Academy|University|College)\b"
        r"|\b(?:University|College) of [A-Z][a-z'-]+\b"
    ),
    "location_cue": re.compile(r"\b(?i:i live in|i am from|i'm from|i moved to|i am based in) [A-Z][\w'-]+"),
    "indirect_identity_cue": re.compile(
        r"\b(?i:i work at|i intern at|i am employed by|i volunteer at) [A-Z][\w'-]+"
        r"|\b(?i:my (?:home |street )?address is|my date of birth is|i was born on)\b"
    ),
    "possible_minor": re.compile(
        r"\b(?:i am|i'm|aged)\s+(?:1[0-7]|[6-9])(?:\s+years? old\b|[- ]year[- ]old\b|\s+and in\b|[.,;!?]|$)"
        r"|\b(?:i am|i'm) (?:a |in )?(?:high school (?:student|freshman|sophomore|junior|senior)"
        r"|(?:[6-9]|1[012])(?:st|nd|rd|th) grad(?:e|er))\b", re.IGNORECASE,
    ),
    "sensitive_experience": re.compile(
        r"\b(?:diagnosed with|my diagnosis|my disability|depression|suicid\w*|self[- ]harm"
        r"|sexual assault|domestic abuse|homeless\w*|undocumented|immigration status"
        r"|deport\w*|mental health condition|chronic illness)\b", re.IGNORECASE,
    ),
    "credential_cue": re.compile(
        r"\b(?:social security number|ssn|credit card number|bank account number|password)"
        r"\s*(?:is|:|=)\s*(?:[0-9][ -]?){8,20}\b", re.IGNORECASE,
    ),
}


class PreparationError(ValueError):
    """A fixed non-disclosing error code."""


def _plain(value):
    visible = MARKUP.sub(" ", html.unescape(value))
    return " ".join("".join(char for char in visible if unicodedata.category(char) != "Cf").split())


def _source_calendar(value):
    match = SOURCE_DATE.fullmatch(value)
    if not match:
        return sampling._calendar(value or None)[0], value or None
    month, day, year, hour, minute, meridiem = match.groups()
    try:
        parsed = datetime(int(year), MONTHS[month.lower()], int(day),
                          int(hour) % 12 + 12 * (meridiem.upper() == "PM"), int(minute))
    except (KeyError, ValueError):
        return "invalid_or_ambiguous", value
    return "local_time_unknown_zone", parsed.isoformat()


def _read_questions(payload):
    rows, year_counts, counts = defaultdict(set), Counter(), Counter()
    asker_groups = {}
    stream = io.StringIO(payload.decode("utf-8-sig"), newline="")
    reader = csv.reader(stream, strict=True)
    header = next(reader, ())
    if len(header) != len(EXPECTED_HEADER) or set(header) != EXPECTED_HEADER:
        raise PreparationError("source_header_mismatch")
    columns = [header.index(field) for field in SOURCE_FIELDS]
    for row_count, row in enumerate(reader, 1):
        counts["answer_level_rows"] += 1
        if row_count > MAX_ROWS or len(row) != len(header):
            raise PreparationError("invalid_source_csv")
        question, asker, title, body, when = (row[index] for index in columns)
        del row
        if ("\0" in title or "\0" in body or len(title) > 4_000 or len(body) > 40_000
                or len(when) > 64 or "\0" in when):
            raise PreparationError("invalid_source_question_fields")
        question, asker, when = question.strip(), asker.strip(), when.strip()
        if not ID.fullmatch(question):
            raise PreparationError("invalid_question_id")
        if asker and not ID.fullmatch(asker):
            raise PreparationError("invalid_asker_id")
        # The source asker ID stays in this lookup, separate from question text.
        group = str(asker_groups.setdefault(asker, len(asker_groups) + 1)) if asker else ""
        del asker
        variant = (group, " ".join(title.split()), " ".join(body.split()), when)
        if variant in rows[question]:
            counts["repeated_identical_answer_rows"] += 1
        rows[question].add(variant)
        if len(rows) > MAX_QUESTIONS:
            raise PreparationError("question_bound_exceeded")
    stream.close()
    counts["source_asker_groups"] = len(asker_groups)
    del asker_groups
    questions, conflict_flags = [], {}
    excluded_groups = set()
    status_counts = Counter()
    for question, variants in sorted(rows.items()):
        if len(variants) != 1:
            counts["conflicting_question_ids"] += 1
            flags = set()
            for _, title, body, _ in variants:
                flags.update(_question_privacy(title, body, _plain(title), _plain(body)))
            if flags:
                conflict_flags[question] = flags
                excluded_groups.update(group for group, _, _, _ in variants if group)
            continue
        asker, title, body, when = next(iter(variants))
        status, created_at = _source_calendar(when)
        status_counts[status] += 1
        if status not in {"missing", "invalid_or_ambiguous"}:
            year_counts[created_at[:4]] += 1
        questions.append(sampling._Question(question, asker, title, body, created_at))
    counts["distinct_question_ids"] = len(rows)
    counts["available_asker_groups"] = len({row.asker_id for row in questions if row.asker_id})
    return (questions, conflict_flags, excluded_groups, dict(counts),
            dict(status_counts), dict(sorted(year_counts.items())))


def _privacy_reasons(text):
    projected = unicodedata.normalize("NFKC", text).replace("’", "'")
    projected = re.sub(r"[\u2010-\u2015\u2212]", "-", projected)
    return {name for name, pattern in RISK_PATTERNS.items() if pattern.search(projected)}


def _question_privacy(raw_title, raw_body, title, body):
    return _privacy_reasons(f"{title} {body}".strip()) | _privacy_reasons(html.unescape(f"{raw_title} {raw_body}"))


def _quality_frame(questions, review_flags, excluded_groups):
    normalized = []
    for original in questions:
        row = replace(original, title=_plain(original.title), body=_plain(original.body))
        flags = _question_privacy(original.title, original.body, row.title, row.body)
        if flags:
            review_flags[row.question_id] = flags
            if row.asker_id:
                excluded_groups.add(row.asker_id)
        normalized.append(row)

    eligible = []
    counts, bins = Counter(), Counter()
    for row in normalized:
        text = row.title if row.title == row.body else f"{row.title} {row.body}".strip()
        words = [word.casefold() for word in sampling.WORD.findall(text)]
        size = len(words)
        bins[next(label for label, upper in (("0", 0), ("1-14", 14), ("15-29", 29),
                                             ("30-49", 49), ("50-99", 99), ("100+", 50_000))
                  if size <= upper)] += 1
        vocabulary = set(words)
        english_signal = len(vocabulary & ENGLISH) >= 2 and sum(word in ENGLISH for word in words) >= size * 0.14
        counts["english_signal" if english_signal else "language_uncertain"] += 1
        counts["missing_title"] += not row.title
        counts["missing_body"] += not row.body
        counts["missing_asker"] += not row.asker_id
        if row.question_id in review_flags:
            counts["excluded_privacy"] += 1
        elif row.asker_id in excluded_groups:
            counts["excluded_linked_asker"] += 1
        elif not row.asker_id:
            counts["excluded_missing_asker"] += 1
        elif size < MIN_WORDS:
            counts["excluded_short_or_empty"] += 1
        elif not english_signal:
            counts["excluded_language_uncertain"] += 1
        else:
            eligible.append((row, text.casefold(), vocabulary))
    return eligible, dict(counts), dict(bins)


def _exclude_duplicates(eligible):
    exact = Counter(text for _, text, _ in eligible)
    exact_ids = {row.question_id for row, text, _ in eligible if exact[text] > 1}
    near_ids, near_pairs = set(), 0
    # The pinned frame bounds this exhaustive comparison to fewer than 8 million pairs.
    for index, (row, text, left) in enumerate(eligible):
        if len(left) < 10:
            continue
        for other_index in range(index + 1, len(eligible)):
            other, other_text, right = eligible[other_index]
            if text == other_text or min(len(left), len(right)) < 10:
                continue
            if 100 * min(len(left), len(right)) < 90 * max(len(left), len(right)):
                continue
            intersection = len(left & right)
            if 100 * intersection >= 90 * (len(left) + len(right) - intersection):
                near_pairs += 1
                near_ids.update((row.question_id, other.question_id))
    excluded = exact_ids | near_ids
    return [row for row, _, _ in eligible if row.question_id not in excluded], {
        "exact_duplicate_questions": len(exact_ids), "near_duplicate_questions": len(near_ids),
        "near_duplicate_pairs": near_pairs, "excluded_duplicate_questions": len(excluded),
    }


def prepare(payload, *, expected_size=SIZE, expected_digest=REFERENCE["publisher_sha256"]):
    """Screen and select questions in memory, returning only aggregate results."""
    aggregate, _, _, _ = _screen_and_select(payload, expected_size=expected_size, expected_digest=expected_digest)
    return aggregate


def _screen_and_select(payload, *, expected_size=SIZE, expected_digest=REFERENCE["publisher_sha256"]):
    """Share the in-memory selection with local research tools."""
    if len(payload) != expected_size or sha256(payload).hexdigest() != expected_digest:
        raise PreparationError("source_integrity_mismatch")
    try:
        questions, review_flags, excluded_groups, frame, dates, years = _read_questions(payload)
    except (UnicodeError, csv.Error):
        raise PreparationError("invalid_source_csv") from None
    eligible, quality, lengths = _quality_frame(questions, review_flags, excluded_groups)
    risks = dict(Counter(flag for flags in review_flags.values() for flag in flags))
    high_risk = sum(
        "credential_cue" in flags or {"possible_minor", "contact"} <= flags
        or {"possible_minor", "name_cue", "school_cue"} <= flags
        for flags in review_flags.values()
    )
    privacy = {
        "privacy_flags": risks,
        "high_risk_combination": high_risk,
        "flagged_privacy_questions": len(review_flags),
        "excluded_privacy_questions": len(review_flags) + quality.get("excluded_linked_asker", 0),
        "excluded_privacy_asker_groups": len(excluded_groups),
    }
    systemic_threshold = max(10, frame["distinct_question_ids"] * .05)
    if high_risk >= systemic_threshold or risks.get("sensitive_experience", 0) >= systemic_threshold:
        return {"status": "stopped_for_privacy", "privacy_stop_reason": "widespread_risk", **privacy}, (), (), ()
    if not eligible and review_flags:
        return {"status": "stopped_for_privacy", "privacy_stop_reason": "no_eligible_questions_after_filtering",
                **privacy}, (), (), ()
    eligible, duplicates = _exclude_duplicates(eligible)
    calendar = {row.question_id: sampling._calendar(row.created_at) for row in eligible}
    general, general_stats = sampling._general(eligible, calendar, SEED, TARGET, True)
    enriched, enriched_stats = sampling._enriched(eligible, general, SEED, TARGET)
    cohort_summaries = {"A_general": general_stats, "B_provisional": enriched_stats}
    overlap = {
        field: len({getattr(row, field) for row in general} & {getattr(row, field) for row in enriched})
        for field in ("question_id", "asker_id")
    }
    if any(overlap.values()):
        raise PreparationError("cohort_overlap")
    selected = len(general) + len(enriched)
    aggregate = {
        "status": "screening_complete_pending_human_review", "schema": SCHEMA,
        "design": {"sampling_schema": sampling.SCHEMA, "seed": SEED, "min_words": MIN_WORDS,
                   "temporal_strata_requested": True, "near_duplicate_jaccard_minimum": 0.9},
        "frame": frame, "quality": quality, "word_count_bins": lengths, "timestamp_status": dates,
        "timestamp_year_counts": years, **privacy, "duplicates": duplicates,
        "sampling_frame_questions": len(eligible),
        "sampling_frame_askers": len({row.asker_id for row in eligible}),
        "cohorts": cohort_summaries, "cross_cohort_overlap": overlap,
        "requires_human_privacy_review_selected": selected,
        "human_review_eligible": 0, "nlp_ready": 0,
        "selected_not_nlp_ready": selected,
    }
    selected_ids = {member.question_id for member in general + enriched}
    source_questions = tuple(question for question in questions if question.question_id in selected_ids)
    return aggregate, source_questions, general, enriched


class ReleaseRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urlsplit(newurl)
        if target.scheme != "https" or target.netloc not in {
            "release-assets.githubusercontent.com", "objects.githubusercontent.com",
            "github-releases.githubusercontent.com",
        }:
            raise PreparationError("unexpected_release_redirect")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _download():
    request = Request(URL, headers={"User-Agent": "Hissiyat-CareerNet-Preparation"})
    with build_opener(ReleaseRedirect()).open(request, timeout=30) as response:
        declared = response.headers.get("Content-Length")
        if declared is not None and declared != str(SIZE):
            raise PreparationError("source_integrity_mismatch")
        return response.read(SIZE + 1)


def _private_directory(path, *, base=None, phase="4c", allowed_files=()):
    base = base or Path(os.environ["LOCALAPPDATA"]) / "Hissiyat"
    try:
        resolved = path.resolve(strict=True)
    except (ValueError, OSError):
        raise PreparationError("unexpected_private_output_directory") from None
    repository = Path(__file__).resolve().parents[2]
    if (not path.is_absolute() or path != resolved or base.is_symlink() or base.is_junction() or
            resolved.parent != base.resolve() or resolved.is_relative_to(repository) or
            not re.fullmatch(rf"phase-{phase}-[a-f0-9]{{32}}", resolved.name) or
            not resolved.is_dir() or path.is_symlink() or path.is_junction()):
        raise PreparationError("unexpected_private_output_directory")
    for item in resolved.iterdir():
        if item.name not in allowed_files or item.is_symlink() or item.is_junction() or not item.is_file():
            raise PreparationError("unexpected_private_output_directory")
    return resolved


def _check_windows_access(directory, *, verify_files=False):
    # Check only this directory. Ignore and do not emit paths, accounts or ACL details.
    command = r"""
    $ErrorActionPreference = 'Stop'
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $directory = $env:HISSIYAT_PHASE4C_OUTPUT
    if ($directory -notmatch '^[A-Za-z]:\\' -or
        [IO.DriveInfo]::new([IO.Path]::GetPathRoot($directory)).DriveType -ne 'Fixed') { exit 2 }
    $acl = [IO.Directory]::GetAccessControl($directory)
    $owner = $acl.GetOwner([Security.Principal.SecurityIdentifier]).Value
    $rules = @($acl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier]))
    if (-not $acl.AreAccessRulesProtected -or $owner -ne $identity -or $rules.Length -ne 1 -or
        $rules[0].IdentityReference.Value -ne $identity -or
        $rules[0].AccessControlType -ne 'Allow' -or
        $rules[0].FileSystemRights -ne 'FullControl' -or
        [int]$rules[0].InheritanceFlags -ne 3 -or
        $rules[0].PropagationFlags -ne 'None' -or $rules[0].IsInherited) { exit 2 }
    if ($env:HISSIYAT_PHASE4C_VERIFY_FILES -eq '1') {
        foreach ($file in [IO.Directory]::EnumerateFiles($directory)) {
            $fileAcl = [IO.File]::GetAccessControl($file)
            $fileOwner = $fileAcl.GetOwner([Security.Principal.SecurityIdentifier]).Value
            $fileRules = @($fileAcl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier]))
            if ($fileOwner -ne $identity -or $fileRules.Length -ne 1 -or
                $fileRules[0].IdentityReference.Value -ne $identity -or
                $fileRules[0].AccessControlType -ne 'Allow' -or
                $fileRules[0].FileSystemRights -ne 'FullControl' -or -not $fileRules[0].IsInherited) { exit 2 }
        }
    }
    """
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        env={**os.environ, "HISSIYAT_PHASE4C_OUTPUT": str(directory),
             "HISSIYAT_PHASE4C_VERIFY_FILES": "1" if verify_files else "0"},
        capture_output=True, timeout=15, check=False,
    )
    if result.returncode:
        raise PreparationError("private_output_permissions_not_verified")


def _store_outputs(directory, provenance, aggregate):
    outputs = {"provenance.json": provenance, "aggregate.json": aggregate}
    created = []
    try:
        for filename, data in outputs.items():
            path = directory / filename
            with path.open("x", encoding="utf-8") as output:
                created.append(path)
                json.dump(data, output, ensure_ascii=True, indent=2, sort_keys=True)
                output.write("\n")
    except (Exception, KeyboardInterrupt):
        cleanup_failed = False
        for path in reversed(created):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                cleanup_failed = True
        if cleanup_failed:
            raise PreparationError("private_output_cleanup_failed") from None
        raise


def _console_summary(aggregate):
    def suppress_small(count):
        return "1-4" if 0 < count < 5 else count

    summary = dict(aggregate)
    for field in ("privacy_flags", "timestamp_year_counts"):
        if field in summary:
            summary[field] = {key: suppress_small(count) for key, count in summary[field].items()}
    for field in ("high_risk_combination", "flagged_privacy_questions",
                  "excluded_privacy_questions", "excluded_privacy_asker_groups"):
        if field in summary:
            summary[field] = suppress_small(summary[field])
    if "quality" in summary:
        summary["quality"] = {
            key: suppress_small(count) if key in {"excluded_privacy", "excluded_linked_asker"} else count
            for key, count in summary["quality"].items()
        }
    return summary


def _retention_deadline(now, requested_day=None):
    if requested_day is not None:
        try:
            last_day = date.fromisoformat(requested_day)
        except ValueError:
            raise PreparationError("invalid_retention_date") from None
        if last_day.isoformat() != requested_day or last_day > PILOT_LAST_DAY:
            raise PreparationError("invalid_retention_date")
    else:
        last_day = PILOT_LAST_DAY
    deadline = datetime.combine(last_day + timedelta(days=1), time.min, PILOT_LOCAL_TIME).astimezone(timezone.utc)
    if requested_day is None:
        deadline = min(deadline, now + timedelta(days=RETENTION_DAYS))
    if deadline <= now:
        raise PreparationError("retention_deadline_elapsed")
    return deadline


def main():
    args = sys.argv[1:]
    if len(args) not in (2, 4) or args[0] != "--approved-careernet-v1.1":
        print('{"status":"explicit_owner_approval_required"}')
        return 2
    try:
        if len(args) == 4 and args[2] != "--retain-until":
            raise PreparationError("invalid_retention_option")
        requested_day = args[3] if len(args) == 4 else None
        _retention_deadline(datetime.now(timezone.utc), requested_day)
        output = _private_directory(Path(args[1]))
        _check_windows_access(output)
        payload = _download()
        received = datetime.now(timezone.utc)
        aggregate = prepare(payload)
        del payload
        if aggregate["status"] == "stopped_for_privacy":
            default_deadline = _retention_deadline(received)
            deadline = min(default_deadline, _retention_deadline(received, requested_day))
        else:
            deadline = _retention_deadline(received, requested_day)
        provenance = {
            **REFERENCE, "download_url": URL, "size_bytes": SIZE, "checksum_verified": True,
            "acquired_utc": received.isoformat(timespec="seconds"),
            "delete_private_records_by_utc": deadline.isoformat(timespec="seconds"),
            "retention_scope": "provenance_and_aggregate_only",
            "manual_deletion_required": True,
            "attribution": "CareerNet v1.1 by Renaissance Philanthropy and The Learning Agency, "
                           "from CareerVillage.org contributions, CC BY 4.0",
            "license_url": "https://creativecommons.org/licenses/by/4.0/",
            "changes": "Question-level filtering, whitespace and markup normalization, privacy screening, and sampling.",
        }
        _check_windows_access(_private_directory(output))
        if datetime.now(timezone.utc) >= deadline:
            raise PreparationError("retention_deadline_elapsed")
        _store_outputs(output, provenance, aggregate)
        print(json.dumps(_console_summary(aggregate), sort_keys=True))
        return 3 if aggregate["status"] == "stopped_for_privacy" else 0
    except PreparationError as error:
        print(json.dumps({"status": "stopped", "reason": error.args[0]}))
    except (Exception, KeyboardInterrupt):
        print('{"status":"stopped","reason":"local_execution_failed"}')
    return 2


if __name__ == "__main__":
    sys.exit(main())
