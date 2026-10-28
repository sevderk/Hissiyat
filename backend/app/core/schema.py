"""Minimal SQLAlchemy Core metadata; importing this module never creates tables."""

from uuid import uuid4

from sqlalchemy import (
    CheckConstraint, Column, DateTime, ForeignKey, ForeignKeyConstraint, Index,
    MetaData, Table, Text, UniqueConstraint, Uuid,
)

metadata = MetaData(naming_convention={
    "pk": "pk_%(table_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
})


def nonblank(column: str) -> CheckConstraint:
    return CheckConstraint(f"{column} ~ '[^[:space:]]'", name=f"{column}_nonblank")


data_sources = Table(
    "data_sources", metadata,
    Column("id", Uuid, primary_key=True, default=uuid4),
    Column("source_key", Text, nullable=False),
    Column("reference", Text),
    UniqueConstraint("source_key"),
    nonblank("source_key"), nonblank("reference"),
)

source_policies = Table(
    "source_policies", metadata,
    Column("id", Uuid, primary_key=True, default=uuid4),
    Column("source_id", Uuid, ForeignKey("data_sources.id", ondelete="RESTRICT"), nullable=False),
    Column("policy_reference", Text, nullable=False),
    Column("usage_status", Text, nullable=False, server_default="unknown"),
    Column("decision_reference", Text),
    Column("documentation_reference", Text),
    Column("reviewed_at", DateTime(timezone=True)),
    Column("usage_constraints", Text),
    Column("retention_constraints", Text),
    UniqueConstraint("id", "source_id"),
    UniqueConstraint("source_id", "policy_reference"),
    CheckConstraint("usage_status IN ('unknown','unverified','approved','denied')", name="usage_status"),
    CheckConstraint("usage_status <> 'approved' OR decision_reference IS NOT NULL", name="approval_reference"),
    *[nonblank(name) for name in (
        "policy_reference", "decision_reference", "documentation_reference",
        "usage_constraints", "retention_constraints",
    )],
)

collection_events = Table(
    "collection_events", metadata,
    Column("id", Uuid, primary_key=True, default=uuid4),
    Column("source_id", Uuid, ForeignKey("data_sources.id", ondelete="RESTRICT"), nullable=False),
    Column("policy_id", Uuid, nullable=False),
    Column("method", Text, nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("status", Text, nullable=False, server_default="planned"),
    Column("source_reference", Text, nullable=False),
    UniqueConstraint("id", "source_id"),
    ForeignKeyConstraint(
        ["policy_id", "source_id"], ["source_policies.id", "source_policies.source_id"], ondelete="RESTRICT",
    ),
    CheckConstraint("method IN ('api','file_import','manual_import')", name="method"),
    CheckConstraint("status IN ('planned','in_progress','completed','partial','failed')", name="status"),
    nonblank("source_reference"),
    Index("ix_collection_events_source_id", "source_id"),
    Index("ix_collection_events_policy_id_source_id", "policy_id", "source_id"),
)

source_records = Table(
    "source_records", metadata,
    Column("id", Uuid, primary_key=True, default=uuid4),
    Column("source_id", Uuid, ForeignKey("data_sources.id", ondelete="RESTRICT"), nullable=False),
    Column("source_record_id", Text, nullable=False),
    Column("record_id_origin", Text, nullable=False, server_default="source"),
    Column("local_id_method", Text),
    Column("first_collection_event_id", Uuid, nullable=False),
    Column("published_at", DateTime(timezone=True)),
    Column("original_reference", Text),
    UniqueConstraint("id", "source_id"),
    UniqueConstraint("source_id", "source_record_id"),
    ForeignKeyConstraint(
        ["first_collection_event_id", "source_id"],
        ["collection_events.id", "collection_events.source_id"], ondelete="RESTRICT",
    ),
    CheckConstraint("record_id_origin IN ('source','local')", name="record_id_origin"),
    CheckConstraint(
        "(record_id_origin = 'source' AND local_id_method IS NULL) OR "
        "(record_id_origin = 'local' AND local_id_method IS NOT NULL)", name="local_id_method",
    ),
    nonblank("source_record_id"), nonblank("local_id_method"), nonblank("original_reference"),
    Index("ix_source_records_first_collection_event_id_source_id", "first_collection_event_id", "source_id"),
)

text_versions = Table(
    "text_versions", metadata,
    Column("id", Uuid, primary_key=True, default=uuid4),
    Column("source_record_id", Uuid, nullable=False),
    Column("source_id", Uuid, nullable=False),
    Column("collection_event_id", Uuid, nullable=False),
    Column("version_key", Text, nullable=False),
    Column("content_kind", Text, nullable=False, server_default="original"),
    Column("text_content", Text),
    Column("content_reference", Text),
    Column("transformation_reference", Text),
    Column("retrieved_at", DateTime(timezone=True), nullable=False),
    Column("retention_until", DateTime(timezone=True)),
    UniqueConstraint("source_record_id", "version_key"),
    ForeignKeyConstraint(
        ["source_record_id", "source_id"], ["source_records.id", "source_records.source_id"], ondelete="RESTRICT",
    ),
    ForeignKeyConstraint(
        ["collection_event_id", "source_id"], ["collection_events.id", "collection_events.source_id"], ondelete="RESTRICT",
    ),
    CheckConstraint("content_kind IN ('original','normalized')", name="content_kind"),
    CheckConstraint("(text_content IS NULL) <> (content_reference IS NULL)", name="content_choice"),
    CheckConstraint(
        "(content_kind = 'original' AND transformation_reference IS NULL) OR "
        "(content_kind = 'normalized' AND transformation_reference IS NOT NULL)", name="transformation_reference",
    ),
    *[nonblank(name) for name in ("version_key", "text_content", "content_reference", "transformation_reference")],
    Index("ix_text_versions_collection_event_id_source_id", "collection_event_id", "source_id"),
)
