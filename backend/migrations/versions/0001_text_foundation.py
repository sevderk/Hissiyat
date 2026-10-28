"""Create the five reviewed text-provenance tables; no data import or authorization."""

from alembic import op
from alembic.util import CommandError
import sqlalchemy as sa

revision = "0001_text_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('data_sources',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('source_key', sa.Text(), nullable=False),
    sa.Column('reference', sa.Text(), nullable=True),
    sa.CheckConstraint("reference ~ '[^[:space:]]'", name=op.f('ck_data_sources_reference_nonblank')),
    sa.CheckConstraint("source_key ~ '[^[:space:]]'", name=op.f('ck_data_sources_source_key_nonblank')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_data_sources')),
    sa.UniqueConstraint('source_key', name=op.f('uq_data_sources_source_key'))
    )
    op.create_table('source_policies',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('source_id', sa.Uuid(), nullable=False),
    sa.Column('policy_reference', sa.Text(), nullable=False),
    sa.Column('usage_status', sa.Text(), server_default='unknown', nullable=False),
    sa.Column('decision_reference', sa.Text(), nullable=True),
    sa.Column('documentation_reference', sa.Text(), nullable=True),
    sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('usage_constraints', sa.Text(), nullable=True),
    sa.Column('retention_constraints', sa.Text(), nullable=True),
    sa.CheckConstraint("decision_reference ~ '[^[:space:]]'", name=op.f('ck_source_policies_decision_reference_nonblank')),
    sa.CheckConstraint("documentation_reference ~ '[^[:space:]]'", name=op.f('ck_source_policies_documentation_reference_nonblank')),
    sa.CheckConstraint("policy_reference ~ '[^[:space:]]'", name=op.f('ck_source_policies_policy_reference_nonblank')),
    sa.CheckConstraint("retention_constraints ~ '[^[:space:]]'", name=op.f('ck_source_policies_retention_constraints_nonblank')),
    sa.CheckConstraint("usage_constraints ~ '[^[:space:]]'", name=op.f('ck_source_policies_usage_constraints_nonblank')),
    sa.CheckConstraint("usage_status <> 'approved' OR decision_reference IS NOT NULL", name=op.f('ck_source_policies_approval_reference')),
    sa.CheckConstraint("usage_status IN ('unknown','unverified','approved','denied')", name=op.f('ck_source_policies_usage_status')),
    sa.ForeignKeyConstraint(['source_id'], ['data_sources.id'], name=op.f('fk_source_policies_source_id_data_sources'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_source_policies')),
    sa.UniqueConstraint('id', 'source_id', name=op.f('uq_source_policies_id')),
    sa.UniqueConstraint('source_id', 'policy_reference', name=op.f('uq_source_policies_source_id'))
    )
    op.create_table('collection_events',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('source_id', sa.Uuid(), nullable=False),
    sa.Column('policy_id', sa.Uuid(), nullable=False),
    sa.Column('method', sa.Text(), nullable=False),
    sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('status', sa.Text(), server_default='planned', nullable=False),
    sa.Column('source_reference', sa.Text(), nullable=False),
    sa.CheckConstraint("method IN ('api','file_import','manual_import')", name=op.f('ck_collection_events_method')),
    sa.CheckConstraint("source_reference ~ '[^[:space:]]'", name=op.f('ck_collection_events_source_reference_nonblank')),
    sa.CheckConstraint("status IN ('planned','in_progress','completed','partial','failed')", name=op.f('ck_collection_events_status')),
    sa.ForeignKeyConstraint(['policy_id', 'source_id'], ['source_policies.id', 'source_policies.source_id'], name=op.f('fk_collection_events_policy_id_source_policies'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['source_id'], ['data_sources.id'], name=op.f('fk_collection_events_source_id_data_sources'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_collection_events')),
    sa.UniqueConstraint('id', 'source_id', name=op.f('uq_collection_events_id'))
    )
    op.create_table('source_records',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('source_id', sa.Uuid(), nullable=False),
    sa.Column('source_record_id', sa.Text(), nullable=False),
    sa.Column('record_id_origin', sa.Text(), server_default='source', nullable=False),
    sa.Column('local_id_method', sa.Text(), nullable=True),
    sa.Column('first_collection_event_id', sa.Uuid(), nullable=False),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('original_reference', sa.Text(), nullable=True),
    sa.CheckConstraint("(record_id_origin = 'source' AND local_id_method IS NULL) OR (record_id_origin = 'local' AND local_id_method IS NOT NULL)", name=op.f('ck_source_records_local_id_method')),
    sa.CheckConstraint("local_id_method ~ '[^[:space:]]'", name=op.f('ck_source_records_local_id_method_nonblank')),
    sa.CheckConstraint("original_reference ~ '[^[:space:]]'", name=op.f('ck_source_records_original_reference_nonblank')),
    sa.CheckConstraint("record_id_origin IN ('source','local')", name=op.f('ck_source_records_record_id_origin')),
    sa.CheckConstraint("source_record_id ~ '[^[:space:]]'", name=op.f('ck_source_records_source_record_id_nonblank')),
    sa.ForeignKeyConstraint(['first_collection_event_id', 'source_id'], ['collection_events.id', 'collection_events.source_id'], name=op.f('fk_source_records_first_collection_event_id_collection_events'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['source_id'], ['data_sources.id'], name=op.f('fk_source_records_source_id_data_sources'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_source_records')),
    sa.UniqueConstraint('id', 'source_id', name=op.f('uq_source_records_id')),
    sa.UniqueConstraint('source_id', 'source_record_id', name=op.f('uq_source_records_source_id'))
    )
    op.create_table('text_versions',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('source_record_id', sa.Uuid(), nullable=False),
    sa.Column('source_id', sa.Uuid(), nullable=False),
    sa.Column('collection_event_id', sa.Uuid(), nullable=False),
    sa.Column('version_key', sa.Text(), nullable=False),
    sa.Column('content_kind', sa.Text(), server_default='original', nullable=False),
    sa.Column('text_content', sa.Text(), nullable=True),
    sa.Column('content_reference', sa.Text(), nullable=True),
    sa.Column('transformation_reference', sa.Text(), nullable=True),
    sa.Column('retrieved_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('retention_until', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("(content_kind = 'original' AND transformation_reference IS NULL) OR (content_kind = 'normalized' AND transformation_reference IS NOT NULL)", name=op.f('ck_text_versions_transformation_reference')),
    sa.CheckConstraint("content_kind IN ('original','normalized')", name=op.f('ck_text_versions_content_kind')),
    sa.CheckConstraint("content_reference ~ '[^[:space:]]'", name=op.f('ck_text_versions_content_reference_nonblank')),
    sa.CheckConstraint("text_content ~ '[^[:space:]]'", name=op.f('ck_text_versions_text_content_nonblank')),
    sa.CheckConstraint("transformation_reference ~ '[^[:space:]]'", name=op.f('ck_text_versions_transformation_reference_nonblank')),
    sa.CheckConstraint("version_key ~ '[^[:space:]]'", name=op.f('ck_text_versions_version_key_nonblank')),
    sa.CheckConstraint('(text_content IS NULL) <> (content_reference IS NULL)', name=op.f('ck_text_versions_content_choice')),
    sa.ForeignKeyConstraint(['collection_event_id', 'source_id'], ['collection_events.id', 'collection_events.source_id'], name=op.f('fk_text_versions_collection_event_id_collection_events'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['source_record_id', 'source_id'], ['source_records.id', 'source_records.source_id'], name=op.f('fk_text_versions_source_record_id_source_records'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_text_versions')),
    sa.UniqueConstraint('source_record_id', 'version_key', name=op.f('uq_text_versions_source_record_id'))
    )
    op.create_index('ix_collection_events_policy_id_source_id', 'collection_events', ['policy_id', 'source_id'], unique=False)
    op.create_index('ix_collection_events_source_id', 'collection_events', ['source_id'], unique=False)
    op.create_index('ix_source_records_first_collection_event_id_source_id', 'source_records', ['first_collection_event_id', 'source_id'], unique=False)
    op.create_index('ix_text_versions_collection_event_id_source_id', 'text_versions', ['collection_event_id', 'source_id'], unique=False)


def downgrade():
    raise CommandError("Destructive downgrades are not supported in Phase 2A; use a reviewed disposable environment.")
