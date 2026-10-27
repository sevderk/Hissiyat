# Minimal source-independent input contracts

Phase 1D implements five Pydantic validation models in
`backend/app/contracts/inputs.py`. They describe candidate inputs for future
controlled JSON/CSV/API adapters. They do not ingest, persist, normalize, analyze
or authorize data. Existing health endpoints are unchanged; no new endpoint,
PostgreSQL table, migration or dependency is added.

## Implemented metadata

| Model | Required fields | Optional fields and defaults |
| --- | --- | --- |
| `SourcePolicyReference` | `source_id`, `policy_reference` | `usage_status` defaults to `unknown`; `decision_reference` is required if status is `approved` |
| `CollectionMetadata` | `collection_id`, nested `source_policy`, `method`, `occurred_at`, `source_reference` | None |
| `TextRecordInput` | Nested `collection`, `source_record_id`, `retrieved_at`, exactly one of `text` / `content_reference` | `record_id_origin=source`, `local_id_method`, `original_reference`, `published_at`, `language_code=und`, `language_method=undetermined`, `quality_status=unchecked` |
| `TrendSeriesMetadata` | `series_id`, nested `collection`, `descriptor`, `descriptor_kind`, `geographic_scope`, `measurement_unit`, `scaling_context` | `scale_min`, `scale_max` are absent unless declared by the source |
| `TrendObservationInput` | Nested `series`, `interval_start`, `interval_end`, `retrieved_at`, `value_status`, `data_reference` | `value` is required only for `observed`; otherwise absent/null |

References and identifiers must be nonblank strings. References can be source
URLs, documented export/row references or internal policy identifiers; validation
does not fetch them or verify their truth, existence or permitted use. Sources,
research topics and UI locales are not enumerated in these contracts. Text
inputs contain no author/profile/user identity fields. Extra fields are rejected.
Collection methods are `api`, `file_import` and `manual_import`.

Nested metadata avoids unresolved in-memory ID lookups: text records trace through
their collection to source and policy; trend observations trace through their
series and collection. Repeated snapshots are not a database provenance system.
The source-provided record ID is required by default. A documented local fallback
requires `record_id_origin=local` and `local_id_method`; the contract neither
generates identifiers nor guarantees their uniqueness. `original_reference` is
optional when unavailable or not permitted. `quality_status` is `unchecked`,
`accepted` or `flagged`; it is a supplied quality label, not an analysis decision.

## Time and language

Timestamps must be timezone-aware Python datetimes or ISO 8601 datetime strings
with an offset. Numeric epochs, date-only values, impossible dates and naive
datetimes are rejected; future adapters must explicitly handle such source
formats. Offsets are retained and ordering compares actual instants.

`published_at` is optional and never replaced with retrieval/import time. When
present, it cannot follow `retrieved_at`. `has_publication_timestamp` reports only
the presence of valid metadata: false prevents treating an unknown publication
time as known, and true does not establish research eligibility. Temporal research
still needs source semantics, precision, corpus selection and permission review.
`occurred_at` describes the collection/import event; record retrieval can precede
a later file import. No equality/order between event and record retrieval is
assumed for arbitrary adapters.

Trend intervals use explicit start/end instants with half-open semantics
`[start, end)` and require `start < end`. No granularity, alignment or timezone is
inferred from a source label. An adapter must map a source's reporting boundaries
explicitly; an ongoing/partial interval is not certified complete by validation.

Language codes use a deliberately limited syntactic form: two/three lowercase
letters, optionally followed by hyphen-separated alphanumeric subtags. `und`
explicitly means undetermined. `language_method` is `undetermined`, `source`,
`human` or `automated`; the undetermined method requires `und`. These fields are
claims about supplied metadata, not language detection or a complete BCP 47
registry validator. No locale defaults to Turkish or English, and UI translation
does not establish NLP language support. A human language assessment does not
stand for independent research annotations.

## Rights and trend semantics

`unknown`, `unverified`, `approved` and `denied` remain separate policy states.
Structurally valid metadata may describe any of them; it must never be used as an
ingestion permission gate. An asserted approval requires a decision reference,
but even that reference is not independently authenticated here. A future
permission gate must resolve a trusted decision and enforce its scope, operations,
conditions, retention and withdrawal rules. No real candidate source is currently
approved for collection or analysis.

Trend observations are separate from textual records. A term/topic descriptor,
geographic scope, measurement unit and scaling context belong to a series. A
measurement must be a finite JSON/Python number, not a boolean or numeric string.
Adapters must explicitly parse CSV numbers and missing/suppression markers.
`missing` and `suppressed` require null/absent values and are never converted to
zero. An observed zero remains a measurement.

Optional source-declared bounds are inclusive and checked against each value;
inverted bounds are rejected. There is no universal 0..100 range. A source adapter
may declare that range for a specific normalized index, but another declared
scale remains valid. Google Trends relative search interest is not absolute
search counts. The contract does not certify series comparability, normalization
windows or representativeness, and does not convert correlations into causation.

## Validation and safe error reporting

Call `Model.model_validate(payload)` or `Model.model_validate_json(json_payload)`
at an adapter boundary. Models reject extra fields and are immutable through
ordinary assignment. Do not use validation-bypassing `model_construct()` or
`model_copy(update=...)` to accept external input.

Inline text uses `SecretStr`: it preserves exact Unicode content but masks model
representations and standard JSON dumps. Future explicitly authorized processing
would retrieve it with `record.text.get_secret_value()`; this phase does not do
so outside synthetic tests. Masking is not encryption, PII removal or storage
permission. References can also contain sensitive information; never log models
or complete input payloads.

For diagnostics, catch `pydantic.ValidationError` and log only
`validation_error_summary(error)`, which returns error-code counts. It omits
inputs, locations (unknown keys can contain personal content), messages and
context. `hide_input_in_errors=True` further hides standard input displays, but
raw `.errors()`, `.json()`, exception strings/tracebacks and request logging are
not a safe reporting interface. No validation logger or API error handler is
installed by this phase.

## Deferred conceptual design

The Phase 1C concepts `SourceRecord`, `TextVersion`, `LanguageAssessment`,
`QualityAssessment`, `CorpusVersion`, `TrendSeries`, `TrendObservation`,
`AnalysisRun`, `ModelVersion`, `HumanAnnotation` and `EvaluationRun` remain
conceptual persistence/research entities. These input models are not their
database implementation, and policy/collection metadata is not a full policy
registry or collection-event store.

Batch duplicate detection, cross-record consistency, source-specific format and
rights verification, source adapters, database provenance, corpus versioning,
normalization, NLP, evaluator identities and inter-evaluator agreement are not
implemented. Fixtures in `backend/tests/fixtures/synthetic_contracts.json` are
explicitly synthetic and never evidence about a real source or population.
Database models and ingestion require a separate approved phase.
