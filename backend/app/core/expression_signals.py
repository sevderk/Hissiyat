"""Conservative English expression rules for request-local aggregate counts."""

import re
from collections.abc import Sequence

# A quoted span becomes one marker before sentence splitting, even if it contains punctuation.
_QUOTES = re.compile(r'"[^"]*(?:"|$)|(?<!\w)\'(?=\S).*?\'(?!\w)')
_SMART_QUOTES = str.maketrans("‘’“”", "''\"\"")
_SENTENCES = re.compile(r"[^.!?;]+[.!?;]?")
_CLAUSES = re.compile(r"\s*(?:,|\b(?:and|but|yet|so)\b)\s*(?=i\b)")
_UNCERTAIN_CONTEXT = re.compile(
    r"\b(?:if|unless|suppos(?:e|ing)|assum(?:e|ing)|imagin(?:e|ing)|wish|hypothetically|"
    r"pretend(?:ed|ing)?|according to|for example|in theory|actually not)\b"
)
_REPORTING = re.compile(
    r"\b(?:said|says?|told|tells|ask(?:s|ed)|claim(?:s|ed)|wrote|writes|mention(?:s|ed)|report(?:s|ed)|quoted)\b"
)

_SELF_STATE = r"i (?:am feeling|was feeling|have been|am|was|feel|felt) (?:very |really |quite |so |a little )?"
_EMOTIONS = {
    label: re.compile(_SELF_STATE + words + r"\b")
    for label, words in {
        "worry": r"(?:worried|concerned)", "excitement": r"excited", "frustration": r"frustrated",
        "confidence": r"confident", "curiosity": r"curious",
    }.items()
}
_NEED = r"i (?:need|would like) (?:(?:some|more) )?"
_REQUEST = r"(?:can|could|would|will) (?:you|anyone|someone) (?:please )?"
_NEEDS = {
    "information": re.compile(_NEED + r"(?:information|details|clarification)(?: (?:about|on|regarding|for)\b|$)"),
    "guidance": re.compile(_NEED + r"(?:guidance|advice)(?: (?:about|on|with|for)\b|$)"),
    "support": re.compile(_NEED + r"(?:help|support|assistance)(?: (?:with|to|for|on|in)\b|$)"),
}
_DIRECT_REQUESTS = {
    "information": re.compile(_REQUEST + r"(?:tell me|explain|clarify)\b"),
    "guidance": re.compile(_REQUEST + r"(?:advise me|guide me|give me (?:some )?(?:advice|guidance))\b"),
    "support": re.compile(_REQUEST + r"(?:help me|support me|assist me)\b"),
}
_EXPERIENCE = re.compile(
    r"i (?:applied (?:for|to)|attended|completed|contacted|finished|installed|joined|learned|left|"
    r"met|moved|opened|practiced|received|rewrote|started|submitted|tried|used(?! to\b)|visited|waited|worked|"
    r"was (?:learning|using|waiting|working))\b"
)


def aggregate_expression_signals(texts: Sequence[str]) -> dict:
    emotions = dict.fromkeys(_EMOTIONS, 0)
    needs = dict.fromkeys(_NEEDS, 0)
    experience_count = 0
    for text in texts:
        normalized = _QUOTES.sub(" \0 ", text.translate(_SMART_QUOTES)).casefold()
        normalized = re.sub(r"\bi'm\b", "i am", normalized)
        normalized = re.sub(r"\bi'd like\b", "i would like", normalized)
        marked_emotions = set()
        marked_needs = set()
        reported_experience = False
        for match in _SENTENCES.finditer(normalized):
            sentence = " ".join(match.group().split())
            if "\0" in sentence or _UNCERTAIN_CONTEXT.search(sentence):
                continue
            question = sentence.endswith("?")
            for clause in _CLAUSES.split(sentence.rstrip(".?!;")):
                clause = clause.strip(" ,")
                if question:
                    marked_needs.update(key for key, rule in _DIRECT_REQUESTS.items() if rule.match(clause))
                else:
                    marked_emotions.update(key for key, rule in _EMOTIONS.items() if rule.match(clause))
                    marked_needs.update(key for key, rule in _NEEDS.items() if rule.match(clause))
                    reported_experience |= _EXPERIENCE.match(clause) is not None
                # A later coordinated clause could still be inside the attributed account.
                if _REPORTING.search(clause):
                    break
        for label in marked_emotions:
            emotions[label] += 1
        for label in marked_needs:
            needs[label] += 1
        experience_count += reported_experience
    return {
        "submitted_texts": len(texts), "emotions": emotions, "needs": needs,
        "experiences": {"reported": experience_count},
    }
