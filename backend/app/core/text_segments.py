"""Bounded document-preserving segmentation with original character offsets."""

import re

MAX_DOCUMENT_CHARS = 8_000
MAX_COLLECTION_CHARS = 100_000
MAX_SEGMENT_CHARS = 400
MAX_SEGMENTS = 1_200
MAX_DOCUMENT_SEGMENTS = 128
_SENTENCE = re.compile(r"[^.!?\n]+(?:[.!?]+|$)|[\n]+", re.MULTILINE)


def segment_document(text: str) -> list[tuple[int, int]]:
    if not text or len(text) > MAX_DOCUMENT_CHARS:
        raise ValueError("document_limit")
    segments = []
    start = 0
    while start < len(text):
        end = min(start + MAX_SEGMENT_CHARS, len(text))
        if end < len(text):
            candidates = [match.end() for match in _SENTENCE.finditer(text, start, end)
                          if match.end() < end and (text[match.end() - 1] in ".!?\n")]
            boundary = candidates[-1] if candidates else text.rfind(" ", start + 1, end)
            if boundary <= start:
                raise ValueError("unsegmentable_document")
            end = boundary
        segments.append((start, end))
        if len(segments) > MAX_DOCUMENT_SEGMENTS:
            raise ValueError("segment_limit")
        start = end
    return segments


def segment_collection(texts: list[str]) -> list[list[tuple[int, int]]]:
    if len(texts) > 100 or sum(map(len, texts)) > MAX_COLLECTION_CHARS:
        raise ValueError("collection_limit")
    documents = [segment_document(text) for text in texts]
    if sum(map(len, documents)) > MAX_SEGMENTS:
        raise ValueError("segment_limit")
    return documents
