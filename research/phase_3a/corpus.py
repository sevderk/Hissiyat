"""Prepare privacy-filtered responses from the licensed Phase 3A snapshot."""

from collections import Counter
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path, PurePosixPath
import re
import unicodedata
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile, ZipFile

from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import fromstring


SHEET_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
OFFICE_REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
MAX_WORKBOOK_BYTES = 200_000
MAX_ZIP_MEMBERS = 150
MAX_EXPANDED_BYTES = 5_000_000
MAX_XML_BYTES = 2_000_000
THRESHOLDS = (30, 15)
WORD = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*", re.UNICODE)
ENGLISH_MARKERS = frozenset(
    "the a an and to of in for that i you my we they it is are was were with "
    "have has not be on by but from as or this how when what which their our do "
    "can would could because about no never".split()
)
DIRECT_IDENTIFIER = re.compile(
    r"\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b"
    r"|\bmy (?:full |legal )?name is\s+\w",
    re.IGNORECASE,
)
CONTACT_DASHES = str.maketrans(dict.fromkeys("\u2010\u2011\u2012\u2013\u2014\u2015\u2212\ufe58\ufe63\uff0d", "-"))
PHONE_NUMBER = re.compile(r"(?<!\w)\+?\(?\d(?:[ .()-]*\d){7,}(?!\w)")
YEAR_RANGE = re.compile(r"(?:19|20)[0-9]{2} *- *(?:19|20)[0-9]{2}")
YEAR_CONTEXT = re.compile(r"\b(?:academic|school) year $", re.IGNORECASE)
EMAIL_AT = r"(?:\s*@\s*|\s*\[\s*at\s*\]\s*|\s*\(\s*at\s*\)\s*|\s+at\s+)"
EMAIL_DOT = r"(?:\s*\.\s*|\s*\[\s*dot\s*\]\s*|\s*\(\s*dot\s*\)\s*|\s+dot\s+)"
OBFUSCATED_EMAIL = re.compile(
    rf"\b[a-z0-9][a-z0-9._%+-]{{0,63}}{EMAIL_AT}"
    rf"(?:[a-z0-9][a-z0-9-]{{0,62}}{EMAIL_DOT}){{1,5}}[a-z]{{2,24}}\b",
    re.IGNORECASE,
)
SPOKEN_DIGIT = r"(?:zero|oh|one|two|three|four|five|six|seven|eight|nine)"
SPOKEN_NUMBER = re.compile(rf"\b{SPOKEN_DIGIT}(?:[\s,-]+{SPOKEN_DIGIT}){{6,}}\b", re.IGNORECASE)
IDENTITY_FIELD = (
    r"(?:e[ -]?mail(?: address)?|(?:mobile|phone)(?: number)?|(?:home |postal )?address"
    r"|full name|legal name|student id|passport(?: number)?|date of birth)"
)
CONTACT_CUE = re.compile(
    rf"\b(?:(?:my|our) {IDENTITY_FIELD}\s+is\b|{IDENTITY_FIELD}\s*[:=])"
    r"|\b(?:contact|reach|call|text|message|e[ -]?mail)\s+(?:me|us)\s+(?:at|on|via)\b",
    re.IGNORECASE,
)
PRIVATE_CONTEXT = re.compile(
    r"https?://|www\.|(?<!\w)@[\w.]+"
    r"|\b\d{1,4}[-/]\d{1,2}[-/]\d{1,4}\b"
    r"|\b(?:diagnosed with|medical diagnosis|immigration status|sexual assault|"
    r"self[- ]harm|suicidal|suicide)\b",
    re.IGNORECASE,
)


class CorpusError(ValueError):
    """A non-disclosing structural or privacy stop."""


@dataclass(frozen=True)
class Response:
    group: int
    question: int
    text: str | None = field(repr=False)


@dataclass(frozen=True)
class PreparedResponse:
    group: int
    question: int
    word_count: int
    text: str = field(repr=False)


def normalized(text):
    text = unicodedata.normalize("NFKC", text).replace("’", "'")
    visible = "".join(char for char in text if unicodedata.category(char) != "Cf")
    return " ".join(visible.split())


def _looks_like_phone(text):
    for number in PHONE_NUMBER.finditer(text):
        if YEAR_RANGE.fullmatch(number.group()) and YEAR_CONTEXT.search(text, max(0, number.start() - 16), number.start()):
            continue
        return True
    return False


def _xml(package, member):
    with package.open(member) as stream:
        content = stream.read(MAX_XML_BYTES + 1)
    if len(content) > MAX_XML_BYTES:
        raise CorpusError("workbook_expansion_limit")
    try:
        return fromstring(content, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except DefusedXmlException:
        raise CorpusError("unsafe_xml") from None
    except (ParseError, LookupError, UnicodeError):
        raise CorpusError("malformed_xml") from None


def _visible_sheet(package):
    members = package.infolist()
    names = package.namelist()
    if (
        len(members) > MAX_ZIP_MEMBERS
        or sum(member.file_size for member in members) > MAX_EXPANDED_BYTES
        or any(member.file_size > MAX_XML_BYTES for member in members)
    ):
        raise CorpusError("workbook_expansion_limit")
    if len(names) != len(set(names)) or any(
        name.startswith("/") or ".." in PurePosixPath(name).parts
        or "vbaproject" in name.lower() or "/embeddings/" in name.lower()
        for name in names
    ) or any(member.flag_bits & 1 for member in members):
        raise CorpusError("unsafe_workbook_package")
    if any(
        rel.get("TargetMode") == "External"
        for name in names if name.endswith(".rels")
        for rel in _xml(package, name)
    ):
        raise CorpusError("external_workbook_relationship")
    sheets = _xml(package, "xl/workbook.xml").findall(f".//{SHEET_NS}sheet")
    if len(sheets) != 1 or sheets[0].get("state", "visible") != "visible":
        raise CorpusError("unexpected_worksheet_count")
    sheet_id = sheets[0].get(OFFICE_REL_NS + "id")
    relationships = _xml(package, "xl/_rels/workbook.xml.rels")
    targets = [rel.get("Target", "") for rel in relationships if rel.get("Id") == sheet_id]
    if len(targets) != 1:
        raise CorpusError("missing_worksheet")
    target = targets[0]
    target = target[1:] if target.startswith("/") else f"xl/{target}"
    if not re.fullmatch(r"xl/worksheets/sheet\d+\.xml", target):
        raise CorpusError("unexpected_worksheet_location")
    return _xml(package, target)


def _cell_text(cell, strings):
    if cell.find(SHEET_NS + "f") is not None:
        raise CorpusError("formula_in_input_columns")
    kind = cell.get("t", "")
    value = cell.findtext(SHEET_NS + "v", "")
    if kind == "inlineStr":
        return "".join(node.text or "" for node in cell.iter(SHEET_NS + "t"))
    if kind == "s" and value:
        if not value.isdecimal() or int(value) >= len(strings):
            raise CorpusError("invalid_shared_string")
        return strings[int(value)]
    return value if kind == "str" else ""


def read_workbook(workbook: Path | bytes, group: int, expected_questions: int = 24):
    """Read responses and the internal question signature for the snapshot."""
    if isinstance(workbook, bytes):
        payload = workbook
    else:
        with workbook.open("rb") as stream:
            payload = stream.read(MAX_WORKBOOK_BYTES + 1)
    if len(payload) > MAX_WORKBOOK_BYTES:
        raise CorpusError("workbook_size_limit")
    try:
        with ZipFile(BytesIO(payload)) as package:
            sheet = _visible_sheet(package)
            strings = []
            if "xl/sharedStrings.xml" in package.namelist():
                strings = [
                    "".join(node.text or "" for node in entry.iter(SHEET_NS + "t"))
                    for entry in _xml(package, "xl/sharedStrings.xml")
                ]
            responses = []
            prompt_signature = []
            for row in sheet.iter(SHEET_NS + "row"):
                if row.get("hidden") in {"1", "true"}:
                    raise CorpusError("hidden_workbook_row")
                cells = {}
                for cell in row.findall(SHEET_NS + "c"):
                    address = cell.get("r", "")
                    if re.fullmatch(r"[CD]\d+", address):
                        column = address[0]
                        if column in cells:
                            raise CorpusError("duplicate_input_cell")
                        cells[column] = _cell_text(cell, strings)
                question = normalized(cells.get("C", ""))
                if not question.endswith("?"):
                    continue
                prompt_signature.append(question.casefold())
                answer = cells.get("D", "")
                responses.append(Response(group, len(responses) + 1, answer if normalized(answer) else None))
            if len(responses) != expected_questions:
                raise CorpusError("unexpected_question_structure")
            return responses, tuple(prompt_signature)
    except (BadZipFile, KeyError, NotImplementedError):
        raise CorpusError("malformed_workbook") from None


def prepare(responses):
    """Screen responses before statistical feature selection."""
    prepared = []
    counts = Counter(missing=0, under_15=0, language=0, private_context=0)
    duplicates = Counter()
    exact_duplicates = {threshold: Counter() for threshold in THRESHOLDS}
    text_rows = total_words = retained_original_words = 0
    for response in responses:
        original = response.text or ""
        text = normalized(original)
        if not text:
            counts["missing"] += 1
            continue
        contact_text = text.translate(CONTACT_DASHES)
        if _looks_like_phone(contact_text) or any(
            pattern.search(contact_text) for pattern in (DIRECT_IDENTIFIER, OBFUSCATED_EMAIL, SPOKEN_NUMBER)
        ):
            raise CorpusError("possible_direct_identifier")
        if CONTACT_CUE.search(contact_text):
            raise CorpusError("privacy_review_required")

        words = WORD.findall(text)
        count = len(words)
        text_rows += 1
        total_words += count
        duplicate_key = text.casefold()
        duplicates[duplicate_key] += 1
        for threshold, tally in exact_duplicates.items():
            if count >= threshold:
                tally[duplicate_key] += 1
        if PRIVATE_CONTEXT.search(text):
            counts["private_context"] += 1
            continue
        if count < min(THRESHOLDS):
            counts["under_15"] += 1
            continue
        if sum(token.lower() in ENGLISH_MARKERS for token in words) / count < 0.15:
            counts["language"] += 1
            continue
        retained_original_words += len(WORD.findall(original))
        prepared.append(PreparedResponse(response.group, response.question, count, text))

    retained_words = sum(row.word_count for row in prepared)
    return prepared, {
        "question_rows": len(responses),
        "workbook_groups": len({row.group for row in responses}),
        "text_rows": text_rows,
        "words": total_words,
        "excluded_before_secondary": dict(counts),
        "secondary_word_counts": {
            "retained_before_normalization": retained_original_words,
            "retained_after_normalization": retained_words,
            "excluded_after_normalization": total_words - retained_words,
        },
        "exact_repeated_occurrences": sum(count - 1 for count in duplicates.values()),
        "subsets": {
            str(threshold): {
                "before_filter": sum(tally.values()),
                "retained": sum(row.word_count >= threshold for row in prepared),
                "groups": len({row.group for row in prepared if row.word_count >= threshold}),
                "retained_words": sum(row.word_count for row in prepared if row.word_count >= threshold),
                "exact_repeated_occurrences_before_filter": sum(count - 1 for count in tally.values()),
            }
            for threshold, tally in exact_duplicates.items()
        },
    }
