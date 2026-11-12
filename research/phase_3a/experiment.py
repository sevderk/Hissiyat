"""Run the bounded Phase 3A methods comparison, with aggregate output only."""

import argparse
from collections import Counter, defaultdict
import ctypes
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import file_digest, sha1, sha256
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
import re
import statistics
import sys
from time import perf_counter
import warnings

from .corpus import MAX_WORKBOOK_BYTES, THRESHOLDS, CorpusError, prepare, read_workbook


DOI = "10.17632/gw43mcsxzm.1"
SOURCE = "https://data.mendeley.com/datasets/gw43mcsxzm/1"
PRIVACY_REVIEW_SCHEMA = "hissiyat_phase_3a_privacy_review_v1"
PRIVACY_REVIEW_DECISION = "reviewed_for_local_analysis"
MAX_RECORD_BYTES = 64 * 1024
WORKBOOK_COUNT = 10
SHA256_HEX = re.compile(r"[0-9a-f]{64}")
MODEL = "sentence-transformers/all-MiniLM-L6-v2"
MODEL_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
MODEL_SHA256 = "6fd5d72fe4589f189f8ebc006442dbb529bb7ce38f8082112682524616046452"
TOKENIZER_BLOB = "cb202bfe2e3c98645018a6d12f182a434c9d3e02"
TOPIC_COUNTS = (2, 3)
SEED = 42
CPU_THREADS = 2
BATCH_SIZE = 8
MAX_TOKENS = 256
REPOSITORY = Path(__file__).resolve().parents[2]
ISO_TIMESTAMP = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,6})?(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])"
)
PUBLIC_TERMS = frozenset(
    "academic access activities adjustment advice assignments assistance barriers classmates "
    "classes communication confidence course courses culture difficult difficulties discussion "
    "education encourage expectations experience experiences feedback help information "
    "interaction language learning lectures listen listening materials motivation opportunities "
    "participation peers practice pressure professors resources skills social speaking "
    "strategies students studies study support teachers teaching time understand understanding "
    "university work writing".split()
)


@dataclass
class Fit:
    labels: object = field(repr=False)
    sizes: list[int]
    empty_topics: int
    zero_input_rows: int
    warnings: int
    terms: list[list[str]]


def _local_external(path):
    path = path.resolve()
    if path == REPOSITORY or path.is_relative_to(REPOSITORY) or str(path).startswith("\\\\"):
        raise CorpusError("expected_private_local_path")
    return path


def _digest(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def _canonical_download_time(value):
    if not isinstance(value, str) or not ISO_TIMESTAMP.fullmatch(value) or value.endswith("-00:00"):
        raise CorpusError("invalid_download_timestamp")
    try:
        utc = datetime.fromisoformat(value).astimezone(timezone.utc)
    except (ValueError, OverflowError):
        raise CorpusError("invalid_download_timestamp") from None
    return utc.isoformat().removesuffix("+00:00") + "Z"


def _unique_manifest_fields(pairs):
    fields = dict(pairs)
    if len(fields) != len(pairs):
        raise CorpusError("duplicate_manifest_field")
    return fields


def _record_bytes(path, error_code):
    try:
        with path.open("rb") as stream:
            payload = stream.read(MAX_RECORD_BYTES + 1)
    except OSError:
        raise CorpusError(error_code) from None
    if len(payload) > MAX_RECORD_BYTES:
        raise CorpusError(error_code)
    return payload


def _parse_record(payload, error_code):
    try:
        return json.loads(payload.decode("utf-8"), object_pairs_hook=_unique_manifest_fields)
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        raise CorpusError(error_code) from None


def _workbook_inventory(records, error_code):
    if not isinstance(records, list) or len(records) != WORKBOOK_COUNT:
        raise CorpusError(error_code)
    inventory = {}
    names, identifiers = set(), set()
    for entry in records:
        if not isinstance(entry, dict) or set(entry) != {"local_name", "file_id", "bytes", "publisher_sha256"}:
            raise CorpusError(error_code)
        name, identifier, size, digest = (
            entry["local_name"], entry["file_id"], entry["bytes"], entry["publisher_sha256"]
        )
        if (
            not isinstance(name, str)
            or not name.casefold().endswith(".xlsx")
            or any(char in name for char in "/\\:\0")
            or name.casefold() in names
            or not isinstance(identifier, str)
            or not identifier.strip()
            or identifier in identifiers
            or type(size) is not int
            or not 0 < size <= MAX_WORKBOOK_BYTES
            or not isinstance(digest, str)
            or not SHA256_HEX.fullmatch(digest)
        ):
            raise CorpusError(error_code)
        names.add(name.casefold())
        identifiers.add(identifier)
        inventory[name] = (identifier, size, digest)
    return inventory


def _reviewed_inventory(review_record, trusted_review_sha256, inputs, provenance):
    if review_record is None or trusted_review_sha256 is None:
        raise CorpusError("privacy_review_required")
    if not isinstance(trusted_review_sha256, str) or not SHA256_HEX.fullmatch(trusted_review_sha256):
        raise CorpusError("invalid_privacy_review")
    review_record = _local_external(review_record)
    if review_record == provenance or review_record.is_relative_to(inputs):
        raise CorpusError("expected_separate_privacy_review")
    payload = _record_bytes(review_record, "invalid_privacy_review")
    if sha256(payload).hexdigest() != trusted_review_sha256:
        raise CorpusError("privacy_review_integrity_mismatch")
    review = _parse_record(payload, "invalid_privacy_review")
    if (
        not isinstance(review, dict)
        or type(review.get("version")) is not int
        or (review.get("schema"), review.get("decision"), review.get("doi"), review["version"])
        != (PRIVACY_REVIEW_SCHEMA, PRIVACY_REVIEW_DECISION, DOI, 1)
    ):
        raise CorpusError("invalid_privacy_review")
    try:
        expires = _canonical_download_time(review.get("expires_utc"))
    except CorpusError:
        raise CorpusError("invalid_privacy_review") from None
    if datetime.fromisoformat(expires) <= datetime.now(timezone.utc):
        raise CorpusError("privacy_review_expired")
    return _workbook_inventory(review.get("files"), "invalid_privacy_review")


def _verified_corpus(inputs, provenance, *, review_record=None, trusted_review_sha256=None):
    inputs = _local_external(inputs)
    provenance = _local_external(provenance)
    source = _parse_record(_record_bytes(provenance, "unexpected_dataset_provenance"), "unexpected_dataset_provenance")
    if (
        not isinstance(source, dict)
        or type(source.get("version")) is not int
        or (source.get("doi"), source["version"], source.get("license"), source.get("source"))
        != (DOI, 1, "CC BY 4.0", SOURCE)
    ):
        raise CorpusError("unexpected_dataset_provenance")
    downloaded = _canonical_download_time(source.get("downloaded_utc"))
    intended = _workbook_inventory(source.get("files"), "unexpected_dataset_inventory")
    reviewed = _reviewed_inventory(review_record, trusted_review_sha256, inputs, provenance)
    if intended != reviewed:
        raise CorpusError("privacy_review_inventory_mismatch")
    try:
        files = sorted(inputs.iterdir())
    except OSError:
        raise CorpusError("workbook_inventory_mismatch") from None
    if {file.name for file in files} != reviewed.keys():
        raise CorpusError("workbook_inventory_mismatch")
    workbooks = []
    for file in files:
        _, size, digest = reviewed[file.name]
        if file.is_symlink() or not file.is_file() or _local_external(file).parent != inputs:
            raise CorpusError("unexpected_workbook_path")
        try:
            with file.open("rb") as stream:
                payload = stream.read(size + 1)
        except OSError:
            raise CorpusError("workbook_integrity_mismatch") from None
        if len(payload) != size or sha256(payload).hexdigest() != digest:
            raise CorpusError("workbook_integrity_mismatch")
        workbooks.append(payload)
    responses, signatures = [], set()
    for group, payload in enumerate(workbooks):
        group_rows, signature = read_workbook(payload, group)
        responses.extend(group_rows)
        signatures.add(signature)
    prepared, counts = prepare(responses)
    counts["question_sequence_count"] = len(signatures)
    return prepared, counts, downloaded


def _local_embeddings(texts, directory):
    import numpy as np
    import onnxruntime as ort
    from tokenizers import Tokenizer

    directory = _local_external(directory)
    weights, tokenizer_path = directory / "model.onnx", directory / "tokenizer.json"
    tokenizer_blob = tokenizer_path.read_bytes()
    blob_hash = sha1(f"blob {len(tokenizer_blob)}\0".encode() + tokenizer_blob).hexdigest()
    if _digest(weights) != MODEL_SHA256 or blob_hash != TOKENIZER_BLOB:
        raise CorpusError("model_integrity_mismatch")
    tokenizer = Tokenizer.from_file(str(tokenizer_path))
    tokenizer.enable_truncation(max_length=MAX_TOKENS)
    tokenizer.enable_padding(pad_id=tokenizer.token_to_id("[PAD]"), pad_token="[PAD]")
    options = ort.SessionOptions()
    options.intra_op_num_threads = CPU_THREADS
    options.inter_op_num_threads = 1
    options.log_severity_level = 4
    session = ort.InferenceSession(str(weights), sess_options=options, providers=["CPUExecutionProvider"])
    input_names = {item.name for item in session.get_inputs()}
    if not {"input_ids", "attention_mask"} <= input_names <= {"input_ids", "attention_mask", "token_type_ids"}:
        raise CorpusError("unexpected_model_inputs")
    vectors = []
    for offset in range(0, len(texts), BATCH_SIZE):
        batch = tokenizer.encode_batch(texts[offset:offset + BATCH_SIZE])
        fields = {
            "input_ids": [item.ids for item in batch],
            "attention_mask": [item.attention_mask for item in batch],
            "token_type_ids": [item.type_ids for item in batch],
        }
        encoded = {key: np.asarray(fields[key], dtype=np.int64) for key in input_names}
        hidden = session.run(None, encoded)[0]
        if hidden.ndim != 3 or hidden.shape[-1] != 384:
            raise CorpusError("unexpected_model_output")
        mask = encoded["attention_mask"][..., None]
        pooled = (hidden * mask).sum(axis=1) / mask.sum(axis=1).clip(min=1)
        vectors.append(pooled / np.linalg.norm(pooled, axis=1, keepdims=True).clip(min=1e-12))
    return np.concatenate(vectors).astype(np.float32)


def _tfidf(rows):
    from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer

    negations = {
        "cannot", "neither", "never", "no", "nobody", "none", "noone",
        "nor", "not", "nothing", "nowhere", "without",
    }
    stop_words = sorted(ENGLISH_STOP_WORDS - negations)
    vectorizer = TfidfVectorizer(
        token_pattern=r"(?u)\b[^\W\d_]+(?:'[^\W\d_]+)?\b", stop_words=stop_words,
    )
    matrix = vectorizer.fit_transform(row.text for row in rows)
    return matrix, vectorizer.get_feature_names_out()


def _public_terms(rows, labels, vocabulary, weights, topic_count):
    import numpy as np

    topic_groups = defaultdict(set)
    total_groups = defaultdict(set)
    for row, label in zip(rows, labels):
        for term in set(row.text.split()) & PUBLIC_TERMS:
            total_groups[term].add(row.group)
            topic_groups[int(label), term].add(row.group)
    return [
        [
            term for i in np.argsort(-weights[topic], kind="stable")
            if weights[topic, i] > 0
            and (term := str(vocabulary[i])) in PUBLIC_TERMS
            and len(total_groups[term]) >= 3 and len(topic_groups[topic, term]) >= 2
        ][:5]
        for topic in range(topic_count)
    ]


def _fit(rows, topic_count, embeddings=None, include_terms=False):
    import numpy as np
    from sklearn.cluster import KMeans
    from sklearn.decomposition import NMF

    if len(rows) < topic_count * 3 or len({row.group for row in rows}) < 3:
        return None
    matrix = vocabulary = weights = None
    if embeddings is None or include_terms:
        try:
            matrix, vocabulary = _tfidf(rows)
        except ValueError:
            if embeddings is None:
                return None
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        if embeddings is None:
            if min(matrix.shape) < topic_count:
                return None
            nmf = NMF(n_components=topic_count, init="nndsvda", random_state=SEED, max_iter=500)
            scores = nmf.fit_transform(matrix)
            labels = scores.argmax(axis=1)
            zero_rows = np.isclose(scores.sum(axis=1), 0)
            labels[zero_rows] = -1
            weights = nmf.components_
        else:
            model = KMeans(n_clusters=topic_count, random_state=SEED, n_init=20)
            labels = model.fit_predict(embeddings)
            zero_rows = np.zeros(len(rows), dtype=bool)
            if matrix is not None:
                weights = np.asarray([
                    np.asarray(matrix[labels == topic].sum(axis=0)).ravel()
                    for topic in range(topic_count)
                ])
    sizes = [int((labels == topic).sum()) for topic in range(topic_count)]
    terms = _public_terms(rows, labels, vocabulary, weights, topic_count) if include_terms and weights is not None else []
    return Fit(labels, sizes, sizes.count(0), int(zero_rows.sum()), len(caught), terms)


def _ari(reference, candidate):
    from sklearn.metrics import adjusted_rand_score

    valid = (reference >= 0) & (candidate >= 0)
    if valid.sum() < 3 or len(set(reference[valid])) < 2 or len(set(candidate[valid])) < 2:
        return None
    return round(float(adjusted_rand_score(reference[valid], candidate[valid])), 4)


def _describe(values):
    values = [value for value in values if value is not None]
    return {
        "count": len(values),
        "min": min(values) if values else None,
        "median": statistics.median(values) if values else None,
        "max": max(values) if values else None,
    }


def _method(rows, embeddings, common_prompts):
    from sklearn.metrics import adjusted_mutual_info_score

    started = perf_counter()
    outcomes = {}
    fits = {}
    for threshold in THRESHOLDS:
        indices = [i for i, row in enumerate(rows) if row.word_count >= threshold]
        subset = [rows[i] for i in indices]
        vectors = None if embeddings is None else embeddings[indices]
        runs = {}
        for count in TOPIC_COUNTS:
            fit = _fit(subset, count, vectors, include_terms=True)
            if fit is None:
                runs[str(count)] = {"status": "insufficient_rows_groups_or_terms"}
                continue
            fits[threshold, count] = (indices, fit.labels)
            valid = fit.labels >= 0
            prompt_ami = None
            if common_prompts and valid.sum() >= 3 and fit.empty_topics < count - 1:
                prompts = [row.question for row, keep in zip(subset, valid) if keep]
                prompt_ami = round(float(adjusted_mutual_info_score(prompts, fit.labels[valid])), 4)
            groups = sorted({row.group for row in subset})
            omission_scores = []
            degenerate_refits = 0
            for group in groups:
                keep = [i for i, row in enumerate(subset) if row.group != group]
                alternate = _fit([subset[i] for i in keep], count, None if vectors is None else vectors[keep])
                if alternate is not None:
                    degenerate_refits += int(bool(alternate.empty_topics or alternate.zero_input_rows))
                    omission_scores.append(_ari(fit.labels[keep], alternate.labels))
            repetitions = Counter(row.text for row in subset)
            unique = [i for i, row in enumerate(subset) if repetitions[row.text] == 1]
            repeat_sensitivity = None
            if len(unique) < len(subset):
                alternate = _fit([subset[i] for i in unique], count, None if vectors is None else vectors[unique])
                if alternate is not None:
                    repeat_sensitivity = _ari(fit.labels[unique], alternate.labels)
            runs[str(count)] = {
                "status": "ran",
                "sizes": fit.sizes,
                "empty_topics": fit.empty_topics,
                "zero_input_rows": fit.zero_input_rows,
                "solver_warnings": fit.warnings,
                "terms": fit.terms,
                "prompt_ami": prompt_ami,
                "leave_one_workbook_out_ari": _describe(omission_scores),
                "leave_one_workbook_out_attempts": len(groups),
                "leave_one_workbook_out_degenerate_fits": degenerate_refits,
                "projected_repeat_occurrences": sum(n - 1 for n in repetitions.values()),
                "without_projected_repeated_responses_ari": repeat_sensitivity,
            }
        if all((threshold, k) in fits for k in TOPIC_COUNTS):
            runs["topic_count_ari"] = _ari(*(fits[threshold, k][1] for k in TOPIC_COUNTS))
        outcomes[str(threshold)] = runs
    sensitivity = {}
    for k in TOPIC_COUNTS:
        if (30, k) in fits and (15, k) in fits:
            primary, primary_labels = fits[30, k]
            secondary, secondary_labels = fits[15, k]
            secondary_lookup = {index: j for j, index in enumerate(secondary)}
            sensitivity[str(k)] = _ari(primary_labels, secondary_labels[[secondary_lookup[i] for i in primary]])
    return {"subsets": outcomes, "threshold_ari": sensitivity, "seconds": round(perf_counter() - started, 3)}, fits


def _peak_memory_mib():
    if os.name == "nt":
        class Counters(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_uint32), ("page_faults", ctypes.c_uint32),
                ("peak_working_set", ctypes.c_size_t), ("working_set", ctypes.c_size_t),
                ("quota_peak_paged", ctypes.c_size_t), ("quota_paged", ctypes.c_size_t),
                ("quota_peak_nonpaged", ctypes.c_size_t), ("quota_nonpaged", ctypes.c_size_t),
                ("pagefile", ctypes.c_size_t), ("peak_pagefile", ctypes.c_size_t),
            ]
        data = Counters()
        data.cb = ctypes.sizeof(data)
        kernel = ctypes.WinDLL("kernel32")
        kernel.GetCurrentProcess.restype = ctypes.c_void_p
        get_memory = ctypes.WinDLL("psapi").GetProcessMemoryInfo
        get_memory.argtypes = (ctypes.c_void_p, ctypes.POINTER(Counters), ctypes.c_uint32)
        if get_memory(kernel.GetCurrentProcess(), ctypes.byref(data), data.cb):
            return round(data.peak_working_set / 2**20, 1)
        return None
    import resource

    scale = 2**20 if sys.platform == "darwin" else 2**10
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / scale, 1)


def run(inputs, provenance, output, model_dir, source_revision, *, review_record=None, trusted_review_sha256=None):
    from threadpoolctl import threadpool_limits

    if not isinstance(source_revision, str) or not re.fullmatch(r"[0-9a-f]{40}", source_revision):
        raise CorpusError("invalid_source_revision")
    output = _local_external(output)
    started = perf_counter()
    rows, corpus, downloaded = _verified_corpus(
        inputs, provenance, review_record=review_record, trusted_review_sha256=trusted_review_sha256,
    )
    report = {
        "source_revision": source_revision,
        "implementation_sha256": {name: _digest(Path(__file__).with_name(name)) for name in ("corpus.py", "experiment.py", "requirements.txt")},
        "dataset": {"doi": DOI, "version": 1, "license": "CC BY 4.0", "downloaded_utc": downloaded},
        "settings": {"thresholds": THRESHOLDS, "topic_counts": TOPIC_COUNTS, "seed": SEED, "cpu_threads": CPU_THREADS},
        "preprocessing": "screened_responses_v3",
        "environment": {
            "python": platform.python_version(), "platform": platform.system(),
            "packages": {name: version(name) for name in ("numpy", "scipy", "scikit-learn", "joblib", "threadpoolctl", "defusedxml")},
        },
        "corpus": corpus,
        "prepare_seconds": round(perf_counter() - started, 3),
    }
    with threadpool_limits(limits=CPU_THREADS):
        report["classical"], classical_fits = _method(rows, None, corpus["question_sequence_count"] == 1)
        report["classical_peak_working_set_mib"] = _peak_memory_mib()
        report["embedding"] = {"status": "skipped", "reason": "verified_local_model_not_supplied"}
        if model_dir is not None and classical_fits:
            encoded_at = perf_counter()
            try:
                vectors = _local_embeddings([row.text for row in rows], model_dir)
            except (OSError, ValueError, ImportError, RuntimeError):
                report["embedding"] = {"status": "skipped", "reason": "local_model_load_or_inference_failed"}
            else:
                encoded_seconds = round(perf_counter() - encoded_at, 3)
                result, fits = _method(rows, vectors, corpus["question_sequence_count"] == 1)
                report["embedding"] = {
                    **result, "status": "ran", "encode_seconds": encoded_seconds,
                    "model": MODEL, "revision": MODEL_REVISION, "model_sha256": MODEL_SHA256,
                    "license": "Apache-2.0", "max_tokens": MAX_TOKENS, "batch_size": BATCH_SIZE,
                    "pooling": "attention_masked_mean_l2",
                    "cross_method_ari": {
                        f"{threshold}-{count}": _ari(classical_fits[threshold, count][1], labels)
                        for (threshold, count), (_, labels) in fits.items()
                        if (threshold, count) in classical_fits
                    },
                }
                report["environment"]["packages"].update({name: version(name) for name in ("onnxruntime", "tokenizers")})
    report["total_seconds"] = round(perf_counter() - started, 3)
    report["peak_working_set_mib"] = _peak_memory_mib()
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(json.dumps(report, sort_keys=True, allow_nan=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--provenance", type=Path, required=True)
    parser.add_argument("--review-record", type=Path)
    parser.add_argument("--trusted-review-sha256")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path)
    parser.add_argument("--source-revision", required=True)
    args = parser.parse_args()
    try:
        run(
            args.inputs, args.provenance, args.output, args.model_dir, args.source_revision,
            review_record=args.review_record, trusted_review_sha256=args.trusted_review_sha256,
        )
    except CorpusError as error:
        print(f"Research run stopped: {error}", file=sys.stderr)
        return 2
    except Exception:
        print("Research run stopped: private input or local execution error", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
