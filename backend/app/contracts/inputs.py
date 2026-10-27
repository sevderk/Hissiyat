"""Validate input structure without granting rights or producing research claims."""

from collections import Counter
from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    SecretStr,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)

NonBlank = Annotated[str, StringConstraints(pattern=r"\S")]
Number = Annotated[float, Field(strict=True, allow_inf_nan=False)]
LanguageCode = Annotated[
    str, StringConstraints(pattern=r"^[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")
]


def require_datetime_input(value: object) -> object:
    # Numeric epochs and date-only values need an explicit adapter decision.
    if not isinstance(value, (str, datetime)) or (
        isinstance(value, str) and "T" not in value and "t" not in value
    ):
        raise ValueError("Use a timezone-aware datetime or ISO 8601 datetime string.")
    return value


Timestamp = Annotated[AwareDatetime, BeforeValidator(require_datetime_input)]


class InputContract(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, hide_input_in_errors=True, revalidate_instances="always"
    )


class SourcePolicyReference(InputContract):
    source_id: NonBlank
    policy_reference: NonBlank
    usage_status: Literal["unknown", "unverified", "approved", "denied"] = "unknown"
    decision_reference: NonBlank | None = None

    @model_validator(mode="after")
    def require_documented_approval(self) -> Self:
        if self.usage_status == "approved" and self.decision_reference is None:
            raise ValueError("Approved status requires a documented decision reference.")
        return self


class CollectionMetadata(InputContract):
    collection_id: NonBlank
    source_policy: SourcePolicyReference
    method: Literal["api", "file_import", "manual_import"]
    occurred_at: Timestamp
    source_reference: NonBlank


class TextRecordInput(InputContract):
    collection: CollectionMetadata
    source_record_id: NonBlank
    record_id_origin: Literal["source", "local"] = "source"
    local_id_method: NonBlank | None = None
    text: SecretStr | None = Field(default=None, repr=False)
    content_reference: NonBlank | None = Field(default=None, repr=False)
    original_reference: NonBlank | None = Field(default=None, repr=False)
    published_at: Timestamp | None = None
    retrieved_at: Timestamp
    language_code: LanguageCode = "und"
    language_method: Literal["undetermined", "source", "human", "automated"] = "undetermined"
    quality_status: Literal["unchecked", "accepted", "flagged"] = "unchecked"

    @field_validator("text")
    @classmethod
    def reject_blank_text(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and not value.get_secret_value().strip():
            raise ValueError("Text must not be blank.")
        return value

    @model_validator(mode="after")
    def validate_record_context(self) -> Self:
        if (self.text is None) == (self.content_reference is None):
            raise ValueError("Provide exactly one of text and content_reference.")
        if self.record_id_origin == "local" and self.local_id_method is None:
            raise ValueError("Local record identifiers require a documented fallback method.")
        if self.record_id_origin == "source" and self.local_id_method is not None:
            raise ValueError("A fallback method applies only to local record identifiers.")
        if self.published_at is not None and self.published_at > self.retrieved_at:
            raise ValueError("Publication time must not follow retrieval time.")
        if self.language_method == "undetermined" and self.language_code != "und":
            raise ValueError("An undetermined language must use the und code.")
        return self

    @property
    def has_publication_timestamp(self) -> bool:
        """Necessary temporal metadata only; not research eligibility or permission."""
        return self.published_at is not None


class TrendSeriesMetadata(InputContract):
    series_id: NonBlank
    collection: CollectionMetadata
    descriptor: NonBlank
    descriptor_kind: Literal["search_term", "topic"]
    geographic_scope: NonBlank
    measurement_unit: NonBlank
    scaling_context: NonBlank
    scale_min: Number | None = None
    scale_max: Number | None = None

    @model_validator(mode="after")
    def validate_scale(self) -> Self:
        if self.scale_min is not None and self.scale_max is not None:
            if self.scale_min > self.scale_max:
                raise ValueError("The declared scale minimum must not exceed its maximum.")
        return self


class TrendObservationInput(InputContract):
    series: TrendSeriesMetadata
    interval_start: Timestamp
    interval_end: Timestamp
    retrieved_at: Timestamp
    value_status: Literal["observed", "missing", "suppressed"]
    value: Number | None = None
    data_reference: NonBlank

    @model_validator(mode="after")
    def validate_observation(self) -> Self:
        if self.interval_start >= self.interval_end:
            raise ValueError("The interval end must follow its start.")
        if self.value_status != "observed":
            if self.value is not None:
                raise ValueError("Missing or suppressed observations must not contain a value.")
            return self
        if self.value is None:
            raise ValueError("An observed measurement requires a value.")
        if self.series.scale_min is not None and self.value < self.series.scale_min:
            raise ValueError("The value is below the source-declared scale minimum.")
        if self.series.scale_max is not None and self.value > self.series.scale_max:
            raise ValueError("The value exceeds the source-declared scale maximum.")
        return self


def validation_error_summary(error: ValidationError) -> dict[str, int]:
    """Return error-code counts only: no inputs, messages, locations or context."""
    return dict(Counter(
        issue["type"]
        for issue in error.errors(include_input=False, include_context=False, include_url=False)
    ))
