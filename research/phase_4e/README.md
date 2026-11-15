# CareerNet local human review

This native Windows utility supports one owner reviewing up to 40 questions from each reconstructed cohort. It uses Python 3.12 and its Tk distribution. It opens no network listener, browser, or dashboard. Real mode checks for the active local Windows console before using the official HTTPS release. Use a private desktop without screen sharing, recording, or a synced clipboard. The window shows one question at a time and hides source IDs. Source text is held in memory. Tk displays the title and body as plain text after the parser's whitespace normalization.

## Reconstructing the review subset

The shared [Phase 4C preparation](../phase_4c/README.md) verifies the official source size and SHA-256, applies the same privacy and linked-author exclusions, and runs the accepted [Phase 3D sampling and codebook](../phase_3d/README.md#future-relevance-codebook) with seed 42, source-calendar strata for A, and targets of 200 for A and B. The utility then sorts each final cohort by SHA-256 of `hissiyat_careernet_review_v1:subset:42:<cohort>:<source-question-id>` and selects the first 40 in each. Shortfalls are displayed. The preceding feasibility run retained only aggregates, so individual membership cannot be independently compared with that run.

## Launching from Windows PowerShell

Use **PowerShell 7**. The helper creates a distinct local fixed-drive folder under `%LOCALAPPDATA%\Hissiyat` with owner-only Windows permissions and checks common sync locations. Confirm the folder is outside any additional sync or backup service you configured. Test the form first without contacting the source:

```powershell
$demoWorkspace = & .\research\phase_4e\new_workspace.ps1
python -B -m research.phase_4e.review --fictional --workspace $demoWorkspace
```

After explicit authorization for real source access, create one separate workspace for this review:

```powershell
$reviewWorkspace = & .\research\phase_4e\new_workspace.ps1
python -B -m research.phase_4e.review --approved-careernet-v1.1 --workspace $reviewWorkspace
```

Keep the workspace path for later sessions. Use the same command and same workspace path to resume. A restart retrieves the same pinned file again because participant text is held in memory only. Obtain explicit authorization covering that retrieval before opening real mode. Keep only one session open per workspace.

## Reviewing a question

1. Choose a privacy decision first. Select suitable for further local research, needs additional privacy review, or exclude for a privacy concern. The latter two decisions disable relevance coding. Inspect possible indirect identifiers and disclosures involving minors. The automatic screen does not establish anonymity.
2. For a suitable question, use the Phase 3D codebook shown in the guide. Mark each applicable label as direct if stated or contextual if supported by the text. The emotion label requires direct evidence. Choose insufficient evidence if no positive label is supportable. General advice seeking alone establishes neither personal uncertainty nor anxiety.
3. For a suitable Cohort B question, decide whether the text supports personal uncertainty about education, employment, career direction, or future opportunities. The form supports generic advice, out of scope, hypothetical or no personal stake, and unclear decisions. This contextual judgment is separate from the automated enrichment signal.
4. Click **Kaydet** before moving to **Önceki** or **Sonraki**. The header shows saved counts separately for A and B. Closing the window releases the source text from the process. Unreviewed questions remain undecided.

## Private records and retention

The workspace stores `review.key` and `review.json` only. A random local key derives stable HMAC-SHA-256 review IDs. The JSON contains opaque IDs, cohorts, fixed decision codes, progress position, source checksum, codebook version and deletion cutoff. It has no text, source IDs or free-text notes. Save uses an atomic replacement in the same restricted directory. Keep the key and decisions private. Delete both as soon as no longer necessary, and at the latest by 28 February 2027 Istanbul day end. Deletion is manual. The review utility does not grant NLP access or change the retention of earlier artifacts.

## Synthetic verification

```powershell
python -B -m unittest discover -s research/phase_4e -v
```

## Summarizing a completed review

From the repository root, set `$reviewWorkspace` to the existing private review directory. Create a separate private directory for the report:

```powershell
$summaryDirectory = & .\research\phase_4e\new_workspace.ps1
python -B -m research.phase_4e.summarize --workspace $reviewWorkspace --output-directory $summaryDirectory
```

The summary validates the codebook and requires 40 completed decisions in each cohort. It reads the coded review JSON, leaves the original files intact and writes only `review-summary.json` in the new directory. Label percentages use the privacy-suitable count within each cohort. Multiple labels can make the percentages sum above 100%. Insufficient evidence has no direct or contextual count. In B, unresolved contextual decisions and decisions unavailable for privacy reasons are tracked separately. The full counts are private. Review sparse cells and combinations before publication. The existing deletion deadline also applies to the summary.
