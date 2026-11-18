"""One licensed Talk-page snapshot via the Wikimedia DiscussionTools Action API."""

from collections import Counter
from datetime import UTC, datetime
from html.parser import HTMLParser
import re

from app.core.research import (
    MAX_POSTS, WIKI_PAGE, WIKI_TITLE, Record, ResearchError, ResearchRequest, bounds, fetch_json, publication_time,
)
from app.core.text_segments import MAX_DOCUMENT_CHARS

ENDPOINT = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "HissiyatResearch/0.1 (https://github.com/sevderk/Hissiyat)"
PARAMETERS = {"action": "discussiontoolspageinfo", "page": WIKI_TITLE, "format": "json", "formatversion": "2",
              "prop": "threaditemshtml|transcludedfrom", "threaditemsflags": "excludesignatures", "maxlag": "5"}
MAX_THREAD_ITEMS = 2000
PLAIN_TAGS = frozenset({"b", "br", "code", "div", "em", "i", "p", "span", "strong", "s", "sub", "sup", "u"})
PERSONAL_OR_IMPORTED = re.compile(
    r"@|https?://|\bwww\.|\b(?:user(?: talk)?|special):|\(UTC\)|\b(?:phone|e-?mail|address|password):|"
    r"\b(?:\d{1,3}\.){3}\d{1,3}\b|(?:\d[\s()+.-]*){7,}|"
    r"\b(?:quoted? (?:from|by)|copied from|according to|full name|home address|my phone|contact me)\b|[\"“”]",
    re.IGNORECASE,
)
ENGLISH_MARKERS = frozenset("the a an and is are was were that this with from for of have it they you to but would".split())


class PlainComment(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.open_tags: list[str] = []
        self.ambiguous = False

    def handle_starttag(self, tag, attrs):
        # Accept simple formatting only. Links, quotes, signatures, templates, and embedded media are excluded.
        if tag not in PLAIN_TAGS or any(name not in ("id", "class", "data-parsoid", "dir") for name, _ in attrs):
            self.ambiguous = True
        if tag in ("br", "p", "div"):
            self.parts.append(" ")
        if tag != "br":
            self.open_tags.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag != "br":
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if not self.open_tags or self.open_tags.pop() != tag:
            self.ambiguous = True
        if tag in ("p", "div"):
            self.parts.append(" ")

    def handle_data(self, data):
        self.parts.append(data)

    def handle_comment(self, data):
        self.ambiguous = True


def plain_english(body: object) -> str | None:
    if not isinstance(body, str) or not 0 < len(body) <= 4000:
        return None
    parser = PlainComment()
    parser.feed(body)
    parser.close()
    text = " ".join("".join(parser.parts).split())
    words = set(re.findall(r"\b[a-z]+\b", text.lower()))
    letters = [char for char in text if char.isalpha()]
    if (parser.ambiguous or parser.open_tags or not 0 < len(text) <= MAX_DOCUMENT_CHARS or len(words & ENGLISH_MARKERS) < 3
            or sum(char.isascii() for char in letters) < .9 * len(letters)
            or "<" in text or ">" in text or PERSONAL_OR_IMPORTED.search(text)):
        return None
    return text


def comment_items(threads: list) -> list[dict]:
    pending = [(item, True) for item in reversed(threads)]
    comments = []
    visited = 0
    while pending:
        item, heading_context = pending.pop()
        visited += 1
        if visited + len(pending) > MAX_THREAD_ITEMS:
            raise ResearchError("invalid_response", 502, 200)
        if not isinstance(item, dict) or not isinstance(replies := item.get("replies"), list):
            raise ResearchError("invalid_response", 502, 200)
        if item.get("type") == "comment" and not heading_context:
            comments.append(item)
        elif item.get("type") != "heading" or not heading_context:
            raise ResearchError("invalid_response", 502, 200)
        pending.extend((reply, False) for reply in reversed(replies))
    return comments


def parse_discussion(payload: object, scope: ResearchRequest) -> tuple[list[Record], tuple[int, int, int, int, int]]:
    if not isinstance(payload, dict) or "continue" in payload or "warnings" in payload:
        raise ResearchError("invalid_response", 502, 200)
    if isinstance(error := payload.get("error"), dict):
        if error.get("code") in ("nosuchrevid", "missingcontent", "missingtitle"):
            raise ResearchError("discussion_missing", 422, 200)
        raise ResearchError("provider_unavailable", 502, 200)
    module = payload.get("discussiontoolspageinfo")
    if not isinstance(module, dict) or not isinstance(threads := module.get("threaditemshtml"), list):
        raise ResearchError("invalid_response", 502, 200)
    locations = module.get("transcludedfrom")
    if not isinstance(locations, dict) and not (locations == [] and not threads):
        raise ResearchError("invalid_response", 502, 200)

    items = comment_items(threads)
    if not items:
        return [], (0, 0, 0, 0, 0)
    start, end = bounds(scope)
    dated = [(item, publication_time(item.get("timestamp"))) for item in items]
    ids = Counter(item["id"] for item in items if isinstance(item.get("id"), str))
    in_window = [(item, stamp) for item, stamp in dated if stamp is not None and start <= stamp < end]
    in_window.sort(key=lambda pair: pair[1], reverse=True)
    # Prioritize dated items in scope, then use any spare budget to account for unclassifiable or outside-date records.
    remainder = [(item, stamp) for item, stamp in dated if stamp is None or not start <= stamp < end]
    sampled = (in_window + remainder)[:MAX_POSTS]
    records = []
    outside = invalid = duplicate = excluded = 0
    seen_text = set()
    for item, stamp in sampled:
        identifier = item.get("id")
        author = item.get("author")
        if stamp is None or not isinstance(identifier, str) or not identifier.startswith("c-") or len(identifier) > 512:
            invalid += 1
        elif not start <= stamp < end:
            outside += 1
        elif ids[identifier] > 1:
            duplicate += 1
        elif (locations.get(identifier) is not False or item.get("warnings") or not (text := plain_english(item.get("html")))
              or not isinstance(author, str) or not author.strip()
              or re.search(r"(?<!\w)" + re.escape(author.replace("_", " ").strip()) + r"(?!\w)", text, re.IGNORECASE)):
            excluded += 1
        elif text.casefold() in seen_text:
            duplicate += 1
        else:
            seen_text.add(text.casefold())
            # DiscussionTools IDs can embed contributor names. Keep them request-local and attribute at page level.
            records.append(Record("wikimedia", WIKI_PAGE, stamp, text, ("en",), kind="comment"))
    return records, (len(sampled), outside, invalid, duplicate, excluded)


def fetch_discussion(scope: ResearchRequest) -> tuple[list[Record], tuple[int, int, int, int, int]]:
    payload = fetch_json(ENDPOINT, PARAMETERS, user_agent=USER_AGENT)
    return parse_discussion(payload, scope)
