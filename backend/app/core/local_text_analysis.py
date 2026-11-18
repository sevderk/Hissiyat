"""Bounded in-memory exploratory topic discovery for the local UI."""

import warnings
from functools import lru_cache

from app.core.minilm import CPU_THREADS, MiniLMEncoder
from app.core.topic_model import KMEANS_MAX_ITER, NMF_MAX_ITER, fit_kmeans, fit_nmf, fit_tfidf, grouping_agreement
from app.core.text_segments import MAX_DOCUMENT_CHARS, segment_collection

MIN_TEXTS = 12
MAX_TEXTS = 100
MAX_TEXT_CHARS = MAX_DOCUMENT_CHARS
MAX_BODY_BYTES = 262_144
MAX_FEATURES = 4_000

# Disclosure vocabulary only. The fit uses the full bounded TF-IDF vocabulary.
DISPLAY_TERMS = frozenset(
    "access accessibility advice application appointments benefits budget career change classes "
    "communication community cost courses design documents education email equipment "
    "expectations feedback forms guidance health help information instructions interview jobs "
    "learning lessons library login navigation notifications opportunities packaging payment "
    "practice privacy process project projects refund repair resources schedule school search "
    "service settings skills software study suggestions support team training transport "
    "tutorial tutorials updates usability website work workshop".split()
)


class InsufficientVariation(ValueError):
    pass


def _distinct_indices(matrix):
    import numpy as np

    matrix.sort_indices()
    # Duplicate weighted rows count once for variation and term disclosure.
    distinct_rows = {}
    for index in range(matrix.shape[0]):
        start, end = matrix.indptr[index:index + 2]
        if start < end:
            signature = (matrix.indices[start:end].tobytes(), matrix.data[start:end].tobytes())
            distinct_rows.setdefault(signature, index)
    return np.array(list(distinct_rows.values()), dtype=np.intp)


def _groups(labels, k, lexical, distinct, nmf_weights=None):
    import numpy as np

    groups = []
    for topic in range(k):
        assigned = labels == topic
        keywords = []
        if lexical is not None:
            matrix, vocabulary = lexical
            support = np.asarray((matrix[distinct[assigned[distinct]]] > 0).sum(axis=0)).ravel()
            weights = (nmf_weights[topic] if nmf_weights is not None
                       else np.asarray(matrix[assigned].sum(axis=0)).ravel())
            keywords = [
                str(vocabulary[index]) for index in np.argsort(-weights, kind="stable")
                if weights[index] > 0 and support[index] >= 3 and vocabulary[index] in DISPLAY_TERMS
            ][:4]
        groups.append({"size": int(assigned.sum()), "keywords": keywords})
    return groups


@lru_cache(maxsize=1)
def _encoder(directory):
    # Only verified model assets are retained. Submitted texts and vectors are request-local.
    return MiniLMEncoder(directory)


def _document_vectors(texts, directory):
    import numpy as np

    encoder = _encoder(directory)
    spans = segment_collection(texts)
    pieces = [text[start:end] for text, segments in zip(texts, spans, strict=True) for start, end in segments]
    encoded = encoder.encode(pieces, reject_truncation=True)
    vectors = []
    offset = 0
    for text, segments in zip(texts, spans, strict=True):
        weights = np.array([end - start for start, end in segments], dtype=np.float32)
        vector = np.average(encoded[offset:offset + len(segments)], weights=weights, axis=0)
        vectors.append(vector / max(float(np.linalg.norm(vector)), 1e-12))
        offset += len(segments)
    return np.asarray(vectors, dtype=np.float32)


def _separation(matrix, assigned):
    from sklearn.metrics import silhouette_score

    valid = assigned >= 0
    labels = assigned[valid]
    if not 2 <= len(set(labels)) < len(labels):
        return None
    try:
        return round(float(silhouette_score(matrix[valid], labels, metric="cosine")), 4)
    except ValueError:
        return None


def analyze_texts(texts: list[str], k: int, method="nmf", model_directory=None, *, diagnostics=False) -> dict:
    from threadpoolctl import threadpool_limits

    lexical = None
    distinct = None
    labels = {}
    results = {}
    separation = {}
    try:
        segment_collection(texts)
    except ValueError:
        raise InsufficientVariation from None
    with threadpool_limits(limits=CPU_THREADS), warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        try:
            lexical = fit_tfidf(texts, max_features=MAX_FEATURES)
        except ValueError:
            if method != "minilm":
                raise InsufficientVariation from None
        if lexical is not None:
            distinct = _distinct_indices(lexical[0])
        if method in ("nmf", "both"):
            if min(lexical[0].shape) < k or len(distinct) < k:
                raise InsufficientVariation
            assigned, weights, iterations = fit_nmf(lexical[0], k)
            labels["nmf"] = assigned
            results["nmf"] = {
                "groups": _groups(assigned, k, lexical, distinct, weights),
                "unassigned": int((assigned == -1).sum()),
                "iteration_limit": iterations >= NMF_MAX_ITER,
            }
            if diagnostics:
                separation["nmf"] = _separation(lexical[0], assigned)
        if method in ("minilm", "both"):
            if len({text.casefold() for text in texts}) < k:
                raise InsufficientVariation
            vectors = _document_vectors(texts, model_directory)
            assigned, iterations = fit_kmeans(vectors, k)
            if len(set(assigned)) < k:
                raise InsufficientVariation
            labels["minilm"] = assigned
            results["minilm"] = {
                "groups": _groups(assigned, k, lexical, distinct),
                "unassigned": 0,
                "iteration_limit": iterations >= KMEANS_MAX_ITER,
            }
            if diagnostics:
                separation["minilm"] = _separation(vectors, assigned)
        agreement = grouping_agreement(labels["nmf"], labels["minilm"]) if method == "both" else None
        result = {"methods": results, "agreement": agreement}
        if diagnostics:
            result["separation"] = separation
        return result
