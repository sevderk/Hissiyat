"""Aggregate-only bridge from the trusted local parser and pinned historical report."""

from datetime import UTC, date, datetime
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Literal
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.research_evidence import EvidenceFact, EvidencePackage, EvidenceScope

REPORT = Path(__file__).resolve().parents[3] / "frontend/src/lib/civil-comparison-data.json"
REPORT_SHA256 = "132ecadd10b5bde4dfd60a44d84bce3d0d03e31e8df0fc2738c96dd5bf33232f"


class Extreme(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    date: str
    value: float = Field(ge=0, le=100, allow_inf_nan=False)
    periods: int = Field(ge=1, le=2000)


class CsvSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    source: Literal["csv"]
    url: str = Field(max_length=2048)
    region: str = Field(pattern=r"(?:[A-Z]{2}|worldwide)")
    mode: Literal["topic", "event"]
    sha256: str = Field(pattern=r"[a-f0-9]{64}")
    interval: Literal["daily", "weekly", "monthly", "yearly"]
    observations: int = Field(ge=1, le=2000)
    observed: int = Field(ge=0, le=2000)
    missing: int = Field(ge=0, le=2000)
    suppressed: int = Field(ge=0, le=2000)
    ambiguous_zero: int = Field(ge=0, le=2000)
    first_period: str
    last_period: str
    peak: Extreme | None
    trough: Extreme | None
    first: Extreme | None
    last: Extreme | None
    change: float | None = Field(ge=-100, le=100, allow_inf_nan=False)

    @model_validator(mode="after")
    def coherent_summary(self):
        term, start, end = self.scope()
        first, last = date.fromisoformat(self.first_period), date.fromisoformat(self.last_period)
        if first > last or last > end or first > end or last < start:
            raise ValueError("invalid_periods")
        # The first exported bucket may overlap the requested start.
        allowance = {"daily": 0, "weekly": 6, "monthly": 30, "yearly": 365}[self.interval]
        if (start - first).days > allowance:
            raise ValueError("invalid_periods")
        if self.observed + self.missing + self.suppressed != self.observations or self.ambiguous_zero > self.observed:
            raise ValueError("invalid_counts")
        extremes = (self.peak, self.trough, self.first, self.last)
        if self.observed == 0:
            if any(item is not None for item in extremes) or self.change is not None:
                raise ValueError("invalid_empty_summary")
        else:
            if any(item is None for item in extremes):
                raise ValueError("incomplete_summary")
            for item in extremes:
                if not first <= date.fromisoformat(item.date) <= last or item.periods > self.observed:
                    raise ValueError("invalid_extreme")
            if not self.trough.value <= self.first.value <= self.peak.value or not self.trough.value <= self.last.value <= self.peak.value:
                raise ValueError("invalid_extreme")
            if (self.trough.value == 0) != (self.ambiguous_zero > 0) or self.first.date > self.last.date:
                raise ValueError("invalid_zero_or_dates")
            expected = round(self.last.value - self.first.value, 6) if self.observed > 1 else None
            if self.change != expected:
                raise ValueError("invalid_change")
        return self

    def scope(self):
        url = urlsplit(self.url)
        if url.scheme != "https" or url.netloc != "trends.google.com" or url.path != "/trends/explore" or url.fragment:
            raise ValueError("invalid_source")
        params = parse_qs(url.query, keep_blank_values=True)
        if set(params) - {"date", "geo", "q", "hl", "cat", "gprop"} or any(len(v) != 1 for v in params.values()):
            raise ValueError("invalid_source")
        value = lambda key, default="": params.get(key, [default])[0]
        terms = value("q").split(",")
        regions = [item or "worldwide" for item in value("geo").split(",")]
        ranges = value("date").split(",")
        if (not 1 <= len(terms) <= 2 or len(regions) != len(terms) or any(t != terms[0] for t in terms)
                or self.region not in regions or len(set(regions)) != len(regions)
                or any(region not in {"TR", "US", "GB", "worldwide"} for region in regions)
                or any(item != ranges[0] for item in ranges) or len(ranges) not in (1, len(terms))
                or value("cat", "0") != "0" or value("gprop") != ""):
            raise ValueError("invalid_scope")
        if not re.fullmatch(r"[a-z]{2,3}(?:-[a-zA-Z0-9]{2,8}){0,3}", value("hl", "en")):
            raise ValueError("invalid_language_metadata")
        term = terms[0]
        if not 2 <= len(term) <= 120 or term.strip() != term or any(not (c.isalnum() or c in " '’-" or 0x300 <= ord(c) <= 0x36f) for c in term):
            raise ValueError("invalid_query")
        start, end = map(date.fromisoformat, ranges[0].split(" "))
        if start < date(2004, 1, 1) or (end - start).days < 29 or end >= datetime.now(UTC).date():
            raise ValueError("invalid_scope")
        return term, start, end


class HistoricalInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    source: Literal["historical"]
    question: Literal["wages", "job_opportunities"]


def package_for(source, family, query, start, end, geography, facts, reference, *, count=0, status="exploratory", mode="topic"):
    return EvidencePackage(package_id=uuid4().hex, created_at=datetime.now(UTC).isoformat(),
        scope=EvidenceScope(source=source, family=family, mode=mode, query=query, start_date=start, end_date=end,
            date_unit="day", geography=geography, requested_geography=geography if family == "search_interest" else None,
            language_filter="en" if family == "discussion" else None, content="comments" if family == "discussion" else None,
            analyzed_documents=count), fictional=False, status=status, source_reference=reference, facts=facts)


def fact_list():
    facts = []
    def add(metric, kind, values, *, unit="metadata", denominator=None, method="curated_aggregate"):
        facts.append(EvidenceFact(id=f"E{len(facts) + 1:02}", metric=metric, unit=unit, kind=kind,
                                  values=values, denominator=denominator, method=method))
    return facts, add


def csv_evidence(summary: CsvSummary):
    term, start, end = summary.scope()
    facts, add = fact_list()
    add("csv_coverage", "observed", {key: getattr(summary, key) for key in (
        "observations", "observed", "missing", "suppressed", "ambiguous_zero", "first_period", "last_period", "interval")},
        unit="periods", denominator=summary.observations, method="validated_explore_csv")
    if summary.peak:
        add("csv_extremes", "observed", {"peak": summary.peak.value, "peak_date": summary.peak.date,
            "peak_ties": summary.peak.periods, "trough": summary.trough.value, "trough_date": summary.trough.date,
            "trough_ties": summary.trough.periods}, unit="interest_index", method="observed_csv_extrema")
    if summary.change is not None:
        add("csv_change", "observed", {"first": summary.first.value, "first_date": summary.first.date,
            "last": summary.last.value, "last_date": summary.last.date, "change": summary.change},
            unit="interest_index", method="last_minus_first_observed_index")
    add("csv_origin", "observed", {"sha256": summary.sha256, "attribution": "user_supplied",
        "measurement": "request_relative_0_to_100"}, method="local_server_csv_parser")
    add("csv_limits", "insufficient", {"scale_min": 0, "scale_max": 100}, method="relative_scale_and_ambiguous_zeros")
    add("search_limits", "insufficient", {}, method="no_absolute_counts_or_emotion_inference")
    return package_for("google_trends_csv", "search_interest", term, start.isoformat(), end.isoformat(),
        summary.region, facts, summary.url, status="exploratory" if summary.observed >= 2 else "insufficient", mode=summary.mode)


def historical_evidence(question: str):
    raw = REPORT.read_bytes().replace(b"\r\n", b"\n")
    if len(raw) > 65536 or sha256(raw).hexdigest() != REPORT_SHA256:
        raise ValueError("historical_report_unverified")
    report = json.loads(raw)
    result = report["questions"][question]
    old, new = result["legacy"], result["updated"]
    facts, add = fact_list()
    add("sample", "observed", {"retrieved": new["matched"], "selected": new["selected"], "analyzed": new["analyzed"]},
        unit="documents", denominator=new["analyzed"])
    add("historical_coverage", "observed", {"legacy": old["analyzed"], "updated": new["analyzed"],
        "shared": result["selection"]["shared"], "legacy_only": result["selection"]["legacy_only"],
        "updated_only": result["selection"]["updated_only"], "long_documents": new["selected_long_documents"]}, unit="documents")
    add("historical_expressions", "exploratory", {"legacy": old["documents_with_expressions"],
        "legacy_denominator": old["analyzed"], "updated": new["documents_with_expressions"], "updated_denominator": new["analyzed"],
        "paired_legacy": result["paired"]["legacy_detected_documents"], "paired_updated": result["paired"]["updated_detected_documents"],
        "paired_documents": result["paired"]["documents"]}, unit="documents", method="different_policy_samples_and_paired_subset")
    add("historical_clusters", "exploratory", {"legacy_ari": old["topics"]["agreement"]["ari"],
        "updated_ari": new["topics"]["agreement"]["ari"], "updated_nmf_silhouette": new["topics"]["separation"]["nmf"],
        "updated_minilm_silhouette": new["topics"]["separation"]["minilm"]}, unit="score", method="unvalidated_thematic_structure")
    for label, count in new["counts"].items():
        if count:
            add("expression", "exploratory", {"label": label, "matched": count, "rules": "aggregate_category_only"},
                unit="documents", denominator=new["analyzed"], method="explicit_english_spans_v2")
    add("historical_origin", "observed", {"examined": report["dataset"]["examined"], "report_sha256": REPORT_SHA256,
        "retrieved_at": report["dataset"]["retrieved_at"], "query": result["query"], "license": "CC0 1.0"})
    add("topic_validity", "insufficient", {}, method="no_independent_thematic_validation")
    add("historical_limits", "insufficient", {}, method="historical_selected_sample_not_current_public_opinion")
    add("context", "insufficient", {}, denominator=new["analyzed"], method="demographics_and_article_context_unavailable")
    return package_for("civil_comments", "discussion", question, *report["study_window"], "UNKNOWN", facts,
        report["dataset"]["source"], count=new["analyzed"])
