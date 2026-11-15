"""Run the bounded CareerNet methods comparison and emit aggregate data only."""

import argparse
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from importlib.metadata import distributions
import json
import os
from pathlib import Path
import platform
import random
import subprocess
import sys
from time import perf_counter
import warnings

from research.phase_3a import experiment as methods
from research.phase_3d import sampling
from research.phase_4c import prepare
from research.phase_4e import review, summarize


SCHEMA = "hissiyat_careernet_methods_v1"
RESAMPLES = 5


class ExperimentError(ValueError):
    """A fixed failure reason with no input data."""


@dataclass(frozen=True)
class Document:
    text: str = field(repr=False)
    group: int  # The selected A and B groups are all distinct in Phase 4C.
    cohort: str


def _require_completed_review(state):
    progress = review.review_progress(state)
    if progress != {"A": (40, 40), "B": (40, 40)}:
        raise ExperimentError("expected_80_completed_reviews")
    decisions = state["decisions"]
    if any(decision["privacy"] != "suitable" for decision in decisions.values()):
        raise ExperimentError("review_contains_non_suitable_questions")
    b_outcomes = Counter(decisions[item]["b_decision"] for item in state["items"] if state["items"][item] == "B")
    if b_outcomes["include"] != 36 or sum(b_outcomes[k] for k in ("generic_advice", "outside_scope", "hypothetical")) != 4:
        raise ExperimentError("unexpected_B_review_distribution")


def link_review(items, saved):
    """Require the same opaque IDs, cohort membership and order as the review."""
    reconstructed = [(item.review_id, item.cohort) for item in items]
    if len(reconstructed) != len({identifier for identifier, _ in reconstructed}):
        raise ExperimentError("duplicate_reconstructed_review_id")
    if reconstructed != list(saved["items"].items()) or set(saved["decisions"]) != set(saved["items"]):
        raise ExperimentError("exact_review_linkage_failed")

    documents, decisions = [], []
    for index, item in enumerate(items):
        title, body = (prepare._plain(value).replace("’", "'") for value in (item.title, item.body))
        text = title if title == body else f"{title} {body}".strip()
        if len(sampling.WORD.findall(text)) < prepare.MIN_WORDS:
            raise ExperimentError("reviewed_question_failed_minimum_length")
        documents.append(Document(text, index, item.cohort))
        decisions.append(saved["decisions"][item.review_id])
    return documents, decisions


def _lengths(documents):
    return {
        cohort: methods._describe([len(sampling.WORD.findall(row.text)) for row in documents if row.cohort == cohort])
        for cohort in ("A", "B")
    }


def _agreement(left, right):
    return {"ari": methods._ari(left, right), "common_assigned": int(((left >= 0) & (right >= 0)).sum())}


def _resamples(documents):
    rng = random.Random(methods.SEED)
    cohorts = [[i for i, row in enumerate(documents) if row.cohort == cohort] for cohort in ("A", "B")]
    return [
        sorted(index for cohort in cohorts for index in rng.sample(cohort, len(cohort) * 4 // 5))
        for _ in range(RESAMPLES)
    ]


def _alignment(documents, decisions, labels, k):
    # Count stored labels only after fitting. Keep cohort denominators separate.
    output = {}
    for cohort in ("A", "B"):
        cells = []
        for cluster in range(k):
            matched = [decision for row, decision, label in zip(documents, decisions, labels, strict=True)
                       if row.cohort == cohort and label == cluster]
            counts = Counter(label for decision in matched for label in decision["labels"])
            cell = {"cluster": cluster + 1, "n": len(matched)}
            if len(matched) >= 5:
                cell["labels"] = {label: _disclosed_count(counts[label]) for label in review.LABELS}
                cell["insufficient_evidence"] = _disclosed_count(sum(decision["insufficient"] for decision in matched))
            if cohort == "B" and len(matched) >= 5:
                cell["context_support"] = sum(decision["b_decision"] == "include" for decision in matched)
                cell["context_no_support"] = _disclosed_count(len(matched) - cell["context_support"])
                if isinstance(cell["context_no_support"], str) or cell["context_support"] < 5:
                    cell["context_support"] = None
                    cell["context_no_support"] = None
            cells.append(cell)
        output[cohort] = cells
    return output


def _disclosed_count(count):
    return "1-4" if 0 < count < 5 else count


def _fit_method(documents, vectors, k, resamples):
    started = perf_counter()
    fit = methods._fit(documents, k, vectors)
    if fit is None:
        raise ExperimentError("model_fit_not_available")
    scores = []
    for indices in resamples:
        docs = [documents[index] for index in indices]
        alternate = methods._fit(docs, k, None if vectors is None else vectors[indices])
        scores.append(None if alternate is None else methods._ari(fit.labels[indices], alternate.labels))
    return fit, {
        "sizes": fit.sizes, "empty_clusters": fit.empty_topics, "unassigned": fit.zero_input_rows,
        "solver_warnings": fit.warnings, "resample_ari": methods._describe(scores),
        "resample_attempts": len(resamples), "fit_and_resampling_seconds": round(perf_counter() - started, 3),
    }


def _compare(documents, decisions, vectors):
    resamples = _resamples(documents)
    outcomes, labels = {}, {}
    for k in methods.TOPIC_COUNTS:
        scores, assigned = {}, {}
        for name, features in (("tfidf_nmf", None), ("minilm_kmeans", vectors)):
            fit, scores[name] = _fit_method(documents, features, k, resamples)
            assigned[name] = fit.labels
            scores[name]["human_label_alignment"] = _alignment(documents, decisions, fit.labels, k)
        scores["between_methods"] = _agreement(assigned["tfidf_nmf"], assigned["minilm_kmeans"])
        outcomes[str(k)] = scores
        labels[k] = assigned
    return outcomes, labels


def analyze(documents, decisions, model_directory):
    import numpy as np
    import onnxruntime
    from threadpoolctl import threadpool_limits

    started = perf_counter()
    onnxruntime.disable_telemetry_events()
    with warnings.catch_warnings(), threadpool_limits(limits=methods.CPU_THREADS):
        warnings.simplefilter("ignore")
        started_embeddings = perf_counter()
        vectors = methods._local_embeddings([row.text for row in documents], model_directory)
        embedding_seconds = round(perf_counter() - started_embeddings, 3)
        if vectors.shape != (len(documents), 384) or not np.isfinite(vectors).all():
            raise ExperimentError("invalid_embedding_matrix")
        primary, primary_labels = _compare(documents, decisions, vectors)
        indices = [i for i, (row, decision) in enumerate(zip(documents, decisions, strict=True))
                   if row.cohort == "A" or decision["b_decision"] == "include"]
        subset = [documents[i] for i in indices]
        sensitivity, sensitivity_labels = _compare(subset, [decisions[i] for i in indices], vectors[indices])
        across_subsets = {
            str(k): {name: _agreement(primary_labels[k][name][indices], sensitivity_labels[k][name])
                     for name in primary_labels[k]}
            for k in methods.TOPIC_COUNTS
        }
    return {
        "primary": {"word_lengths": _lengths(documents), "models": primary},
        "human_judgment_selected_sensitivity": {"word_lengths": _lengths(subset), "models": sensitivity},
        "primary_vs_sensitivity_on_common_questions": across_subsets,
        "compute": {"embedding_seconds": embedding_seconds, "analysis_seconds": round(perf_counter() - started, 3),
                    "peak_process_working_set_mib": methods._peak_memory_mib()},
    }


def _model_integrity(directory):
    from hashlib import sha1

    directory = methods._local_external(directory)
    weights = directory / "model.onnx"
    tokenizer = (directory / "tokenizer.json").read_bytes()
    blob = sha1(f"blob {len(tokenizer)}\0".encode() + tokenizer).hexdigest()
    if blob != methods.TOKENIZER_BLOB or methods._digest(weights) != methods.MODEL_SHA256:
        raise ExperimentError("model_integrity_mismatch")


def _reproducibility():
    paths = (Path(__file__), Path(methods.__file__), Path(sampling.__file__), Path(prepare.__file__),
             Path(review.__file__))
    packages = {distribution.metadata["Name"]: distribution.version for distribution in distributions()}
    return {
        "source_sha256": prepare.REFERENCE["publisher_sha256"], "source_size": prepare.SIZE,
        "review_codebook": review.CODEBOOK, "sampling_schema": sampling.SCHEMA, "preparation_schema": prepare.SCHEMA,
        "model": methods.MODEL, "model_revision": methods.MODEL_REVISION,
        "model_sha256": methods.MODEL_SHA256, "tokenizer_git_blob": methods.TOKENIZER_BLOB,
        "code_sha256": {path.relative_to(methods.REPOSITORY).as_posix(): sha256(path.read_bytes()).hexdigest()
                        for path in paths},
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=methods.REPOSITORY,
                                           text=True, stderr=subprocess.DEVNULL).strip(),
        "python": platform.python_version(), "packages": dict(sorted(packages.items())),
        "seed": methods.SEED, "cpu_threads": methods.CPU_THREADS, "token_limit": methods.MAX_TOKENS,
        "min_words": prepare.MIN_WORDS, "k": list(methods.TOPIC_COUNTS),
        "stability": {"resamples": RESAMPLES, "fraction": 0.8, "stratify_by_cohort": True},
        "human_review": {"reviewers": 1, "independent": False, "early_calibration_assistance": True},
    }


def run(workspace, output_directory, model_directory):
    started = perf_counter()
    directory = review._private_directory(workspace)
    output = prepare._private_directory(output_directory, phase="4e")
    prepare._check_windows_access(output, verify_files=True)
    state = review._read_state(directory, prepare.REFERENCE["publisher_sha256"])
    if state is None:
        raise ExperimentError("saved_review_missing")
    _require_completed_review(state)
    config = _reproducibility()
    _model_integrity(model_directory)
    with (directory / review.KEY_FILE).open("rb") as file:
        key = file.read(33)
    if len(key) != 32:
        raise ExperimentError("invalid_review_key")
    payload = prepare._download()
    items = review.review_items(payload, key)
    del payload, key
    documents, decisions = link_review(items, state)
    del items
    result = {"schema": SCHEMA, "exact_review_linkage": True, "reconstructed": len(documents),
              "delete_by_utc": state["delete_by_utc"], "reproducibility": config,
              **analyze(documents, decisions, model_directory)}
    result["compute"]["total_seconds_before_save"] = round(perf_counter() - started, 3)
    if datetime.now(timezone.utc) >= datetime.fromisoformat(state["delete_by_utc"]):
        raise ExperimentError("review_deadline_elapsed")
    prepare._check_windows_access(prepare._private_directory(output, phase="4e"), verify_files=True)
    path = summarize._write_summary(output, result, filename="methods-comparison.json")
    try:
        prepare._check_windows_access(output, verify_files=True)
    except (Exception, KeyboardInterrupt):
        path.unlink(missing_ok=True)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approved-careernet-v1.1", action="store_true", required=True)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--output-directory", required=True, type=Path)
    parser.add_argument("--model-directory", required=True, type=Path)
    args = parser.parse_args()
    try:
        for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
            os.environ[variable] = str(methods.CPU_THREADS)
        os.environ["TOKENIZERS_PARALLELISM"] = "false"
        run(args.workspace, args.output_directory, args.model_directory)
    except (ExperimentError, prepare.PreparationError, review.ReviewError, methods.CorpusError) as error:
        print(json.dumps({"status": "stopped", "reason": error.args[0]}))
        return 2
    except (Exception, KeyboardInterrupt):
        print('{"status":"stopped","reason":"local_execution_failed"}')
        return 2
    print('{"status":"complete"}')
    return 0


if __name__ == "__main__":
    sys.exit(main())
