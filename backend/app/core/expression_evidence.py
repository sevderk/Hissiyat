"""Conservative explicit English expressions with verifiable original spans."""

from collections import Counter
import re

from app.core.expression_signals import aggregate_expression_signals

RULES = {
    "self_emotion_v2": {
        "worry": r"\bi(?:['’]m| am| feel| felt| was) (?:very |really )?(?:worried|concerned)\b",
        "excitement": r"\bi(?:['’]m| am| feel| felt| was) (?:very |really )?excited\b",
        "frustration": r"\bi(?:['’]m| am| feel| felt| was) (?:very |really )?frustrated\b",
        "confidence": r"\bi(?:['’]m| am| feel| felt| was) (?:very |really )?confident\b",
        "curiosity": r"\bi(?:['’]m| am| feel| felt| was) (?:very |really )?curious\b",
    },
    "stated_need_v2": {
        "information": r"\bi (?:need|would like) (?:some |more )?(?:information|details|clarification)\b",
        "guidance": r"\bi (?:need|would like) (?:some |more )?(?:guidance|advice)\b",
        "support": r"\bi (?:need|would like) (?:some |more )?(?:help|support|assistance)\b",
    },
    "direct_request_v2": {
        "information": r"\b(?:can|could|would|will) (?:you|anyone|someone) (?:please )?(?:tell me|explain|clarify)\b",
        "guidance": r"\b(?:can|could|would|will) (?:you|anyone|someone) (?:please )?(?:advise me|guide me|give me (?:some )?(?:advice|guidance))\b",
        "support": r"\b(?:can|could|would|will) (?:you|anyone|someone) (?:please )?(?:help me|support me|assist me)\b",
    },
    "first_person_past_v2": {
        "reported": r"\bi (?:applied (?:for|to)|attended|completed|contacted|finished|installed|joined|learned|left|met|moved|opened|practiced|received|rewrote|started|submitted|tried|used(?! to\b)|visited|waited|worked|was (?:learning|using|waiting|working))\b",
    },
    "stated_problem_v1": {
        "problem": r"\bi (?:cannot|can't|can’t|could not|couldn't|couldn’t) (?:access|afford|find|use|reach|understand)\b",
    },
    "explicit_reason_v1": {
        "reason": r"\bi (?:applied|joined|left|chose|changed|used|started|stopped|moved)\b[^.!?\n]{0,80}\bbecause\b[^.!?\n]{3,100}",
    },
}
COMPILED = [(rule, label, re.compile(pattern, re.IGNORECASE)) for rule, labels in RULES.items() for label, pattern in labels.items()]
SENTENCES = re.compile(r"[^.!?\n]+[.!?]*")
UNCERTAIN = re.compile(r"\b(?:if|unless|suppose|supposing|imagine|wish|hypothetically|pretend|according to|for example|in theory|actually not|never|not only|might|maybe)\b", re.IGNORECASE)
REPORTING = re.compile(r"\b(?:said|says|told|wrote|writes|quoted|reports?|claimed|claims)\b", re.IGNORECASE)
QUOTES = re.compile(r'"[^"]*(?:"|$)|“[^”]*(?:”|$)|(?<!\w)[‘\'](?=\S).*?[’\'](?!\w)', re.DOTALL)
LABELS = ("worry", "excitement", "frustration", "confidence", "curiosity", "information", "guidance", "support", "reported",
          "problem", "reason")
MAX_EVIDENCE_PER_DOCUMENT = 64


def expression_evidence(texts: list[str], rows: list[int], *, disclose_text=False) -> dict:
    evidence = []
    counts = dict.fromkeys(LABELS, 0)
    abstentions = Counter()
    for text, row in zip(texts, rows, strict=True):
        quoted = [(match.start(), match.end()) for match in QUOTES.finditer(text)]
        labels = set()
        found = 0
        for sentence in SENTENCES.finditer(text):
            if found >= MAX_EVIDENCE_PER_DOCUMENT:
                abstentions["evidence_limit"] += 1
                break
            start, end = sentence.span()
            while start < end and text[start].isspace():
                start += 1
            span = text[start:end]
            if not span:
                continue
            if any(left < end and right > start for left, right in quoted) or span.startswith(">"):
                abstentions["quoted"] += 1
                continue
            if len(span) > 400 or UNCERTAIN.search(span) or re.search(r"\bnot\b", span, re.IGNORECASE):
                abstentions["ambiguous"] += 1
                continue
            reporting = REPORTING.search(span)
            matched_rules = []
            for rule, label, pattern in COMPILED:
                match = pattern.search(span)
                if match is None or (reporting is not None and reporting.start() < match.start()):
                    continue
                # Statement forms phrased as questions are ambiguous. A request needs its question mark.
                is_question = span.endswith("?")
                if (rule == "direct_request_v2") != is_question:
                    continue
                # Require a clause boundary before the author's own "I" or direct request.
                prefix = span[:match.start()].strip(" ,")
                if prefix and not re.search(r"(?:\b(?:and|but|yet|so)|,)\s*$", span[:match.start()], re.IGNORECASE):
                    continue
                matched_rules.append((rule, label))
            for rule, label in matched_rules[:MAX_EVIDENCE_PER_DOCUMENT - found]:
                item = {"row": row, "start": start, "end": end, "rule": rule, "label": label}
                if disclose_text:
                    item["text"] = span
                evidence.append(item)
                labels.add(label)
                found += 1
        for label in labels:
            counts[label] += 1
    return {"method": "explicit_english_spans_v2", "documents": len(texts), "counts": counts,
            "abstentions": dict(abstentions), "evidence": evidence}


def evidence_signals(report: dict) -> dict:
    # Keep the existing aggregate API shape. Each category counts each document once.
    result = aggregate_expression_signals([])
    result["submitted_texts"] = report["documents"]
    for group in ("emotions", "needs", "experiences"):
        for label in result[group]:
            result[group][label] = report["counts"][label]
    return result
