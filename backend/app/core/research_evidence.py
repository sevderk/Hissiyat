"""Request-local aggregate evidence, built from completed backend computations."""

from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.core.research import ResearchRequest


class EvidenceFact(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    id: str = Field(pattern=r"E[0-9]{2}")
    metric: str
    unit: Literal["documents", "days", "score", "periods", "metadata", "interest_index"]
    kind: Literal["observed", "exploratory", "insufficient"]
    values: dict[str, str | int | float | None]
    denominator: int | None
    method: str


class EvidenceScope(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    source: Literal["fictional", "bluesky", "lemmy", "wikimedia", "civil_comments", "google_trends", "google_trends_csv"]
    family: Literal["discussion", "search_interest"]
    mode: Literal["topic", "event"]
    query: str
    start_date: str
    end_date: str
    date_unit: Literal["day", "month"]
    geography: str
    requested_geography: str | None
    language_filter: str | None
    content: str | None
    analyzed_documents: int


class EvidencePackage(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    package_id: str = Field(pattern=r"[0-9a-f]{32}")
    version: Literal["research_evidence_v1"] = "research_evidence_v1"
    created_at: str
    scope: EvidenceScope
    fictional: bool
    status: Literal["exploratory", "insufficient"]
    source_reference: str | None
    facts: list[EvidenceFact] = Field(min_length=1, max_length=24)


def build_evidence(scope: ResearchRequest, result: dict) -> EvidencePackage:
    facts = []

    def add(metric, kind, values, denominator=None, method="source_metadata"):
        units = {"sample": "documents", "expression": "documents", "no_expression_matches": "documents",
                 "topic_partition": "documents", "coverage": "days", "agreement": "score", "search_summary": "periods"}
        facts.append(EvidenceFact(id=f"E{len(facts) + 1:02}", metric=metric, unit=units.get(metric, "metadata"), kind=kind,
                                  values=values, denominator=denominator, method=method))

    analysis = result.get("discussion_analysis")
    count = len(analysis["evidence_rows"]) if analysis else 0
    family = "search_interest" if scope.source == "google_trends" else "discussion"
    geography = "UNKNOWN"
    status = "insufficient"
    reference = None
    if family == "discussion":
        records = result["records"]
        add("sample", "observed", {"retrieved": result["retrieved"], "selected": len(records), "analyzed": count}, len(records))
        document = result.get("dataset_document") or result.get("source_document") or {}
        add("source_scope", "observed", {"max_items": result["capabilities"]["max_items"],
            "retrieved_at": document.get("retrieved_at"), "revision": document.get("revision"),
            "examined": document.get("examined"), "eligible": document.get("eligible")}, method="bounded_source_selection")
        if records:
            dates = sorted(record["published_at"][:10] for record in records)
            add("coverage", "observed", {"first": dates[0], "last": dates[-1], "active_days": len(set(dates))}, len(records))
        add("temporal_comparison", "insufficient", {}, method="no_comparable_sampling_design")
        if analysis:
            report = analysis.get("expression_evidence")
            if report:
                for label, value in report["counts"].items():
                    if value:
                        rule_ids = sorted({item["rule"] for item in report["evidence"] if item["label"] == label})
                        add("expression", "exploratory", {"label": label, "matched": value, "rules": ", ".join(rule_ids)},
                            count, report["method"])
                if not any(report["counts"].values()):
                    add("no_expression_matches", "exploratory", {"matched": 0}, count, report["method"])
            else:
                add("expression_unavailable", "insufficient", {}, count, "versioned_evidence_unavailable")
            topics = analysis["topics"]
            if topics:
                status = "exploratory" if count >= 12 else "insufficient"
                for method, groups in topics["methods"].items():
                    values = {f"group_{index + 1}": group["size"] for index, group in enumerate(groups["groups"])}
                    values.update({f"terms_{index + 1}": ", ".join(group["keywords"])
                                   for index, group in enumerate(groups["groups"])})
                    values["unassigned"] = groups["unassigned"]
                    values["assigned"] = count - groups["unassigned"]
                    values["groups_count"] = len(groups["groups"])
                    score = topics.get("separation", {}).get(method)
                    values["silhouette"] = score
                    add("topic_partition", "exploratory", values, count, method)
                if topics["agreement"]:
                    agreement = topics["agreement"]
                    add("agreement", "exploratory", {"ari": agreement["ari"]}, agreement["common_assigned"], "adjusted_rand_index")
                add("topic_validity", "insufficient", {}, count, "no_independent_thematic_validation")
            else:
                add("topics_unavailable", "insufficient", {"reason": analysis["topics_status"]}, count, "topic_eligibility")
            add("expression_validity", "insufficient", {}, count, "no_independent_rule_accuracy_estimate")
        else:
            add("analysis_unavailable", "insufficient", {}, method="analysis_not_requested")
        reference = (result.get("source_document") or result.get("dataset_document") or {}).get("source")
        if scope.source == "wikimedia":
            reference = result["source_document"]["page"]
    else:
        reference = "https://trends.googleapis.com"
        summary = result.get("summary")
        if summary is not None:
            geography = summary["geography"]
            status = "exploratory" if summary["nonzero"] >= 2 else "insufficient"
            add("search_summary", "observed", {key: summary[key] for key in (
                "cadence", "first_period", "last_period", "nonzero", "ambiguous_zero", "missing", "suppressed",
                "peak_period", "peak_ties", "direction",
            )}, method="documented_official_api_summary")
        else:
            add("search_unverified", "insufficient", {}, method="response_semantics_or_display_unverified")
        add("search_limits", "insufficient", {}, method="no_absolute_counts_or_emotion_inference")
    add("geography", "observed" if geography != "UNKNOWN" else "insufficient", {"geography": geography})
    add("context", "insufficient", {}, count if family == "discussion" and analysis else None,
        method="demographics_and_article_context_unavailable")
    add("generalization", "insufficient", {}, method="no_population_or_causal_design")
    return EvidencePackage(
        package_id=uuid4().hex, created_at=datetime.now(UTC).isoformat(),
        scope=EvidenceScope(source=scope.source, family=family, mode=scope.mode, query=scope.query,
                            start_date=scope.start_date.strftime("%Y-%m") if family == "search_interest" else scope.start_date.isoformat(),
                            end_date=scope.end_date.strftime("%Y-%m") if family == "search_interest" else scope.end_date.isoformat(),
                            date_unit="month" if family == "search_interest" else "day",
                            geography=geography, requested_geography=scope.geography, language_filter=scope.language,
                            content=scope.content, analyzed_documents=count),
        fictional=scope.source == "fictional" or result.get("source") == "fictional_trends_research",
        status=status, source_reference=reference, facts=facts,
    )
