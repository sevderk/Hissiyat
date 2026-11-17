from collections import Counter
import json
from pathlib import Path

import pytest

from app.core.expression_signals import aggregate_expression_signals


CASES = json.loads((Path(__file__).parents[1] / "fixtures/expression_signals.json").read_text(encoding="utf-8"))


def counts(results):
    return {**results["emotions"], **results["needs"], **results["experiences"]}


@pytest.mark.parametrize("case", CASES, ids=[row["case"] for row in CASES])
def test_explicit_expression_or_abstention(case):
    result = aggregate_expression_signals([case["text"]])
    assert result["submitted_texts"] == 1
    assert {label for label, count in counts(result).items() if count} == set(case["labels"])
    assert all(count in (0, 1) for count in counts(result).values())


def test_aggregate_determinism_overlap_and_changes():
    texts = [row["text"] for row in CASES]
    expected = Counter(label for row in CASES for label in row["labels"])
    result = aggregate_expression_signals(texts)
    assert result == aggregate_expression_signals(texts) == aggregate_expression_signals(texts[::-1])
    assert result["submitted_texts"] == len(texts)
    assert {label: count for label, count in counts(result).items() if count} == expected

    modified = aggregate_expression_signals(["I am not worried about the delay.", *texts[1:]])
    assert modified["submitted_texts"] == result["submitted_texts"]
    assert counts(modified) == counts(result) | {"worry": 0}
