# Frozen-policy Civil Comments comparison

## Scope and controls

Phase 9C used one separately owner-authorized retrieval of the pinned
`test_public_expanded.csv.gz` artifact. The retrieved 16,425,656 bytes passed
SHA-256 `a5a8fba390af3f17639b1bcef9b1c1b38373d3e45728f7eb814bfe5f3ea1c3d2`.
The mirror revision is `9beb047ad342ac2c3ac209d2d74e0b7c833fe294`.
The same 97,320-row Jigsaw public-leaderboard split underlies every comparison.
No local archive was found in the checked Downloads, private Hissiyat and
workspace artifacts locations before that retrieval.

The two prespecified phrase lists and inclusive 2015-01-01 through 2017-12-31
UTC window come from `civil_study.QUESTIONS` and `study_scope`. Each policy
retains the same required metadata, safety-score and moderation checks, contact
and markup exclusions, English-word heuristic, source-ID/text deduplication,
SHA-256 ranking, four-per-article cap and 100-document sample cap. A policy's
screening reasons record its first failing check. A length exclusion can conceal
another reason that would have failed later. Eligible and selected denominators
therefore describe distinct stages.

Legacy uses the original whitespace-collapsed, 500-character source text and
`explicit_english_rules_v1`. Updated retains NFC-normalized paragraphs, allows
8,000-character documents and uses `explicit_english_spans_v2`. Processing counts
use documents as the observation unit. Both policies run the current full-document
NMF and segment-aggregated MiniLM implementation, with unchanged fit settings and
the existing verified offline model. The primary grouping uses k=2. The original
k=3 sensitivity minimum of 24 documents is preserved. These recomputed model
results have a different embedding protocol from the original Phase 8G run.

The runner reads the one in-memory archive for both policies and both questions.
Linkage uses source metadata and normalized document text in memory after
deduplication. The shared analyzed-document comparison applies both rule versions
to the same updated text. Only aggregate results leave the process. The archive,
comment bodies, document linkage, source IDs, evidence spans, embeddings and
individual cluster assignments are never saved. No additional human annotation
or model/source download was requested.

## Observed coverage

| Measure | Wages legacy | Wages updated | Job opportunities legacy | Job opportunities updated |
| --- | ---: | ---: | ---: | ---: |
| Phrase matches | 236 | 236 | 104 | 104 |
| First exclusion due to length | 125 | 0 | 50 | 0 |
| Eligible before sampling | 79 | 179 | 42 | 76 |
| Selected and analyzed documents | 65 | 100 | 42 | 76 |
| Selected documents over 500 collapsed characters | 0 | 65 | 0 | 34 |
| Analyzed characters | 18,407 | 59,727 | 12,555 | 40,770 |
| Processing segments | 82 | 217 | 52 | 146 |
| Documents with a supported expression match | 0 | 2 | 0 | 1 |
| Retained v2 evidence spans | unavailable | 2 | unavailable | 1 |

Both queries had zero duplicates, invalid source metadata or out-of-window
matches. All selected documents passed processing. No collection/segment limit
exclusion, unavailable topic method or iteration-limit result was recorded.
Updated screening reasons for wages were length 0, privacy/markup 11, language
15, moderation 6 and safety labels 25. The job figures were 0, 3, 5, 7 and 13.
These figures should be read alongside the original first-failure counts.

Wages had 35 selected/analyzed documents in common, 30 legacy-only selected
documents and 65 updated-only selected documents. Expanded eligibility changed
which documents fit within the article and overall caps. Job opportunities
retained all 42 legacy documents and added 34 documents. Counts across questions
can overlap and cannot be summed into a unique corpus size. Character totals
also reflect the stated whitespace-normalization difference.

## Expression evidence and validity

The updated wage sample had one confidence-wording match and one first-person
past-action match. The job sample had one first-person past-action match. All
other supported categories were zero, including information/guidance/support,
explicit problems and reasons. Legacy has no problem/reason categories or span
count, so these measures remain null. All v2 matches began before offset 500.

On the 35 shared wage documents and 42 shared job documents, both rule versions
matched zero documents. No category gained or lost a match in either shared
subset. The three full-sample v2 matches occurred in the added document pool.
The run establishes increased coverage and a small number of inspectable rule
matches. It provides no evidence of improved rule precision or recall on the
shared documents. Rule effects on every added long document were not isolated
in a full crossed-rule evaluation.

V2 recorded 63 quoted and 93 ambiguous/overlong sentence abstentions for wages,
and 75 and 71 for jobs. No evidence-limit stop was recorded. These are sentence
counts, with no claim that every abstention contains a relevant expression.
They are distinct from document exclusions. Unsupported implicit expression,
unmarked attribution, sarcasm and complex negation can cause errors. No new
human reference labels establish accuracy or identify which of the three
matches are false positives. Original excerpts and individual evidence
references are withheld from persisted/public findings.

## Topic diagnostics

| Query / policy | k=2 NMF sizes | k=2 MiniLM sizes | ARI k=2 | NMF silhouette | MiniLM silhouette | ARI k=3 |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| Wages legacy | 57 / 8 | 35 / 30 | -0.0080 | 0.0091 | 0.0770 | 0.1141 |
| Wages updated | 91 / 9 | 49 / 51 | -0.0020 | 0.0062 | 0.0801 | 0.0116 |
| Jobs legacy | 28 / 14 | 16 / 26 | -0.0065 | 0.0168 | 0.0632 | 0.2845 |
| Jobs updated | 35 / 41 | 48 / 28 | 0.3582 | 0.0139 | 0.0899 | 0.2473 |

Both methods were available for every policy at k=2 and k=3. Wages remained
weakly aligned and its updated NMF grouping included a 9% group. Updated jobs
had more agreement at k=2, alongside weak silhouette in both representations
and sensitivity to k. Changing sample composition contributes to these
differences. No parameter was tuned after observing these results. Topic
validity, interpretable shared themes and method superiority remain unverified.
Article context is unavailable and author geography remains unknown. This
selected, safety-screened historical sample supports no population estimate.

## Application and reproducibility

`python -m app.core.civil_comparison` requires either an explicitly authorized
retrieval flag or an existing authorized local source file. It verifies the
fixed byte count and digest before analysis, checks every archive row count and
prints only the allowlisted aggregate report. Errors use fixed sanitized codes.
A failed authorized retrieval requires a new owner decision before a retry.

The integrated bilingual topic/event workspace reads curated aggregate data
from `frontend/src/lib/civil-comparison-data.json`, under the existing local
research gate. It shows stage denominators, selection overlap, shared-document
rule outcomes, category/rule counts, abstention units and topic diagnostics.
The display performs no source request. Frontend projection checks pinned
provenance, scope and counter consistency. The final local commit fixes the
comparison code, rule versions and aggregate findings together.

The historical pilot ends with this comparison. A subsequent product phase can
use verified aggregate contracts and provenance to constrain evidence-grounded
AI summaries, with an explicit distinction between measured findings and
interpretation. No generated interpretation was used in this phase.

## Verification

On 18 November 2026 the non-database backend suite passed 448 tests with the
already installed official SDK available for fictional transport tests.
Ninety PostgreSQL integration tests were deliberately deselected. The existing
Starlette/httpx deprecation warning remained. Dependency checking passed.
All 40 frontend contract tests, ESLint, TypeScript validation and the production
build passed. Next.js reported the existing ignored lockfile outside the
repository. Existing bilingual route checks passed.

Isolated Chrome verified Turkish at 430 px and English at 1,365 px, including
the saved aggregate coverage/paired tables, category support, rule counts,
topic diagnostics, fictional long-document and event flows, CSV fallback,
approval gates and production restrictions. Browser traffic stayed on loopback.
The temporary application backend blocked outbound connections and had no
provider authorizations or database configuration. Only the separately
authorized CLI run retrieved the historical archive. No second retrieval or
real-data analysis run was used for regression testing.
