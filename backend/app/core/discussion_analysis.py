"""Structured aggregates over bounded discussion evidence."""

from collections.abc import Sequence
import re
from typing import TYPE_CHECKING

from app.core.expression_signals import aggregate_expression_signals
from app.core.local_text_analysis import MAX_TEXT_CHARS, MIN_TEXTS, InsufficientVariation, analyze_texts
from app.core.minilm import ModelUnavailable

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

_MARKUP = re.compile(r"```|~~~|<[^>]+>|!?\[[^\]]*\]\(|https?://", re.IGNORECASE)


def group_discussion(texts: list[str], k: int, model_directory):
    try:
        return "comparison", analyze_texts(texts, k, "both", model_directory)
    except ModelUnavailable:
        try:
            return "nmf_only", analyze_texts(texts, k, "nmf")
        except InsufficientVariation:
            return "insufficient_variation", None
    except InsufficientVariation:
        return "insufficient_variation", None


def analyze_discussion(records: "Sequence[Record]", model_directory=None, *, include_sensitivity=False) -> dict:
    rows = []
    texts = []
    seen = set()
    for index, record in enumerate(records):
        # Preserve the unit of one post or reply. Skip ambiguous Markdown and quoted lines.
        if "en" not in record.languages or _MARKUP.search(record.body):
            continue
        text = " ".join(" ".join(line.split()) for line in record.body.splitlines()
                        if line.strip() and not line.lstrip().startswith(">"))
        fingerprint = text.casefold()
        if not text or len(text) > MAX_TEXT_CHARS or fingerprint in seen:
            continue
        seen.add(fingerprint)
        rows.append(index)
        texts.append(text)

    topic_status, topics = (group_discussion(texts, 2, model_directory) if len(texts) >= MIN_TEXTS
                            else ("insufficient_texts", None))
    result = {
        "evidence_rows": rows,
        "topics_status": topic_status,
        "topics": topics,
        "expression_signals": aggregate_expression_signals(texts),
    }
    if include_sensitivity:
        status, groups = (group_discussion(texts, 3, model_directory) if len(texts) >= 24
                          else ("insufficient_texts", None))
        result["sensitivity"] = {"k": 3, "status": status, "topics": groups}
    return result
