"""Versioned batch envelopes around the existing text input contract."""

from typing import Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from app.contracts.inputs import InputContract, NonBlank, TextRecordInput, Timestamp


class TextImportEntry(InputContract):
    version_key: NonBlank
    record: TextRecordInput


class TextImportBatch(InputContract):
    format_version: Literal["hissiyat.text-import.v1"]
    fixture_id: NonBlank
    records: tuple[TextImportEntry, ...] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def require_one_explicit_event(self) -> Self:
        collection = self.records[0].record.collection
        # The existing event UUID is the import identity; never derive one from text.
        if str(UUID(collection.collection_id)) != collection.collection_id:
            raise ValueError("Use a canonical UUID for collection_id.")
        if collection.method != "file_import":
            raise ValueError("This boundary supports explicit file imports only.")
        if any(entry.record.collection != collection for entry in self.records):
            raise ValueError("A batch must describe one source, policy and event.")
        return self


class RowResult(InputContract):
    index: int
    status: Literal["accepted", "duplicate", "rejected", "failed"]
    code: str
    source_record_id: UUID | None = None
    text_version_id: UUID | None = None
    version_collection_event_id: UUID | None = None
    record_created: bool = False
    language_code: str | None = None
    language_method: str | None = None
    quality_status: str | None = None
    has_publication_timestamp: bool = False
    published_at: Timestamp | None = None
    retrieved_at: Timestamp | None = None


class ImportResult(InputContract):
    status: Literal["applied", "rejected", "failed"]
    code: str
    rows: tuple[RowResult, ...] = ()
    validation_errors: dict[str, int] = Field(default_factory=dict)
    collection_event_id: UUID | None = None
    fixture_id: str | None = None
    fixture_fingerprint: str | None = None
    language_and_quality_storage: Literal["input_and_receipt_only"] = "input_and_receipt_only"

    @property
    def counts(self) -> dict[str, int]:
        return {status: sum(row.status == status for row in self.rows)
                for status in ("accepted", "rejected", "duplicate", "failed")}
