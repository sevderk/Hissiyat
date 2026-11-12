"""Deterministic sampling rehearsal for fictional in-memory questions."""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from hashlib import sha256
import json
import re


SCHEMA = "hissiyat_phase_3d_sampling_v1"
CAREERNET_REFERENCE = {
    "publisher": "Renaissance Philanthropy",
    "source": "https://github.com/RenaissancePhilanthropy/careernet-data/releases/tag/v1.1",
    "version": "v1.1",
    "filename": "general_public_v1.1.csv",
    "license": "CC BY 4.0",
    "publisher_sha256": "4e1583b68348ef741ca4abd8e52dec323c6cfc0bf761b15047c308370afb3017",
}
FIELDS = {"question_id", "asker_id", "title", "body", "created_at"}
QUESTION_ID = re.compile(r"synthetic-question-[a-z0-9-]{1,40}")
ASKER_ID = re.compile(r"synthetic-asker-[a-z0-9-]{1,40}")
DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
DATETIME = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}[T ][0-9]{2}:[0-9]{2}"
    r"(?::[0-9]{2}(?:\.[0-9]{1,6})?)?(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])?"
)
WORD = re.compile(r"[^\W\d_]+(?:['’-][^\W\d_]+)*")
DOMAIN = re.compile(
    r"\b(?:education|school|college|universit(?:y|ies)|degree|major|study|studies|"
    r"graduat\w*|jobs?|employ\w*|work|career\w*|occupations?|train\w*|"
    r"(?:re|up)[ -]?skill\w*|profession\w*|future|prospects?|opportunit(?:y|ies))\b",
    re.IGNORECASE,
)
UNCERTAINTY = re.compile(
    r"\b(?:unsure|uncertain\w*|unclear|not sure|whether|worr\w*|concern\w*|"
    r"don't know|do not know|can't decide|cannot decide|decid\w* between|"
    r"weigh\w* (?:my |the )?options|what if|risks?|layoffs?|laid off|job loss)\b",
    re.IGNORECASE,
)


class SamplingError(ValueError):
    """A fixed error code without input data."""


@dataclass(frozen=True, repr=False)
class _Question:
    question_id: str
    asker_id: str
    title: str
    body: str
    created_at: str | None


@dataclass(frozen=True, repr=False)
class PrivateMembership:
    question_id: str
    asker_id: str
    within_asker_frame_size: int
    stratum: str


@dataclass(frozen=True)
class SamplingResult:
    aggregate: dict
    general_membership: tuple[PrivateMembership, ...] = field(repr=False)
    enriched_candidates: tuple[PrivateMembership, ...] = field(repr=False)


def _parse_question(row):
    if type(row) is not dict or row.keys() != FIELDS:
        raise SamplingError("invalid_row_schema")
    question_id, asker_id = row["question_id"], row["asker_id"]
    if type(question_id) is not str or not QUESTION_ID.fullmatch(question_id):
        raise SamplingError("expected_synthetic_question_id")
    if type(asker_id) is not str or not ASKER_ID.fullmatch(asker_id):
        raise SamplingError("expected_synthetic_asker_id")
    title, body, created_at = row["title"], row["body"], row["created_at"]
    if any(type(value) is not str or "\0" in value or len(value) > limit
           for value, limit in ((title, 4_000), (body, 40_000))):
        raise SamplingError("invalid_question_text")
    if created_at is not None and (type(created_at) is not str or len(created_at) > 64 or "\0" in created_at):
        raise SamplingError("invalid_timestamp_field")
    created_at = created_at.strip() if created_at is not None else None
    return _Question(question_id, asker_id, " ".join(title.split()), " ".join(body.split()),
                     created_at or None)


def _calendar(created_at):
    if created_at is None:
        return "missing", "unknown_date"
    try:
        if DATE.fullmatch(created_at):
            year = date.fromisoformat(created_at).year
            status = "date_only"
        elif DATETIME.fullmatch(created_at) and not created_at.endswith("-00:00"):
            stamp = datetime.fromisoformat(created_at)
            year = stamp.year
            status = "local_time_unknown_zone" if stamp.tzinfo is None else "offset_datetime"
        else:
            return "invalid_or_ambiguous", "unknown_date"
    except ValueError:
        return "invalid_or_ambiguous", "unknown_date"
    for start, end in ((2011, 2019), (2020, 2022), (2023, 2025)):
        if start <= year <= end:
            return status, f"{start}-{end}"
    return status, "other_years"


def _rank(question, seed, stage):
    key = f"{SCHEMA}:{stage}:{seed}:{question.question_id}"
    return sha256(key.encode("ascii")).digest(), question.question_id


def _representatives(questions, seed, stage):
    groups = defaultdict(list)
    for question in questions:
        groups[question.asker_id].append(question)
    reps = [min(group, key=lambda row: _rank(row, seed, stage)) for group in groups.values()]
    return reps, {asker: len(group) for asker, group in groups.items()}


def _quotas(strata, target):
    sizes = {name: len(rows) for name, rows in strata.items()}
    draw = min(target, sum(sizes.values()))
    if draw == sum(sizes.values()):
        return sizes
    # Each nonempty stratum has positive coverage. Use the largest remainders
    # of remaining capacity to assign the remaining slots.
    remaining = draw - len(sizes)
    capacity = sum(sizes.values()) - len(sizes)
    shares = {name: divmod(remaining * (size - 1), capacity) for name, size in sizes.items()}
    quotas = {name: 1 + share[0] for name, share in shares.items()}
    order = sorted(quotas, key=lambda name: (-shares[name][1], name))
    for name in order[:draw - sum(quotas.values())]:
        quotas[name] += 1
    return quotas


def _general(eligible, calendar, seed, target, stratify):
    reps, group_sizes = _representatives(eligible, seed, "general-representative")
    strata = defaultdict(list)
    for row in reps:
        strata[calendar[row.question_id][1] if stratify else "all"].append(row)
    effective = stratify and 0 < len(strata) <= target
    if not effective:
        strata = {"all": reps} if reps else {}
    quotas = _quotas(strata, target)
    members, design = [], {}
    for name, rows in sorted(strata.items()):
        selected = sorted(rows, key=lambda row: _rank(row, seed, "general-draw"))[:quotas[name]]
        members.extend(PrivateMembership(row.question_id, row.asker_id, group_sizes[row.asker_id], name)
                       for row in selected)
        design[name] = {"representative_frame_size": len(rows), "draw_size": len(selected)}
    return tuple(members), {
        "target": target, "selected": len(members), "shortfall": target - len(members),
        "eligible_asker_groups": len(reps), "temporal_strata_used": effective, "strata": design,
        "reason_counts": {"selected_general": len(members), "representative_not_drawn": len(reps) - len(members),
                          "alternate_same_asker": len(eligible) - len(reps)},
    }


def _enriched(eligible, general, seed, target):
    question_ids = {member.question_id for member in general}
    asker_ids = {member.asker_id for member in general}
    reasons = dict.fromkeys(("no_uncertainty_screen_signal", "general_question_overlap_excluded",
                             "general_asker_overlap_excluded"), 0)
    pool = []
    for row in eligible:
        text = f"{row.title} {row.body}".replace("’", "'")
        if not (DOMAIN.search(text) and UNCERTAINTY.search(text)):
            reasons["no_uncertainty_screen_signal"] += 1
        elif row.question_id in question_ids:
            reasons["general_question_overlap_excluded"] += 1
        elif row.asker_id in asker_ids:
            reasons["general_asker_overlap_excluded"] += 1
        else:
            pool.append(row)
    reps, group_sizes = _representatives(pool, seed, "enriched-representative")
    chosen = sorted(reps, key=lambda row: _rank(row, seed, "enriched-draw"))[:target]
    members = tuple(PrivateMembership(row.question_id, row.asker_id, group_sizes[row.asker_id], "all")
                    for row in chosen)
    reasons.update(alternate_same_asker=len(pool) - len(reps), candidate_not_drawn=len(reps) - len(members),
                   pending_context_review=len(members))
    return members, {
        "target": target, "candidate_count": len(members), "candidate_shortfall": target - len(members),
        "eligible_candidate_asker_groups": len(reps), "review_status": "pending_context_review",
        "reason_counts": reasons,
    }


def sample_synthetic(rows, *, seed=42, general_target=200, enriched_target=200, min_words=30,
                     temporal_strata=False):
    """Return a disclosure-limited manifest and separate in-memory memberships."""
    if (type(seed) is not int or not 0 <= seed < 2**64 or type(temporal_strata) is not bool
            or type(general_target) is not int or not 1 <= general_target <= 200
            or type(enriched_target) is not int or not 0 <= enriched_target <= 200
            or type(min_words) is not int or not 1 <= min_words <= 100):
        raise SamplingError("invalid_sampling_options")
    if type(rows) not in (list, tuple):
        raise SamplingError("invalid_input_container")

    inventory = defaultdict(Counter)
    canonical_rows = []
    for raw in rows:
        row = _parse_question(raw)
        inventory[row.question_id][row] += 1
        canonical_rows.append(json.dumps((row.question_id, row.asker_id, row.title, row.body, row.created_at),
                                         separators=(",", ":")))
    digest = sha256("\n".join(sorted(canonical_rows)).encode("ascii")).hexdigest()

    counts = dict.fromkeys(("repeated_identical_rows", "conflicting_question_id", "empty_question_text",
                            "below_minimum_words", "eligible_question"), 0)
    eligible = []
    for variants in inventory.values():
        counts["repeated_identical_rows"] += sum(variants.values()) - len(variants)
        if len(variants) > 1:
            counts["conflicting_question_id"] += 1
            continue
        row = next(iter(variants))
        text = row.title if row.title == row.body else f"{row.title} {row.body}"
        if not text.strip():
            counts["empty_question_text"] += 1
        elif len(WORD.findall(text)) < min_words:
            counts["below_minimum_words"] += 1
        else:
            eligible.append(row)
    counts["eligible_question"] = len(eligible)

    calendar = {row.question_id: _calendar(row.created_at) for row in eligible}
    general, general_stats = _general(eligible, calendar, seed, general_target, temporal_strata)
    enriched, enriched_stats = _enriched(eligible, general, seed, enriched_target)
    aggregate = {
        "schema": SCHEMA,
        "input": {"kind": "synthetic", "canonical_row_multiset_sha256": digest, "row_count": len(rows),
                  "unique_question_ids": len(inventory)},
        "reference_dataset_not_processed": dict(CAREERNET_REFERENCE),
        "design": {"seed": seed, "minimum_words": min_words, "temporal_strata_requested": temporal_strata},
        "frame_reason_counts": counts,
        "eligible_timestamp_status_counts": dict(sorted(Counter(status for status, _ in calendar.values()).items())),
        "general": general_stats,
        "uncertainty_enriched_candidates": enriched_stats,
        "overlap": {
            "question_ids": len({row.question_id for row in general} & {row.question_id for row in enriched}),
            "asker_ids": len({row.asker_id for row in general} & {row.asker_id for row in enriched}),
        },
    }
    return SamplingResult(aggregate, general, enriched)
