"""Structured aggregates over bounded discussion evidence."""

from collections.abc import Sequence
import re
from typing import TYPE_CHECKING

from app.core.expression_evidence import evidence_signals, expression_evidence
from app.core.local_text_analysis import MAX_TEXT_CHARS, MIN_TEXTS, InsufficientVariation, analyze_texts
from app.core.minilm import ModelUnavailable
from app.core.text_segments import MAX_COLLECTION_CHARS, MAX_SEGMENTS, segment_document

if TYPE_CHECKING:
    from app.core.research import Record


FICTIONAL_DISCUSSION = (
    (6, "en", "I used the community services library website to reserve a study room. I feel confident using the booking form.", "post"),
    (6, "en", "I need information about the community services transport schedule. The bus stops by the library.", "post"),
    (7, "en", "I am frustrated with the community services library website. I submitted the booking form twice.", "comment"),
    (7, "en", "I tried the community services transport route. I waited beside the station for half an hour.", "comment"),
    (8, "en", "I need guidance on the community services library tutorials. I opened the website to look for study resources.", "post"),
    (8, "en", "I am worried about the community services transport changes. I need information about the evening schedule.", "comment"),
    (9, "en", "I attended the community services workshop at the library. The website had a list of training resources.", "comment"),
    (9, "en", "I used the community services transport service to reach the market. I felt excited to see the new route.", "post"),
    (10, "en", "I completed the community services library training. I need help with printing from the website.", "comment"),
    (10, "en", "I need advice about the community services transport timetable. I missed the night bus after work.", "comment"),
    (11, "en", "I am curious about the new community services library workshops. The website includes training for beginners.", "post"),
    (11, "en", "I contacted the community services transport team about the schedule. I received a map of the new routes.", "comment"),
    (12, "en", "I used the community services library study space. I feel confident about presenting my project there.", "comment"),
    (12, "en", "I am frustrated about the community services transport service. Could anyone help me read the weekend schedule?", "post"),
    (13, "en", "I need more details about community services library access. I opened the website to check the rules.", "comment"),
    (13, "en", "I attended the community services transport meeting. I need support with the accessible route to the station.", "comment"),
)
FICTIONAL_LONG_DISCUSSION = tuple(
    (day, language, text.replace("community services", "public service research")
     + "\n\n" + "The fictional report describes the service, its opening hours and the full context of the visit. " * 8
     + "\nI cannot access the booking form. I chose this service because the library was accessible.",
     kind)
    for day, language, text, kind in FICTIONAL_DISCUSSION
)

_MARKUP = re.compile(r"```|~~~|<[^>]+>|!?\[[^\]]*\]\(|https?://", re.IGNORECASE)


def group_discussion(texts: list[str], k: int, model_directory):
    try:
        return "comparison", analyze_texts(texts, k, "both", model_directory, diagnostics=True)
    except ModelUnavailable:
        try:
            return "nmf_only", analyze_texts(texts, k, "nmf", diagnostics=True)
        except InsufficientVariation:
            return "insufficient_variation", None
    except InsufficientVariation:
        return "insufficient_variation", None


def analyze_discussion(records: "Sequence[Record]", model_directory=None, *, include_sensitivity=False) -> dict:
    rows = []
    texts = []
    seen = set()
    characters = segments = 0
    excluded = dict.fromkeys(("language_or_markup", "document_limit", "duplicate", "collection_limit", "segment_limit"), 0)
    for index, record in enumerate(records):
        # Preserve the unit of one post or reply. Skip ambiguous markup.
        if "en" not in record.languages or _MARKUP.search(record.body):
            excluded["language_or_markup"] += 1
            continue
        # Original text remains the evidence coordinate system, including quoted paragraphs.
        text = record.body
        fingerprint = " ".join(text.casefold().split())
        if not text.strip() or len(text) > MAX_TEXT_CHARS:
            excluded["document_limit"] += 1
            continue
        if fingerprint in seen:
            excluded["duplicate"] += 1
            continue
        if characters + len(text) > MAX_COLLECTION_CHARS or len(texts) >= 100:
            excluded["collection_limit"] += 1
            continue
        try:
            parts = segment_document(text)
        except ValueError:
            excluded["segment_limit"] += 1
            continue
        if segments + len(parts) > MAX_SEGMENTS:
            excluded["segment_limit"] += 1
            continue
        seen.add(fingerprint)
        rows.append(index)
        texts.append(text)
        characters += len(text)
        segments += len(parts)

    topic_status, topics = (group_discussion(texts, 2, model_directory) if len(texts) >= MIN_TEXTS
                            else ("insufficient_texts", None))
    expressions = expression_evidence(texts, rows, disclose_text=all(record.source == "fictional" for record in records))
    result = {
        "evidence_rows": rows,
        "topics_status": topic_status,
        "topics": topics,
        "expression_signals": evidence_signals(expressions),
        "expression_evidence": expressions,
        "processing": {"documents": len(texts), "segments": segments, "characters": characters, "excluded": excluded},
    }
    if include_sensitivity:
        status, groups = (group_discussion(texts, 3, model_directory) if len(texts) >= 24
                          else ("insufficient_texts", None))
        result["sensitivity"] = {"k": 3, "status": status, "topics": groups}
    return result
