# Bounded human-experience analysis

## Document processing

The main topic/event workspace analyzes eligible English posts and comments in
request memory. Each source record retains its input index, timestamp, type,
available source/thread reference and unknown geography. The Civil Comments
adapter normalizes text to NFC and retains paragraph breaks. Evidence offsets
refer to the adapter's complete analyzed text. Whitespace-normalized,
case-insensitive fingerprints suppress duplicate documents.

The bounds are 100 documents, 8,000 Unicode codepoints per document, 100,000
codepoints per collection, 128 segments per document and 1,200 segments per
collection. Local text-analysis requests also have a 256 KiB JSON limit.
Contiguous segments preserve every input character and prefer sentence or
paragraph boundaries, then whitespace, with at most 400 codepoints per segment.
An unsegmentable document is excluded in full by research analysis. The direct
local text endpoint rejects an invalid collection. Exclusion counts are reported
by reason. No accepted document is truncated.

NMF fits TF-IDF on complete documents with the existing 4,000-feature vocabulary
bound. MiniLM encodes every segment in batches of eight, combines vectors using
segment-character weights and normalizes one vector per document. Tokenizer
overflow beyond 256 tokens causes MiniLM abstention. The main workspace can
still report NMF-only results. Segment averaging is an operational document
representation whose thematic validity has not been independently evaluated.
Segments never increase the topic or expression denominator. Grouping needs at
least 12 eligible documents. Existing source-specific safety/permission gates
continue to apply.

## Versioned expression evidence

The main workspace uses `explicit_english_spans_v2`. Rules identify first-person
emotion wording, stated information/guidance/support needs, direct requests,
first-person past actions, explicit access/affordability problems and explicit
`because` explanations. The response gives a rule ID, category, input-document
index and half-open Unicode-codepoint sentence span for each match. Counts use
distinct documents per category. Categories can overlap. At most 64 evidence
items are retained per document and counts use only retained evidence.

Recognized quoted ranges can span paragraphs. Quoted sentences, reporting cues,
conditional/hypothetical contexts, negation, statement questions and sentences
over 400 codepoints cause abstention. Direct requests require question syntax.
These templates have limited English coverage and can miss paraphrases or
misread sarcasm, attribution and complex syntax. A stated reason is evidence of
wording, with no established causal explanation. An unmatched document can
still express the category. Previous small human-review overlap does not
validate these rules.

Fictional examples show exact matched sentences and expandable complete
documents. Third-party source projections expose only input-document references,
rule IDs, category and offsets. Source text stays in memory and is withheld
from the browser. No source excerpts, per-document cluster assignments,
embeddings or persistent evidence dataset are generated. The separate local
text workbench retains its earlier aggregate-only expression API for existing
callers. The v2 evidence interface belongs to the main research workspace.

## Topic diagnostics and interpretation

NMF reports cosine silhouette over assigned documents in the TF-IDF space.
MiniLM reports cosine silhouette over document vectors. These describe distinct
representations and cannot establish thematic accuracy or method superiority.
An unavailable score stays null. Each displayed score uses its own assigned
document denominator. The UI flags silhouette at most 0.10, a group below 10%
of assigned documents and between-method ARI at most 0.10. These are descriptive
review thresholds with no claim of calibrated significance. ARI compares shared
assignments and accounts for chance. A weak or inconsistent grouping can leave
common interpretable topic structure unverified. Existing model seeds and fit
settings are preserved. Recurring allowlisted keywords remain tentative
descriptors. No generated topic names or causal interpretation is added.

The bilingual view reports processing counts, expression denominators, rule IDs,
source-document anchors and uncertainty. Temporal coverage and search-interest
evidence retain their separate existing contracts. Historical Civil Comments
results still reflect the old 500-character protocol. Phase 9B validation used
fictional inputs. The separately authorized [Phase 9C comparison](civil-policy-comparison.md)
records the subsequent bounded real-corpus evaluation.

## Verification scope

Fictional regression cases exercise full character coverage, late-document
evidence, Unicode offsets, negation, quotations across chunks, ambiguous
attribution, category overlap, per-document counting, disclosure controls,
tokenizer overflow and separation. They establish implementation behavior on
those cases. Real-world precision/recall, long-document thematic validity and
the effect of changed eligibility remain unmeasured. A future separately
authorized evaluation should compare frozen rule/version behavior and processing
coverage on an approved sample, preserving the original historical results.

### Local verification on 18 November 2026

- `python -m pytest -m "not integration" -q` with the existing official SDK
  available passed 443 tests, with 90 database integration tests deselected.
  One existing Starlette/httpx deprecation warning remains. `pip check` passed.
- All 37 frontend contract tests, ESLint, TypeScript validation and the Next.js
  production build passed. The build reported the existing ignored lockfile
  outside the repository.
- Existing bilingual route checks exercised NMF, offline MiniLM and comparison
  modes, request limits, expression challenges and local-only proxy guards.
- Isolated Chrome acceptance passed in Turkish at 430 px and English at
  1,365 px. The long fictional fixture retained 16 documents, 48 segments and
  15,638 codepoints, with 60 evidence spans. Both methods accounted for all
  16 documents. Their fixture silhouettes were 0.1595 and 0.3156 respectively.
  Exact evidence slices, source anchors, event mode, CSV fallback, approval
  gates and production endpoint restrictions passed. Browser traffic stayed
  on loopback and the test backend blocked outbound connections.
- No database-dependent checks, external source requests or real-corpus
  experiments were performed. These checks establish fictional-case behavior.
