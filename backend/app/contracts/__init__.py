"""Source-independent input validation; no ingestion or persistence."""

from app.contracts.inputs import (
    CollectionMetadata,
    SourcePolicyReference,
    TextRecordInput,
    TrendObservationInput,
    TrendSeriesMetadata,
    validation_error_summary,
)

__all__ = [
    "CollectionMetadata",
    "SourcePolicyReference",
    "TextRecordInput",
    "TrendObservationInput",
    "TrendSeriesMetadata",
    "validation_error_summary",
]
