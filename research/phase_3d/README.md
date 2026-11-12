# Phase 3D CareerNet sampling protocol

CareerNet v1.1 is conditionally selected for the English pilot on education,
career expectations, and future uncertainty. The unit is a distinct source
question. An asker identifier groups contributions operationally and does
not verify a unique person. The pilot concerns this curated CareerNet release.

## Research baseline

Phase 3C reported 7,984 question-answer rows, 3,000 distinct questions, 2,483
asker identifiers, 2,080 questions with at least 30 words, and a median of
41 words. Source dates ran from 2011-09-27 to 2025-03-12 with unknown
timezone. In the earlier 120-question inspection, keyword indicators flagged
60 education, 48 career expectations and 14 broad uncertainty signals.
These are historical, unvalidated indicators. Phase 3D uses fictional rows.

The Phase 3A runner already illustrates deterministic text preparation,
group-aware analysis, pinned provenance, independent review attestation,
disclosure-limited reports and synthetic regression tests. Its workbook
parser, model runner and workbook-specific review contract stay separate.
This utility uses the same separation of private inputs and aggregate output
with the Python standard library.

## Shared eligibility and cohort A

For an approved run, define the frame before sampling. Use only the approved
release and question title and body. Check English-language eligibility,
apply privacy review and documented redaction, and use at least 30 words
after preparation for the main frame. Analyze a separately declared 15–29
word sensitivity frame if useful. Apply the same eligibility rules to both
cohorts. Document losses from privacy, language, length and missing grouping
metadata. The synthetic utility rehearses structure, grouping, whitespace
normalization and length checks. It does not decide language or privacy
eligibility. It counts identical title and body text once.

Deduplicate by source question ID before drawing. Collapse identical
question fields repeated across answer rows. Quarantine every variant of an
ID when the title, body, asker or timestamp differs after the documented
whitespace normalization. Keep conflicts out of both cohorts and count
them. Review near-duplicate text across different IDs separately before
fitting models. Do not count repeated answers or repeated questions from one
asker as independent experiences.

Draw up to 200 questions in cohort A. First select one eligible question
per asker by seeded SHA-256 rank. Then draw from those representatives by
an independent rank namespace. The seed, rank algorithm and sample design
must be recorded before examining thematic outcomes. The versioned rank key
is the ASCII string
`hissiyat_phase_3d_sampling_v1:<stage>:<seed>:<question_id>` with question ID
as the tie breaker. Draw stages use distinct fixed names. Input order does
not affect selection.

Optional strata use the source calendar date of the selected representative.
Use 2011–2019, 2020–2022, 2023–2025, other years and unknown date. Assign a
date-only value or a valid datetime to its written calendar year. Preserve
the distinction between a local timestamp with unknown timezone and one
with an explicit offset. Do not convert a source-local year to UTC. Missing
or ambiguous dates are counted and use the unknown stratum. Never guess a
timezone or the order of an ambiguous numeric date.

Give every nonempty stratum one slot when the target allows it and allocate
remaining slots proportionally to remaining capacity, using largest
remainders and stratum-name order for ties. If the budget cannot cover all
nonempty strata, use one unstratified draw and report the fallback. Record
the representative frame size N_h and draw size n_h for each used stratum.
Choose the seed independently of the data. Under the uniform hash-rank
design assumption, each of the m_a eligible questions from asker a has
first-stage probability 1/m_a. This is an asker-balanced design. In an
unstratified draw of n representatives from M eligible asker IDs, each
asker has probability n/M and each of that asker's questions has probability
(n/M)/m_a. The unweighted mean estimates the average of the within-asker
means over eligible questions, with each asker ID contributing equally.
For a binary label, this is the mean within-asker label share. It does not
estimate the fraction of askers who ever used the label or, when m_a varies,
the fraction of all eligible questions with the label.

In a stratified draw, the second-stage probability is n_h/N_h conditional
on the realized representative frame. The selected question determines its
asker's stratum, so the product of stage probabilities describes the
realized sampling path. It is not the marginal inclusion probability over
all possible representative frames. When the stratum sampling fractions
differ, an unweighted pooled proportion describes the selected sample. To
estimate the asker-balanced mean, weight representatives by N_h/n_h and
divide the resulting total by M. For question totals, use m_a × N_h/n_h.
Use the known eligible question count as the denominator for a question-level
proportion. Retain m_a and the stratum in private membership and state the
estimand, design assumptions and denominators in the report.

## Cohort B and interpretation

Screen eligible titles and bodies for at least one education, work, career
or opportunity expression and at least one broad uncertainty expression,
such as being unsure, weighing options, or mentioning job loss. The two
signals can occur anywhere in the same question. Record the screening
version and every exclusion category. Exclude question IDs and all asker
groups selected in A. Rank a single matching representative per remaining
asker with separate enrichment rank namespaces and shortlist up to 200
candidates. Count the shortfall rather than add unrelated questions.
The shortlist is pending contextual review. The final cohort B comprises only
accepted questions and can be smaller than the shortlist. Keep shortlisted,
accepted, excluded and unclear totals distinct.

Include questions with a first-person statement or a contextually supported
personal stake in uncertainty about education, employment, career direction
or future opportunities. Exclude generic advice requests, unrelated
uncertainty, purely hypothetical questions without a personal stake and
cases with insufficient or privacy-sensitive evidence. Record a reason for
each reviewed exclusion. Mentioning uncertainty or asking advice is not
evidence of anxiety. The sample remains enriched by design, including the
effects of cue words and the privacy and length criteria. Removing every
asker selected in A also removes their other screen-positive questions.
The B candidate pool therefore depends on the realized A draw, including
its seed and any unequal sampling fractions across strata. This exclusion
controls cross-cohort dependence and changes who can enter B.

Keep cohort labels and denominators separate in every table and analysis.
Use A for exploratory estimates on the defined curated frame under the
design described above. Use B for theme discovery and analytical variation
reported in aggregate. Do not pool their proportions or generalize either to
CareerVillage, all students, or changes in public sentiment. Compare periods only with their source
coverage, sample design and unknown timezone documented. Publisher scenario
tags, quality scores and other original annotations are excluded from model
inputs and are not reference labels. Before comparing methods, freeze the
corpus, use the same eligible question texts, and group any evaluation
splits by asker.

## Future relevance codebook

Assign multiple labels when supported. For each positive label record
“direct” if the author states it, or “contextual” if supported by the
surrounding text. Record uncertainty rather than extrapolating beyond the
text. Retain evidence notes privately without copying verbatim text.

| Label | Evidence required |
| --- | --- |
| Education or learning decision | A choice or stated need concerning studies, credentials, or a learning path. |
| Career aspiration or expectation | A stated desired role, trajectory, expectation, or career goal. |
| Employment uncertainty | Uncertainty about obtaining, keeping, changing, or finding suitable work. |
| Future opportunity concern | A concern tied to future prospects, timing, or access to opportunities. |
| Reskilling or professional development | A need or decision to gain skills or progress professionally. |
| General information-seeking | A request for information or guidance. This alone is insufficient for B. |
| Explicitly expressed emotion | The author names or plainly expresses their own emotion. Require direct evidence. |
| Personal experience | A first-person account of an event or circumstance, distinct from a general claim. |
| Unclear or insufficient evidence | Evidence is too thin, contradictory, or ambiguous for a decision. |

This codebook is preliminary. After authorization, calibrate two reviewers
on fictional examples and record any revised definitions with a version and
rationale. Freeze the codebook before double-coding a small preselected
subset, for example 30 items balanced across the A sample and B shortlist,
with no shared asker. Both
reviewers code independently before discussion, without seeing prior
annotations, other reviewers' decisions or cohort assignments where
practical. Include B inclusion, label presence, evidence type and reasons
for exclusions. Preserve original decisions. Report sample size, per-label
agreement counts and percent agreement, and Cohen's kappa for binary
decisions where estimable. Report undefined or sparse results and show both
reviewers' positive counts. Calculate agreement before reconciliation.
Discuss disagreements against the frozen criteria. Keep unresolved cases
unclear and exclude them from final B. Record any codebook change and which
items were re-reviewed. If a second reviewer is unavailable, report that
limitation and do not report independent agreement.

## Utility, manifest and data controls

Use Python 3.12 from the repository root.

    python -B -m unittest discover -s research/phase_3d -v

`sample_synthetic` accepts a list or tuple of dictionaries with exactly
`question_id`, `asker_id`, `title`, `body` and `created_at`. Identifiers use
the `synthetic-question-` and `synthetic-asker-` prefixes. These are fixture
conventions, not a detector of real data. Use wholly fictional text. There
is no CSV, API, file, model or production entry point. Shape failures stop
with fixed error codes. Date strings that are unsupported or ambiguous are
counted separately. Public output is the `SamplingResult.aggregate` mapping.
Do not serialize the whole result object.

The manifest schema is `hissiyat_phase_3d_sampling_v1`. The `input` object
identifies synthetic input, its row and unique ID counts, and the SHA-256 of
the sorted newline-joined canonical JSON row multiset. This fingerprint
includes repeated rows and is invariant to input order. The separate
`reference_dataset_not_processed` object identifies the target publisher,
release, license, filename and publisher hash. `design` records the seed,
length threshold and requested temporal strata. Fixed reason counts, date
statuses, separate cohort counts, conditional draw denominators and overlap
counts complete the manifest. It carries no private membership or arbitrary
metadata. Keep actual run settings and the code revision with a future
approved run. Review aggregate disclosure, including sparse cells, before
publishing real results.

Before any real-data preparation, obtain explicit project-owner approval and
institutional clarification of ethics review or exemption and the applicable
data-protection basis. Verify the exact release and checksum, document an
access-controlled local research directory outside Git and outside synced
storage, and agree a source-specific retention and deletion schedule.
In a future approved run, keep a separate private membership file in that
directory with pseudonymous question and asker keys, stage probabilities,
cohort, disposition and reason. Restrict any linkage table and review
records separately. Retain only the fields needed for the declared purpose.

Arrange a documented privacy review bound to the exact input and permitted
use before model processing or reviewer access. Review indirect
identification, school or location clues, and potentially minor contributors.
Pattern screening alone cannot establish anonymity. Keep unreviewed text,
record-level membership and derivatives private. Publish disclosure-reviewed
aggregates. Attribute CareerNet v1.1 to Renaissance Philanthropy and The
Learning Agency, acknowledge CareerVillage.org as the original Q&A source,
link the release and CC BY 4.0, and describe any changes when sharing
adapted material. CC BY 4.0 does not establish an ethics decision or a
data-protection basis. CareerNet v1.1 is a separate release from the
restricted 2019 CareerVillage Kaggle competition distribution.

- [CareerNet v1.1 release](https://github.com/RenaissancePhilanthropy/careernet-data/releases/tag/v1.1)
- [CC BY 4.0 legal code](https://creativecommons.org/licenses/by/4.0/legalcode.en)
- [Erciyes University research ethics guidance](https://etikkurul.erciyes.edu.tr/tr/sosyal-ve-beseri-bilimler-etik-kurulu-yonergesi)
