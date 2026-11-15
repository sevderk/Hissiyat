# Research checkpoint and blinded reviewer pilot

## Frozen Phase 5A findings

The private Phase 5A result records exact reconstruction of 80 reviewed questions. The primary comparison used 40 A and 40 B questions, including four B cases without supporting contextual evidence. The sensitivity comparison used the same A questions and the 36 positive B cases selected by the existing human judgments. The two methods used the same ordered records within each comparison. For each method, stability is the median adjusted Rand index (ARI) against five refits on stratified draws retaining approximately 80% of the records.

| Analysis | k | NMF sizes | MiniLM + K-means sizes | Between-method ARI | NMF stability | MiniLM stability |
| --- | ---: | --- | --- | ---: | ---: | ---: |
| Primary (80) | 2 | 39 / 41 | 37 / 43 | 0.3518 | 0.8184 | 0.8770 |
| Primary (80) | 3 | 26 / 19 / 35 | 44 / 14 / 22 | 0.1823 | 0.5177 | 0.4989 |
| Sensitivity (76) | 2 | 36 / 40 | 42 / 34 | 0.2140 | 0.7469 | 0.9333 |
| Sensitivity (76) | 3 | 26 / 20 / 30 | 27 / 33 / 16 | 0.2463 | 0.7191 | 0.4731 |

On the 76 common questions, primary versus sensitivity partition ARI was 0.7508 for NMF and 0.9474 for MiniLM at k=2. At k=3 it was 0.8567 for NMF and 0.3547 for MiniLM. In these runs k=2 had the higher measured median resampling stability for both methods. ARI measures partition agreement. Higher stability does not establish topic interpretability or general model superiority.

Human labels were inspected after fitting. General information-seeking appeared across all clusters and could not distinguish them. Other label patterns are exploratory interpretations from one reviewer who received early codebook assistance. The study has no independent ground truth or measured inter-rater reliability yet. The corpus is small and selected, B is purposefully enriched, and MiniLM truncates inputs at 256 tokens. The experiments used seed 42, the pinned MiniLM revision `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`, and Python 3.12.9. The private report retains exact package versions, code fingerprints, source provenance and runtime. No source text, topic terms or individual cluster assignments are part of this checkpoint.

## Independent 12-question pilot

The owner prepares the window only after separate authorisation for real CareerNet retrieval. The second reviewer codes independently and the owner does not answer for them. Keep the first-review files, key, terminal and this operator document out of the reviewer's view. The local window exposes numbered questions and the second reviewer's own saved responses. It displays the same privacy, five topic, evidence and personal-uncertainty controls for all 12 questions.

The selection chooses six privacy-suitable A records, five B records supporting personal uncertainty and one B record judged not to support it. It skips the first five saved review positions as a proxy for early calibration. Exact calibration membership was not recorded. A private keyed rank makes selection reproducible and a separate keyed rank mixes presentation order. The sample intentionally includes a challenging negative and provides an exploratory agreement check. Its distribution does not estimate agreement across all 80 records. Separate opaque IDs and a keyed binding to the frozen first-review decisions enforce correct resumption without storing first-review decisions or cohort membership beside the second review.

Use the established private, unsynchronized Windows storage. From the repository root in PowerShell 7, set `$firstReview` to the completed private Phase 4E review directory. After approval, the owner opens the local console session with:

```powershell
$blindWorkspace = & .\research\phase_4e\new_workspace.ps1
python -B -m research.phase_5b.blinded --approved-careernet-v1.1 --first-review $firstReview --blind-workspace $blindWorkspace
```

In the window, read each question, give the privacy decision, then for suitable text mark the applicable labels or insufficient evidence and decide whether personal uncertainty is supported, unsupported or unclear. Use **Kaydet** and **Sonraki**. Do not show the selection design or discuss expected answers before saving. A resumed session requires separate scope for reacquiring the pinned source and uses the same private workspace. The data file contains only the second reviewer's coded decisions, opaque linkage and the original deletion deadline. Delete it manually once no longer needed and by that deadline. If a crash leaves a lock file, first confirm that the session ended, then remove only that empty lock file before resuming.

Once all 12 independent decisions are saved and the owner confirms their independence, the owner may calculate private aggregate agreement without retrieving the source:

```powershell
python -B -m research.phase_5b.blinded --summarize-confirmed-independent --first-review $firstReview --blind-workspace $blindWorkspace
```

Privacy agreement uses all completed cases. Each topic is compared separately as a binary label only for cases both reviewers found suitable. Personal uncertainty is compared on the jointly suitable B records, because the original form did not collect that decision in A. Counts and percentage agreement are shown with denominators, and null kappa indicates an undefined statistic. Keep raw decision files private. Review aggregate disclosure before considering dashboard integration.
