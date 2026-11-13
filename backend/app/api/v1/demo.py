"""Fixed aggregate examples for the development and test dashboard."""

from datetime import date, timedelta
from typing import Annotated, Literal, Self

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field, model_validator

from app.contracts.inputs import InputContract

router = APIRouter(prefix="/demo", tags=["synthetic demo"])
Cohort = Literal["general", "uncertainty-enriched"]
Group = Literal["topics", "emotions", "needs", "experiences"]
Category = Literal[
    "education", "career_paths", "job_market", "reskilling",
    "hope", "concern", "frustration", "relief",
    "guidance", "information", "support", "opportunities",
    "study_choice", "job_search", "career_change", "skills_training",
]
Count = Annotated[int, Field(strict=True, ge=0, le=100_000)]
Score = Annotated[int, Field(strict=True, ge=0, le=100)]
GROUPS: dict[Group, tuple[Category, ...]] = {
    "topics": ("education", "career_paths", "job_market", "reskilling"),
    "emotions": ("hope", "concern", "frustration", "relief"),
    "needs": ("guidance", "information", "support", "opportunities"),
    "experiences": ("study_choice", "job_search", "career_change", "skills_training"),
}


class DemoResponse(InputContract):
    demo: Literal[True] = True
    contract_version: Literal["1.0"] = "1.0"
    provenance: Literal["fixed_fictional_aggregates"] = "fixed_fictional_aggregates"


class CategoryCount(InputContract):
    key: Category
    count: Count


class TextAnalysis(DemoResponse):
    source_category: Literal["human_experience"] = "human_experience"
    method: Literal["fictional_document_label_counts"] = "fictional_document_label_counts"
    limitations: tuple[Literal["fictional_only"], Literal["cohorts_not_comparable_for_prevalence"]] = (
        "fictional_only", "cohorts_not_comparable_for_prevalence",
    )
    cohort: Cohort
    document_count: Count
    multi_label: Literal[True] = True
    emotion_basis: Literal["explicit_expression"] = "explicit_expression"
    groups: dict[Group, tuple[CategoryCount, ...]]

    @model_validator(mode="after")
    def check_counts(self) -> Self:
        if self.groups.keys() != GROUPS.keys():
            raise ValueError("All four category groups are required.")
        for group, categories in self.groups.items():
            if len({item.key for item in categories}) != len(categories) or any(
                item.key not in GROUPS[group] or item.count > self.document_count for item in categories
            ):
                raise ValueError("Categories must be unique, in their group and within the denominator.")
            if not self.document_count and categories:
                raise ValueError("An empty cohort must have empty category groups.")
        return self


class InterestPoint(InputContract):
    date: date
    status: Literal["observed", "missing", "suppressed"]
    value: Score | None

    @model_validator(mode="after")
    def check_status(self) -> Self:
        if (self.status == "observed") != (self.value is not None):
            raise ValueError("Only observed points have a numeric value.")
        return self


class SearchInterest(DemoResponse):
    source_category: Literal["search_interest"] = "search_interest"
    method: Literal["fictional_relative_index"] = "fictional_relative_index"
    limitations: tuple[Literal["fictional_only"], Literal["index_not_volume"]] = (
        "fictional_only", "index_not_volume",
    )
    query: Literal["orbital_greenhouse_apprenticeships"] = "orbital_greenhouse_apprenticeships"
    geography: Literal["fictional_harbor_district"] = "fictional_harbor_district"
    granularity: Literal["weekly"] = "weekly"
    scale: tuple[Literal[0], Literal[100]] = (0, 100)
    points: Annotated[tuple[InterestPoint, ...], Field(max_length=52)]

    @model_validator(mode="after")
    def check_calendar(self) -> Self:
        if any(point.date.weekday() != 0 for point in self.points) or any(
            (current.date - previous.date).days != 7
            for previous, current in zip(self.points, self.points[1:])
        ):
            raise ValueError("Provide ordered, consecutive Mondays including gaps.")
        return self


def _text_fixture(cohort: Cohort, total: int, counts: tuple[tuple[int, ...], ...]) -> TextAnalysis:
    return TextAnalysis(
        cohort=cohort,
        document_count=total,
        groups={
            group: tuple(CategoryCount(key=key, count=count) for key, count in zip(keys, values, strict=True))
            for (group, keys), values in zip(GROUPS.items(), counts, strict=True)
        },
    )


TEXT_FIXTURES = {
    "general": _text_fixture("general", 240, (
        (131, 108, 77, 54), (86, 69, 34, 21), (106, 92, 56, 43), (93, 71, 44, 38),
    )),
    "uncertainty-enriched": _text_fixture("uncertainty-enriched", 126, (
        (58, 75, 86, 42), (30, 78, 43, 11), (82, 53, 64, 33), (37, 77, 51, 29),
    )),
}
INTEREST_FIXTURE = SearchInterest(points=tuple(
    InterestPoint(date=date(2025, 1, 6) + timedelta(weeks=index), status=status, value=value)
    for index, (status, value) in enumerate((
        ("observed", 28), ("observed", 39), ("observed", 34), ("observed", 52),
        ("missing", None), ("observed", 47), ("observed", 63), ("observed", 56),
        ("suppressed", None), ("observed", 68), ("observed", 78), ("observed", 72),
    ))
))


@router.get("/text-analysis", response_model=TextAnalysis)
def text_analysis(request: Request, cohort: str = "general") -> TextAnalysis:
    if (set(request.query_params) - {"cohort"} or len(request.query_params.getlist("cohort")) > 1
            or cohort not in TEXT_FIXTURES):
        raise HTTPException(status_code=400, detail="Invalid demo cohort.")
    return TEXT_FIXTURES[cohort]


@router.get("/search-interest", response_model=SearchInterest)
def search_interest(request: Request) -> SearchInterest:
    if request.query_params:
        raise HTTPException(status_code=400, detail="Invalid demo query.")
    return INTEREST_FIXTURE
