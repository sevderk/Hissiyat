# Phase 3A local NLP feasibility

This experiment compares TF-IDF and NMF with local MiniLM embeddings and
K-means on the Khamis interview workbooks. It has no FastAPI, PostgreSQL or
ingestion dependency. Its output describes a small set of prompted responses.

## Inputs and execution

For a separately authorized run, obtain version 1 from the official Mendeley
record under CC BY 4.0. Keep the workbooks and all run files in an
access-restricted local directory outside the repository. Supply a private JSON
manifest with `source`, `doi`, `version`, `license`, `downloaded_utc`
and a `files` list. Each file entry has `local_name`,
`file_id`, `bytes` and `publisher_sha256`. Match each hash to the publisher's
file metadata. Use a dedicated input directory containing only the ten workbooks.

Record `downloaded_utc` as a full ISO 8601 date and time with seconds and an
explicit offset or `Z`. The runner rejects invalid dates, unknown offsets,
free text and duplicate manifest keys. It emits the normalized UTC timestamp
and fixed dataset metadata without copying arbitrary manifest fields to results.

### Trusted privacy review

An authorized reviewer examines the response text for identifying details and
sensitive combinations and verifies the file inventory. If the review supports
local analysis, the reviewer explicitly creates a separate UTF-8 JSON record.
It contains `schema: "hissiyat_phase_3a_privacy_review_v1"`,
`decision: "reviewed_for_local_analysis"`, the dataset `doi`, `version: 1`,
an `expires_utc` timestamp with an explicit offset, and a `files` list with
the same four fields per workbook. Review covers those exact local names,
publisher file IDs, byte sizes and SHA-256 digests until the stated expiry.
The reviewer withholds the record when material privacy uncertainty remains.

Keep the record outside Git and outside the workbook directory, in a
reviewer-controlled location. After issuing it, the reviewer supplies its
SHA-256 through a trusted channel or controls the launch configuration. Pass
that independently obtained digest as `--trusted-review-sha256`. The dataset
operator supplies the current manifest. The reviewer or trusted launcher
controls the review path and digest independently of that manifest. The runner
does not issue review records or derive trusted digests from the presented
manifest or record. Manifest fields such as `approved` grant no authority.

The runner verifies the record against the trusted digest, checks expiry and
compares the manifest and exact directory inventory with the review. It reads
each workbook once, verifies the byte size and SHA-256, and parses the same
verified bytes. A changed file or expanded inventory requires a fresh review.
The digest protects the record relative to the supplied trust pin. The
reviewer's authority comes from the controlled record and launch procedure.
A compromised local account or launcher that can replace both the record and
trusted digest is outside this boundary. Access permission, ethics and
retention requirements apply separately.

Use Python 3.12 and install the pinned packages in an isolated virtual
environment outside the repository. The XLSX reader uses `defusedxml` for
every XML part it reads, with DTDs, custom entities and external references
disabled. It also bounds ZIP size, member count and decompressed sizes. For the
optional embedding method, place
`onnx/model.onnx` from the official model repository as `model.onnx` beside
`tokenizer.json`. Use the revision recorded in the model link below. The
runner checks both artifacts and reads them locally. Omit `--model-dir` to run
only the classical method.

Run from the repository root. Substitute private absolute paths and the
current full Git commit hash.

```text
python -m unittest discover -s research/phase_3a -v
python -m research.phase_3a.experiment --inputs PRIVATE_WORKBOOK_DIRECTORY --provenance PRIVATE_MANIFEST_JSON --review-record REVIEWER_CONTROLLED_JSON --trusted-review-sha256 REVIEWER_SUPPLIED_SHA256 --output PRIVATE_NEW_RESULTS_JSON --model-dir PRIVATE_MODEL_DIRECTORY --source-revision FULL_GIT_HASH
```

- [Mselem Khamis, Academic Adjustment and Learning Barriers, v1](https://data.mendeley.com/datasets/gw43mcsxzm/1)
- [MiniLM official repository at the pinned revision](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/tree/1110a243fdf4706b3f48f1d95db1a4f5529b4d41)

## Analysis and disclosure

The fixed workbook layout pairs a question in column C with its answer in
column D. Only answers enter the corpus. A workbook is an operational group.
The mapping between files and unique participants has not been independently
verified. Exact repeats are counted without automatic deletion.

The runner stops on recognizable identifiers such as ordinary and word-based
email addresses, written and spoken phone patterns, and unresolved contact
cues. Contact matching uses normalized whitespace and a bounded mapping of
common Unicode hyphens, dashes and minus signs to ASCII hyphen-minus. This
mapping applies only to detection. An explicitly labeled academic or school
year range is treated as a year range. Contact cues remain active. A valid
review never overrides these checks. The runner also excludes flagged private
contexts, short responses and answers that fail the simple English marker
check. Human review addresses contextual and indirect identification.
Pattern screening can miss unsupported formats or reject benign text. The
reviewed response text and its features remain private research data.

Preprocessing preserves the normalized wording of retained responses,
including rare terms and negation. Both methods start from the same records
at the 30-word and 15-word thresholds, with two and three topics or clusters.
TF-IDF builds its own features, keeping negations and terms seen in one
document. MiniLM uses CPU inference, attention-masked mean pooling and L2
normalization. The report counts words before and after normalization for the
retained 15-word subset, words excluded after normalization, and retained words
per subset. These counts describe corpus preparation, before TF-IDF feature
selection or MiniLM tokenization.

Cluster sizes and terms come from the fitted models. Public terms must be on
the fixed disclosure list and supported by multiple groups. Adjusted Rand
Index (ARI) describes chance-adjusted agreement between assignments on common
records. Group omission, threshold changes and repeated wording checks assess
stability. These comparisons provide exploratory evidence about assignments.

Keep only aggregate results and non-content provenance after the experiment.
Do not share source workbooks, projected text, individual assignments, or
embeddings. Report the sample size and the effect of interview prompts, and
treat any thematic interpretation as exploratory.

## Historical run and validation scope

The earlier Phase 3A run demonstrated that both methods executed locally on
the Khamis snapshot. Its frequency filter retained 55.82% of the words in
retained responses. It included 65 responses from ten workbook groups at 15
words and 26 responses from four groups at 30 words. Those counts and ARI
values describe the earlier preprocessing. The corrected runner identifies
its preprocessing as `screened_responses_v3` and has been checked only on
synthetic data.

The prompted interviews provide a narrow view of academic adjustment.
Responses within one workbook can be dependent and participant identities
across workbooks have not been verified. The study lacks verified temporal
coverage, a sample of natural online discussions and independent human
evaluation. The technical demonstration supports no validated
population-level conclusions or ranking of the methods.

Git contains the runner and synthetic tests. Reproducing an authorized
real-data run requires the private verified input snapshot, the matching
manifest, a current trusted review, the exact model artifacts and the run
environment. The synthetic tests cover workbook structure, XML security,
trusted review binding, Unicode contact screening, UTC timestamp validation,
negation and matching inputs across methods.
