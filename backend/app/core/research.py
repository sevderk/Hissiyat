"""One-page topic and event searches with ephemeral provider records."""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
import json
import re
from time import monotonic
from typing import Literal
from unicodedata import category, normalize
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

MAX_BODY_BYTES = 4096
MAX_POSTS = 25
MAX_RESPONSE_BYTES = 512 * 1024
SEARCH_ENDPOINT = "https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts"
LEMMY_ORIGIN = "https://lemmy.world"
LEMMY_SEARCH_ENDPOINT = f"{LEMMY_ORIGIN}/api/v3/search"
LIVE_SOURCES = ("bluesky", "lemmy", "wikimedia")
APPROVAL_SOURCES = (*LIVE_SOURCES, "civil_comments")
ANALYSIS_SOURCES = ("fictional", "wikimedia", "civil_comments")
CIVIL_FIRST = date(2015, 1, 1)
CIVIL_LAST = date(2017, 12, 31)
CIVIL_SAMPLE_SIZE = 100
WIKI_TITLE = "Talk:USB flash drive"
WIKI_PAGE = "https://en.wikipedia.org/wiki/Talk:USB_flash_drive"
WIKI_HISTORY = "https://en.wikipedia.org/w/index.php?title=Talk:USB_flash_drive&action=history"
WIKI_LICENSE = "https://creativecommons.org/licenses/by-sa/4.0/"
BLUESKY_RESTRICTED_LABELS = frozenset({"!hide", "!warn", "!no-unauthenticated", "porn", "sexual", "nudity", "graphic-media"})
POST_URI = re.compile(
    r"at://(did:(?:plc:[a-z2-7]{24}|web:[A-Za-z0-9._:%-]{1,200}))/app\.bsky\.feed\.post/([A-Za-z0-9._~:-]{1,128})"
)
LANGUAGE = re.compile(r"[a-zA-Z]{2,8}(?:-[a-zA-Z0-9]{1,8}){0,4}")
TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)")
CAPABILITIES = {
    "fictional": {"status": "synthetic", "languages": ["en", "tr"], "geography": False, "max_items": MAX_POSTS},
    "bluesky": {"status": "public_api", "languages": ["en", "tr"], "geography": False, "max_items": MAX_POSTS},
    "lemmy": {"status": "public_api", "languages": [], "geography": False, "max_items": MAX_POSTS},
    "wikimedia": {"status": "public_api", "languages": [], "geography": False, "max_items": MAX_POSTS},
    "civil_comments": {"status": "historical", "languages": ["en"], "geography": False, "max_items": CIVIL_SAMPLE_SIZE},
    "google_trends": {"status": "unavailable", "languages": [], "geography": False, "max_items": None},
}


def civil_query_phrases(query: str) -> tuple[str, ...]:
    phrases = tuple(part.strip() for part in query.split("|"))
    if len(phrases) > 8 or len(set(phrase.casefold() for phrase in phrases)) != len(phrases):
        raise ValueError("Use up to eight distinct alternatives.")
    if len(phrases) > 1 and any(
        not 2 <= len(phrase.split()) <= 6
        or not all(re.fullmatch(r"[a-zA-Z]+(?:[-'’][a-zA-Z]+)*", word) for word in phrase.split())
        for phrase in phrases
    ):
        raise ValueError("Use two to six English words in each alternative.")
    return phrases


class ResearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True, frozen=True)

    mode: Literal["topic", "event"]
    query: str
    start_date: date
    end_date: date
    source: Literal["fictional", "bluesky", "lemmy", "wikimedia", "civil_comments", "google_trends"]
    language: Literal["en", "tr"] | None = None
    geography: str | None = None
    content: Literal["posts", "comments", "mixed"] | None = None
    analyze_discussion: bool = False

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        value = normalize("NFC", value)
        if any(category(char).startswith("C") for char in value):
            raise ValueError("Unsupported search characters.")
        value = " ".join(value.split())
        if not 2 <= len(value) <= 120 or not any(char.isalnum() for char in value):
            raise ValueError("Invalid search query.")
        return value

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def require_iso_date(cls, value: object) -> date:
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError("Expected an ISO calendar date.")
        return date.fromisoformat(value)

    @model_validator(mode="after")
    def validate_scope(self):
        if not date(2000, 1, 1) <= self.start_date <= self.end_date <= datetime.now(UTC).date():
            raise ValueError("Invalid date range.")
        if self.source not in ("wikimedia", "civil_comments") and (self.end_date - self.start_date).days >= 31:
            raise ValueError("Date range exceeds 31 days.")
        capabilities = CAPABILITIES[self.source]
        if self.geography is not None and not capabilities["geography"]:
            raise ValueError("Geographic filtering is unsupported.")
        if self.language is not None and self.language not in capabilities["languages"]:
            raise ValueError("Language filtering is unsupported.")
        if self.source == "lemmy" and any(
            not (char.isalnum() or category(char).startswith("M") or char in " -'’") for char in self.query
        ):
            # Lemmy search may resolve object IDs. This adapter accepts textual searches only.
            raise ValueError("Use words for Lemmy searches.")
        if self.source == "wikimedia":
            if self.query != WIKI_TITLE or self.mode != "topic" or self.content != "comments":
                raise ValueError("Unsupported Wikimedia pilot scope.")
        elif self.source == "civil_comments":
            if not (CIVIL_FIRST <= self.start_date <= self.end_date <= CIVIL_LAST and self.content == "comments"
                    and self.language == "en" and self.analyze_discussion):
                raise ValueError("Unsupported historical pilot scope.")
            civil_query_phrases(self.query)
        elif self.content is not None and (self.source not in ("fictional", "lemmy")
                                           or (self.source == "lemmy" and self.content == "mixed")):
            raise ValueError("Unsupported content selection.")
        return self


class ResearchError(Exception):
    def __init__(self, code: str, status: int, upstream_status: int | None = None):
        super().__init__(code)
        self.code = code
        self.status = status
        self.upstream_status = upstream_status


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@dataclass(frozen=True)
class Record:
    source: Literal["fictional", "bluesky", "lemmy", "wikimedia", "civil_comments"]
    reference: str | None
    published_at: datetime
    body: str = field(repr=False)
    languages: tuple[str, ...]
    country: Literal["UNKNOWN"] = "UNKNOWN"
    geography_attribution: Literal["unknown"] = "unknown"
    source_language_id: int | None = None
    kind: Literal["post", "comment"] = "post"
    thread_reference: str | None = None
    article_id: str | None = None
    publication_id: str | None = None

    def for_display(self) -> dict:
        result = {
            "source": self.source, "reference": self.reference,
            "published_at": self.published_at.isoformat(), "languages": self.languages,
            "country": self.country, "geography_attribution": self.geography_attribution,
        }
        if self.source == "fictional":
            result["text"] = self.body
        elif self.source == "lemmy":
            result["source_language_id"] = self.source_language_id
        elif self.source == "civil_comments":
            result.update(article_id=self.article_id, publication_id=self.publication_id)
        if self.kind == "comment":
            result.update(kind=self.kind, thread_reference=self.thread_reference)
        return result


def bounds(scope: ResearchRequest) -> tuple[datetime, datetime]:
    return (
        datetime.combine(scope.start_date, time.min, UTC),
        datetime.combine(scope.end_date + timedelta(days=1), time.min, UTC),
    )


def fetch_bluesky(scope: ResearchRequest) -> list:
    start, end = bounds(scope)
    params = {"q": scope.query, "sort": "latest", "limit": MAX_POSTS,
              "since": start.date().isoformat(), "until": end.date().isoformat()}
    if scope.language is not None:
        params["lang"] = scope.language
    return fetch_posts(SEARCH_ENDPOINT, params)


def fetch_lemmy(scope: ResearchRequest) -> list:
    search_type = "Comments" if scope.content == "comments" else "Posts"
    return fetch_posts(LEMMY_SEARCH_ENDPOINT, {
        "q": scope.query, "type_": search_type, "listing_type": "Local", "sort": "New", "limit": MAX_POSTS,
    }, expected_type=search_type, collection_key=search_type.lower())


def upstream_error(status: int) -> ResearchError:
    if status == 401:
        return ResearchError("provider_auth_required", 502, status)
    if status == 403:
        return ResearchError("provider_denied", 502, status)
    if status == 429:
        return ResearchError("rate_limited", 429, status)
    return ResearchError("provider_unavailable", 502, status if 100 <= status <= 599 else None)


def fetch_posts(endpoint: str, params: dict[str, str | int], *, expected_type: str | None = None,
                collection_key: str = "posts") -> list:
    payload = fetch_json(endpoint, params)
    records = payload.get(collection_key) if isinstance(payload, dict) else None
    if (not isinstance(records, list) or len(records) > MAX_POSTS
            or (expected_type is not None and payload.get("type_") != expected_type)):
        raise ResearchError("invalid_response", 502, 200)
    return records


def fetch_json(endpoint: str, params: dict[str, str | int], *,
               user_agent: str = "Hissiyat/0.1 (local research preview)") -> object:
    request = Request(f"{endpoint}?{urlencode(params)}", headers={
        "Accept": "application/json", "User-Agent": user_agent,
    })
    opener = build_opener(ProxyHandler({}), NoRedirect())
    deadline = monotonic() + 8
    body = bytearray()
    upstream_status = None
    try:
        with opener.open(request, timeout=8) as response:
            upstream_status = response.status
            if upstream_status != 200:
                raise upstream_error(upstream_status)
            while True:
                if monotonic() >= deadline:
                    raise TimeoutError
                chunk = response.read1(65536)
                if not chunk:
                    break
                if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                    raise ResearchError("invalid_response", 502, upstream_status)
                body.extend(chunk)
    except HTTPError as exc:
        with exc:
            raise upstream_error(exc.code) from None
    except TimeoutError:
        raise ResearchError("provider_timeout", 504, upstream_status) from None
    except URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            raise ResearchError("provider_timeout", 504) from None
        raise ResearchError("provider_unavailable", 502) from None
    except OSError:
        raise ResearchError("provider_unavailable", 502, upstream_status) from None

    try:
        return json.loads(body)
    except (ValueError, RecursionError):
        raise ResearchError("invalid_response", 502, upstream_status) from None


def publication_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not TIMESTAMP.fullmatch(value):
        return None
    try:
        return datetime.fromisoformat(value).astimezone(UTC)
    except (ValueError, OverflowError):
        return None


def bluesky_is_restricted(post: object) -> bool:
    if not isinstance(post, dict):
        return False
    record = post.get("record")
    self_labels = record.get("labels") if isinstance(record, dict) else None
    self_values = self_labels.get("values") if isinstance(self_labels, dict) else None
    author = post.get("author")
    author_labels = author.get("labels") if isinstance(author, dict) else None
    return any(
        isinstance(label, dict) and isinstance(label.get("val"), str)
        and label["val"] in BLUESKY_RESTRICTED_LABELS and label.get("neg") is not True
        for labels in (post.get("labels"), author_labels, self_values) if isinstance(labels, list)
        for label in labels
    )


def normalize_post(post: object) -> Record | None:
    if not isinstance(post, dict) or not isinstance(record := post.get("record"), dict):
        return None
    uri = post.get("uri")
    timestamp = publication_time(record.get("createdAt"))
    text = record.get("text")
    if (record.get("$type") != "app.bsky.feed.post"
            or not isinstance(uri, str) or not (match := POST_URI.fullmatch(uri))
            or timestamp is None
            or not isinstance(text, str) or len(text) > 3000):
        return None
    languages = record.get("langs")
    tags = () if not isinstance(languages, list) else tuple(dict.fromkeys(
        tag.lower() for tag in languages[:3] if isinstance(tag, str) and LANGUAGE.fullmatch(tag)
    ))
    did, key = match.groups()
    if key in (".", "..") or re.search(r"%(?![0-9A-Fa-f]{2})", did):
        return None
    # Quote the opaque path components separately. A local URL can never be supplied by the provider.
    return Record("bluesky", f"https://bsky.app/profile/{quote(did, safe=':')}/post/{quote(key, safe=':~')}",
                  timestamp, text, tags)


def normalize_lemmy_post(view: object, *, comment: bool = False) -> tuple[Record | None, bool]:
    if not isinstance(view, dict):
        return None, False
    post, community = view.get("post"), view.get("community")
    if not isinstance(post, dict) or not isinstance(community, dict):
        return None, False
    # A missing safety or visibility flag cannot establish eligibility.
    if (any(post.get(flag) is not False for flag in ("nsfw", "removed", "deleted"))
            or any(community.get(flag) is not False for flag in ("nsfw", "removed", "deleted", "hidden"))
            or post.get("local") is not True or community.get("local") is not True
            or community.get("visibility") != "Public"):
        return None, True

    post_id = post.get("id")
    if type(post_id) is not int or not 0 < post_id <= 2_147_483_647:
        return None, False
    thread = f"{LEMMY_ORIGIN}/post/{post_id}"
    if post.get("ap_id") != thread:
        return None, False
    if comment:
        item = view.get("comment")
        if not isinstance(item, dict):
            return None, False
        if (any(item.get(flag) is not False for flag in ("removed", "deleted"))
                or item.get("local") is not True or ("nsfw" in item and item["nsfw"] is not False)):
            return None, True
        comment_id = item.get("id")
        if (type(comment_id) is not int or not 0 < comment_id <= 2_147_483_647
                or type(item.get("post_id")) is not int or item["post_id"] != post_id):
            return None, False
        reference = f"{LEMMY_ORIGIN}/comment/{comment_id}"
        text = item.get("content")
        if item.get("ap_id") != reference or not isinstance(text, str) or not text.strip() or len(text) > 20_000:
            return None, False
    else:
        item = post
        reference = thread
        title, body = post.get("name"), post.get("body")
        if (not isinstance(title, str) or not title.strip() or len(title) > 300
                or (body is not None and (not isinstance(body, str) or len(body) > 20_000))):
            return None, False
        text = f"{title}\n\n{body}" if body else title
    publication = publication_time(item.get("published"))
    if publication is None:
        return None, False
    language_id = item.get("language_id")
    if type(language_id) is not int or not 0 < language_id <= 2_147_483_647:
        language_id = None
    return Record("lemmy", reference, publication, text, (), source_language_id=language_id,
                  kind="comment" if comment else "post", thread_reference=thread), False


FICTIONAL_POSTS = (
    (6, "en", "Bike lanes near the station made my morning ride less stressful."),
    (9, "en", "The new bike lanes still end before the busiest junction."),
    (11, "en", "I joined the bike lanes planning meeting to ask for safer crossings."),
    (7, "tr", "Bisiklet yolları istasyon çevresinde yolculuğumu kolaylaştırdı."),
    (12, "tr", "Mahalledeki bisiklet yolları kavşakta kesiliyor."),
    (10, "en", "The river festival moved its afternoon concert indoors after the rain forecast."),
    (11, "en", "I found the river festival entrance easier to reach by shuttle."),
    (10, "tr", "Nehir festivali bu yıl öğleden sonraki konseri kapalı alana aldı."),
    (13, "tr", "Nehir festivali çıkışında servis saatlerini bulmakta zorlandım."),
)


def run_research(scope: ResearchRequest, *, model_directory=None) -> dict:
    if scope.analyze_discussion and scope.source not in ANALYSIS_SOURCES:
        raise ResearchError("analysis_permission_unverified", 403)
    start, end = bounds(scope)
    received = outside = invalid = duplicate = excluded = 0
    records = []
    source_document = None
    dataset_document = None
    if scope.source == "civil_comments":
        from app.core.civil_comments import fetch_sample

        records, metrics, dataset_document = fetch_sample(scope)
        received, outside, invalid, duplicate, excluded = metrics
    elif scope.source == "wikimedia":
        from app.core.wikimedia_discussion import fetch_discussion

        records, metrics = fetch_discussion(scope)
        received, outside, invalid, duplicate, excluded = metrics
        source_document = {"page": WIKI_PAGE, "history": WIKI_HISTORY, "license": "CC BY-SA 4.0",
                           "license_url": WIKI_LICENSE, "retrieved_at": datetime.now(UTC).isoformat()}
    elif scope.source in LIVE_SOURCES:
        posts = fetch_lemmy(scope) if scope.source == "lemmy" else fetch_bluesky(scope)
        received = len(posts)
        seen = set()
        for post in posts:
            if scope.source == "lemmy":
                record, restricted = normalize_lemmy_post(post, comment=scope.content == "comments")
            else:
                restricted = bluesky_is_restricted(post)
                record = None if restricted else normalize_post(post)
            if restricted:
                excluded += 1
            elif record is None:
                invalid += 1
            elif not start <= record.published_at < end:
                outside += 1
            elif record.reference in seen:
                duplicate += 1
            else:
                seen.add(record.reference)
                records.append(record)
    elif scope.source == "fictional":
        from app.core.discussion_analysis import FICTIONAL_DISCUSSION

        for day, language, text, kind in (*((day, language, text, "post") for day, language, text in FICTIONAL_POSTS),
                                         *FICTIONAL_DISCUSSION):
            timestamp = datetime(2026, 11, day, 12, tzinfo=UTC)
            if (start <= timestamp < end and scope.language in (None, language)
                    and scope.query.casefold() in text.casefold()
                    and scope.content in (None, "mixed", f"{kind}s")):
                records.append(Record("fictional", None, timestamp, text, (language,), kind=kind))
        received = len(records)
    else:
        raise ResearchError("source_unavailable", 422)
    records.sort(key=lambda record: record.published_at)
    scope_data = scope.model_dump(mode="json")
    if scope.content is None:
        scope_data.pop("content")
    if not scope.analyze_discussion:
        scope_data.pop("analyze_discussion")
    result = {
        "scope": scope_data, "capabilities": CAPABILITIES[scope.source],
        "retrieved": received, "outside_dates": outside, "invalid_records": invalid, "duplicates": duplicate,
        "excluded_records": excluded,
        "records": [record.for_display() for record in records],
    }
    if source_document is not None:
        result["source_document"] = source_document
    if dataset_document is not None:
        result["dataset_document"] = dataset_document
    if scope.analyze_discussion:
        from app.core.discussion_analysis import analyze_discussion

        result["discussion_analysis"] = analyze_discussion(records, model_directory)
    return result
