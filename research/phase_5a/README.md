# CareerNet local methods comparison

This bounded exploratory run compares TF-IDF + NMF and English MiniLM + K-means at fixed `k=2` and `k=3`. It uses the existing Phase 3A fit and CPU embedding routines, Phase 3D sampling, Phase 4C screening, and Phase 4E review linkage. A separate owner decision is required before retrieving the real data. The experiment is local and contains no hosted model calls.

The runner requires 40 suitable completed reviews in each cohort and verifies every reconstructed opaque ID, cohort, and position. Original source bytes, question text, review key, labels, embeddings, and cluster assignments stay in process memory. The source file is verified before parsing. The original review and key are opened for reading only. Text preprocessing removes recognized markup and collapses whitespace, normalizes curly apostrophes and avoids repeating an identical title and body. Negations are preserved. The methods receive the same ordered text. MiniLM uses the Phase 3A limit of 256 tokens and TF-IDF uses its own tokenization and stopwords.

The primary run uses all 80 reviewed questions, including the four negative B judgments. The human-judgment-selected sensitivity run uses 40 A and 36 positive B questions. The human labels are never features. Cluster-by-cohort tables describe alignment with the stored labels after fitting. They omit label details for cohort-cluster cells smaller than five and mask positive counts below five. No topic terms are exported.

Between-method adjusted Rand index uses commonly assigned records for each subset and each k. Stability uses five seeded draws without replacement, each retaining 80% of each cohort rounded down. The models are refitted, then compared against their primary or sensitivity fit on the retained records. NMF recomputes TF-IDF on each draw. MiniLM vectors are reused for identical input documents. Reference versus resample and primary versus sensitivity results compare partitions. Undefined comparisons are counted separately. Labels come from one reviewer with early codebook assistance, and no independent second review is available. These results support exploratory interpretation, with no claims of model superiority or prevalence.

Install the pinned [Phase 3A requirements](../phase_3a/requirements.txt) in a local Python 3.12 environment outside Git. Verify the published files from [the pinned MiniLM revision](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/tree/1110a243fdf4706b3f48f1d95db1a4f5529b4d41) using the existing Phase 3A checks. The model directory must contain `model.onnx` from `onnx/model.onnx` and `tokenizer.json`. Run this from the repository root after separate authorization:

```powershell
$resultsDirectory = & .\research\phase_4e\new_workspace.ps1
python -B -m research.phase_5a.experiment --approved-careernet-v1.1 --workspace $reviewWorkspace --output-directory $resultsDirectory --model-directory $modelDirectory
```

The private results directory contains one aggregate JSON with model and package versions, code fingerprints, cluster sizes and comparison statistics. Delete the private results manually when no longer needed and by the review's existing deadline, at the latest 28 February 2027 Istanbul day end. Keep earlier deadlines in force. The public model assets and runtime directory are separate.

```powershell
python -B -m unittest discover -s research/phase_5a -v
```
