"""Bounded, in-memory pilot from one pinned Civil Comments distribution."""

from collections import Counter
from collections.abc import Iterable
import csv
from datetime import UTC, datetime
import gzip
from hashlib import sha256
import io
import re
from time import monotonic
from unicodedata import normalize
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from app.core.local_text_analysis import MAX_TEXT_CHARS
from app.core.research import CIVIL_SAMPLE_SIZE, Record, ResearchError, ResearchRequest, bounds, civil_query_phrases, upstream_error

REVISION = "9beb047ad342ac2c3ac209d2d74e0b7c833fe294"
ARTIFACT = "test_public_expanded.csv.gz"
REPOSITORY = "https://huggingface.co/datasets/shuttie/jigsaw-unintended-bias"
URL = f"{REPOSITORY}/resolve/{REVISION}/data/{ARTIFACT}"
SOURCE = "https://huggingface.co/datasets/google/jigsaw_unintended_bias"
LICENSE = "https://creativecommons.org/publicdomain/zero/1.0/"
SHA256 = "a5a8fba390af3f17639b1bcef9b1c1b38373d3e45728f7eb814bfe5f3ea1c3d2"
ARCHIVE_BYTES = 16_425_656
ARCHIVE_ROWS = 97_320
PER_ARTICLE = 4
ZERO_SCORES = ("sexual_explicit", "obscene", "threat", "severe_toxicity")
REQUIRED = frozenset(("id", "comment_text", "created_date", "article_id", "publication_id",
                      "rating", "toxicity", "toxicity_annotator_count", *ZERO_SCORES))
TIMESTAMP = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}[ T][0-9]{2}:[0-9]{2}:[0-9]{2}"
                       r"(?:\.[0-9]{1,6})?(?:Z|[+-](?:[01][0-9]|2[0-3])(?::?[0-5][0-9])?)")
IDENTIFIER = re.compile(r"[1-9][0-9]{0,11}")
ENGLISH_WORDS = re.compile(r"\b(?:the|and|was|were|this|that|with|from|for|have|they|you|would)\b")
PRIVACY_MARKERS = re.compile(
    r"@|https?://|\bwww\.|(?:\d[\s()+.-]*){7,}|\b(?:full name|home address|my phone|contact me)\b"
    r"|[<>]|\x60\x60\x60|~~~|!?\[[^\]]*\]\(", re.IGNORECASE,
)


class DistributionRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        destination = urlsplit(newurl)
        if (req.full_url != URL or code != 302 or destination.scheme != "https"
                or destination.netloc != "us.aws.cdn.hf.co" or destination.fragment):
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download_archive() -> bytearray:
    request = Request(URL, headers={"Accept-Encoding": "identity", "User-Agent": "HissiyatResearch/0.1"})
    opener = build_opener(ProxyHandler({}), DistributionRedirect())
    deadline = monotonic() + 45
    payload = bytearray()
    try:
        with opener.open(request, timeout=15) as response:
            if response.status != 200:
                raise upstream_error(response.status)
            if (response.headers.get("Content-Length") != str(ARCHIVE_BYTES)
                    or response.headers.get("Content-Encoding", "identity") != "identity"):
                raise ResearchError("invalid_response", 502, 200)
            while chunk := response.read1(65536):
                if monotonic() >= deadline:
                    raise TimeoutError
                if len(payload) + len(chunk) > ARCHIVE_BYTES:
                    raise ResearchError("invalid_response", 502, 200)
                payload.extend(chunk)
    except HTTPError as exc:
        with exc:
            raise upstream_error(exc.code) from None
    except (TimeoutError, URLError, OSError) as exc:
        if isinstance(exc, TimeoutError) or isinstance(getattr(exc, "reason", None), TimeoutError):
            raise ResearchError("provider_timeout", 504) from None
        raise ResearchError("provider_unavailable", 502) from None
    if len(payload) != ARCHIVE_BYTES or sha256(payload).hexdigest() != SHA256:
        raise ResearchError("invalid_response", 502, 200)
    return payload


def source_time(value: str) -> datetime | None:
    if not TIMESTAMP.fullmatch(value):
        return None
    try:
        return datetime.fromisoformat(value).astimezone(UTC)
    except (ValueError, OverflowError):
        return None


SCREENING_REASONS = ("length", "privacy_or_markup", "language", "moderation", "safety_labels")


def exclusion_reason(text: str, normalized: str, row: dict, *, max_text_chars=MAX_TEXT_CHARS) -> str | None:
    if len(text) > max_text_chars:
        return "length"
    if PRIVACY_MARKERS.search(text):
        return "privacy_or_markup"
    if len(set(ENGLISH_WORDS.findall(normalized))) < 2:
        return "language"
    if row["rating"] != "approved":
        return "moderation"
    try:
        if (int(row["toxicity_annotator_count"]) > 0 and 0 <= float(row["toxicity"]) < 0.2
                and all(float(row[label]) == 0 for label in ZERO_SCORES)):
            return None
    except (ValueError, TypeError):
        pass
    return "safety_labels"


def phrase_pattern(phrase: str) -> str:
    return r"(?<!\w)" + re.escape(normalize("NFC", phrase.casefold())) + r"(?!\w)"


def select_sample(rows: Iterable[dict], scope: ResearchRequest, *, max_text_chars=MAX_TEXT_CHARS,
                  collapse_whitespace=False) -> tuple:
    start, end = bounds(scope)
    literal = re.compile("|".join(phrase_pattern(phrase) for phrase in civil_query_phrases(scope.query)))
    examined = matched = outside = invalid = duplicates = 0
    screening = dict.fromkeys(SCREENING_REASONS, 0)
    candidates = []
    for row in rows:
        examined += 1
        if examined > ARCHIVE_ROWS or None in row or any(row[column] is None for column in REQUIRED):
            raise ValueError
        text = normalize("NFC", row["comment_text"]).strip()
        if collapse_whitespace:
            text = " ".join(text.split())
        normalized = " ".join(text.casefold().split())
        if not literal.search(normalized):
            continue
        matched += 1
        timestamp = source_time(row["created_date"])
        identifier = row["id"]
        if timestamp is None or not IDENTIFIER.fullmatch(identifier):
            invalid += 1
        elif not start <= timestamp < end:
            outside += 1
        elif reason := exclusion_reason(text, normalized, row, max_text_chars=max_text_chars):
            screening[reason] += 1
        else:
            article = row["article_id"] if IDENTIFIER.fullmatch(row["article_id"]) else None
            publication = row["publication_id"] if IDENTIFIER.fullmatch(row["publication_id"]) else None
            record = Record("civil_comments", None, timestamp, text, ("en",), kind="comment",
                            article_id=article, publication_id=publication)
            candidates.append((sha256(identifier.encode("ascii")).digest(), normalized, record))

    # Deterministically resolve duplicates before applying per-article and overall caps.
    candidates.sort(key=lambda item: (item[0], item[1], item[2].published_at, item[2].article_id or "",
                                      item[2].publication_id or "", item[2].body))
    identifiers = set()
    texts = set()
    articles = Counter()
    records = []
    for identifier, text, record in candidates:
        if identifier in identifiers or text in texts:
            duplicates += 1
            continue
        identifiers.add(identifier)
        texts.add(text)
        article = record.article_id
        if len(records) >= CIVIL_SAMPLE_SIZE or articles[article] >= PER_ARTICLE:
            continue
        articles[article] += 1
        records.append(record)
    metrics = (matched, outside, invalid, duplicates, sum(screening.values()))
    return records, metrics, examined, len(identifiers), screening


def archive_sample(payload: bytes | bytearray, scope: ResearchRequest, *, max_text_chars=MAX_TEXT_CHARS,
                   collapse_whitespace=False) -> tuple:
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(payload)) as stream, io.TextIOWrapper(stream, encoding="utf-8-sig", newline="") as text:
            reader = csv.DictReader(text, strict=True)
            header = reader.fieldnames or []
            if not REQUIRED.issubset(header) or len(header) != len(set(header)):
                raise ValueError
            records, metrics, examined, eligible, screening = select_sample(
                reader, scope, max_text_chars=max_text_chars, collapse_whitespace=collapse_whitespace,
            )
            if examined != ARCHIVE_ROWS:
                raise ValueError
    except (ValueError, csv.Error, EOFError, OSError):
        raise ResearchError("invalid_response", 502, 200) from None
    return records, metrics, {
        "source": SOURCE, "license": "CC0 1.0", "license_url": LICENSE, "artifact": ARTIFACT,
        "revision": REVISION, "sha256": SHA256, "examined": examined, "eligible": eligible, "screening": screening,
        "retrieved_at": datetime.now(UTC).isoformat(),
    }


def fetch_sample(scope: ResearchRequest) -> tuple:
    return archive_sample(download_archive(), scope)
