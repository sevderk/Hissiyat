"""Clustering and agreement shared by the research and local explorer."""

SEED = 42
NMF_MAX_ITER = 500
KMEANS_MAX_ITER = 300
NEGATIONS = frozenset({
    "cannot", "neither", "never", "no", "nobody", "none", "noone",
    "nor", "not", "nothing", "nowhere", "without",
})


def fit_tfidf(texts, *, max_features=None):
    from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer

    vectorizer = TfidfVectorizer(
        token_pattern=r"(?u)\b[^\W\d_]+(?:'[^\W\d_]+)?\b",
        stop_words=sorted(ENGLISH_STOP_WORDS - NEGATIONS),
        max_features=max_features,
    )
    matrix = vectorizer.fit_transform(texts)
    return matrix, vectorizer.get_feature_names_out()


def fit_nmf(matrix, topic_count):
    import numpy as np
    from sklearn.decomposition import NMF

    model = NMF(n_components=topic_count, init="nndsvda", random_state=SEED, max_iter=NMF_MAX_ITER)
    scores = model.fit_transform(matrix)
    labels = scores.argmax(axis=1)
    labels[np.isclose(scores.sum(axis=1), 0)] = -1
    return labels, model.components_, model.n_iter_


def fit_kmeans(embeddings, topic_count):
    from sklearn.cluster import KMeans

    model = KMeans(
        n_clusters=topic_count, random_state=SEED, n_init=20,
        init="k-means++", max_iter=KMEANS_MAX_ITER, tol=1e-4, algorithm="lloyd",
    )
    labels = model.fit_predict(embeddings)
    return labels, model.n_iter_


def grouping_agreement(left, right):
    from sklearn.metrics import adjusted_rand_score

    valid = (left >= 0) & (right >= 0)
    common = int(valid.sum())
    ari = None
    if common >= 3 and len(set(left[valid])) >= 2 and len(set(right[valid])) >= 2:
        ari = round(float(adjusted_rand_score(left[valid], right[valid])), 4)
    return {"ari": ari, "common_assigned": common}
