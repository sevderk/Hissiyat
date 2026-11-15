"""Prepare and review a short blinded sample on the owner's local desktop."""

import argparse
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
import hmac
import json
from pathlib import Path
import sys
from tempfile import NamedTemporaryFile

from research.phase_4c import prepare
from research.phase_4e import review, window


SCHEMA = "hissiyat_careernet_blind_review_v1"
FILE = "blind-review.json"
LOCK = "blind-review.lock"
CALIBRATION_PREFIX = 5
LABELS = {key: review.LABELS[key] for key in ("education", "career", "employment", "opportunities", "emotion")}
CONTEXT = {"include": "Destekleniyor", "generic_advice": "Desteklenmiyor", "unclear": "Belirsiz"}


def _opaque(key, purpose, value):
    return hmac.digest(key, f"{SCHEMA}:{purpose}:{value}".encode("ascii"), "sha256").hex()


def _plan(first, key):
    if review.review_progress(first) != {"A": (40, 40), "B": (40, 40)}:
        raise review.ReviewError("expected_40_complete_reviews_per_cohort")

    def ranked(ids):
        return sorted(ids, key=lambda identifier: _opaque(key, "select", identifier))

    eligible = [(identifier, cohort, first["decisions"][identifier])
                for identifier, cohort in list(first["items"].items())[CALIBRATION_PREFIX:]
                if first["decisions"][identifier]["privacy"] == "suitable"]
    a = ranked(identifier for identifier, cohort, _ in eligible if cohort == "A")
    b_positive = ranked(identifier for identifier, cohort, choice in eligible
                        if cohort == "B" and choice["b_decision"] == "include")
    b_negative = ranked(identifier for identifier, cohort, choice in eligible
                        if cohort == "B" and choice["b_decision"] in ("generic_advice", "outside_scope", "hypothetical"))
    if len(a) < 6 or len(b_positive) < 5 or not b_negative:
        raise review.ReviewError("insufficient_blinded_sample")
    mixed = sorted(a[:6] + b_positive[:5] + b_negative[:1], key=lambda identifier: _opaque(key, "order", identifier))
    return {_opaque(key, "blind-id", identifier): identifier for identifier in mixed}


def _binding(first, key):
    coded = json.dumps([list(first["items"].items()), first["decisions"]], sort_keys=True, ensure_ascii=True)
    return _opaque(key, "first-review-binding", coded)


def _blind_items(reconstructed, first, plan):
    if [(item.review_id, item.cohort) for item in reconstructed] != list(first["items"].items()):
        raise review.ReviewError("exact_review_linkage_failed")
    indexed = {item.review_id: item for item in reconstructed}
    return [review.Item(blind_id, "X", indexed[first_id].title, indexed[first_id].body)
            for blind_id, first_id in plan.items()]


def _validate(decision, _cohort="X"):
    review.validate_decision(decision, "B")
    if not set(decision["labels"]) <= LABELS.keys() or (
        decision["b_decision"] is not None and decision["b_decision"] not in CONTEXT
    ):
        raise review.ReviewError("invalid_blinded_decision")


class BlindWindow(window.ReviewWindow):
    labels_and_definitions = LABELS
    context_caption = "Kişisel belirsizlik kararı"
    context_guide = "Eğitim, iş, kariyer yönü veya gelecek fırsatlarıyla ilgili kişisel belirsizliği değerlendirin."
    context_choices = CONTEXT
    validate = staticmethod(_validate)

    def show_context(self):
        return True

    def heading_text(self):
        return (f"Soru {self.state['position'] + 1}/{len(self.items)}"
                f"  ·  Kaydedilen {len(self.state['decisions'])}/{len(self.items)}")


def _workspace(path):
    directory = prepare._private_directory(path, phase="4e", allowed_files=(FILE, LOCK))
    prepare._check_windows_access(directory, verify_files=True)
    if (directory / FILE).exists() and (directory / FILE).stat().st_nlink != 1:
        raise review.ReviewError("unexpected_private_review_file")
    return directory


@contextmanager
def _exclusive(directory):
    path = directory / LOCK
    try:
        lock = path.open("xb")
    except FileExistsError:
        raise review.ReviewError("blinded_workspace_in_use") from None
    try:
        with lock:
            yield
    finally:
        path.unlink(missing_ok=True)


def _state(directory, first, key, plan):
    expected = {
        "schema": SCHEMA, "binding": _binding(first, key), "items": list(plan),
        "delete_by_utc": first["delete_by_utc"],
    }
    path = directory / FILE
    if not path.exists():
        return {**expected, "position": 0, "decisions": {}}
    with path.open(encoding="utf-8") as file:
        raw = file.read(20_001)
    try:
        saved = json.loads(raw, object_pairs_hook=review._unique_fields)
        if (len(raw) > 20_000 or not isinstance(saved, dict) or
                saved.keys() != expected.keys() | {"position", "decisions"} or
                any(saved[name] != value for name, value in expected.items()) or
                type(saved["position"]) is not int or not 0 <= saved["position"] < 12 or
                not isinstance(saved["decisions"], dict) or not saved["decisions"].keys() <= plan.keys()):
            raise ValueError
        for choice in saved["decisions"].values():
            _validate(choice)
    except (ValueError, TypeError, KeyError):
        raise review.ReviewError("invalid_blinded_state") from None
    return saved


def _save(directory, state):
    if datetime.fromisoformat(state["delete_by_utc"]) <= datetime.now(timezone.utc):
        raise review.ReviewError("review_deadline_elapsed")
    _workspace(directory)
    temp = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory, delete=False) as stream:
            temp = Path(stream.name)
            json.dump(state, stream, ensure_ascii=True, indent=2)
        temp.replace(directory / FILE)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def agreement(pairs):
    n = len(pairs)
    if not n:
        return {"compared": 0, "agreed": 0, "percent": None, "kappa": None}
    agreed = sum(left == right for left, right in pairs)
    left_counts = Counter(left for left, _ in pairs)
    right_counts = Counter(right for _, right in pairs)
    expected_pairs = sum(count * right_counts[label] for label, count in left_counts.items())
    kappa = (agreed * n - expected_pairs) / (n * n - expected_pairs) if expected_pairs != n * n else None
    return {"compared": n, "agreed": agreed, "percent": round(100 * agreed / n, 2),
            "kappa": round(kappa, 4) if kappa is not None else None}


def summarize(first, second, plan):
    if second["decisions"].keys() != plan.keys():
        raise review.ReviewError("independent_review_incomplete")
    choices = [(first["items"][identifier], first["decisions"][identifier], second["decisions"][blind_id])
               for blind_id, identifier in plan.items()]
    eligible = [(cohort, left, right) for cohort, left, right in choices
                if left["privacy"] == right["privacy"] == "suitable"]

    def contextual(decision):
        value = decision["b_decision"]
        return value if value in ("include", "unclear") else "generic_advice"

    return {
        "privacy": agreement([(left["privacy"], right["privacy"]) for _, left, right in choices]),
        "labels": {label: agreement([(label in left["labels"], label in right["labels"])
                                     for _, left, right in eligible]) for label in LABELS},
        "personal_uncertainty_B_only": agreement([(contextual(left), contextual(right))
                                                 for cohort, left, right in eligible if cohort == "B"]),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    task = parser.add_mutually_exclusive_group(required=True)
    task.add_argument("--approved-careernet-v1.1", action="store_true")
    task.add_argument("--summarize-confirmed-independent", action="store_true")
    parser.add_argument("--first-review", type=Path, required=True)
    parser.add_argument("--blind-workspace", type=Path, required=True)
    args = parser.parse_args()
    try:
        first_directory = review._private_directory(args.first_review)
        directory = _workspace(args.blind_workspace)
        if directory == first_directory:
            raise review.ReviewError("separate_blinded_workspace_required")
        first = review._read_state(first_directory, prepare.REFERENCE["publisher_sha256"])
        if first is None:
            raise review.ReviewError("first_review_missing")
        with (first_directory / review.KEY_FILE).open("rb") as stream:
            key = stream.read(33)
        if len(key) != 32:
            raise review.ReviewError("invalid_review_key")
        plan = _plan(first, key)
        if args.summarize_confirmed_independent:
            with _exclusive(directory):
                print(json.dumps(summarize(first, _state(directory, first, key, plan), plan)))
            return 0
        review._require_local_session()
        with _exclusive(directory):
            state = _state(directory, first, key, plan)
            payload = prepare._download()
            items = _blind_items(review.review_items(payload, key), first, plan)
            del payload, key, first, plan
            _save(directory, state)
            window.launch(items, state, lambda: _save(directory, state), window_type=BlindWindow)
        return 0
    except (review.ReviewError, prepare.PreparationError) as error:
        print(json.dumps({"status": "stopped", "reason": error.args[0]}))
    except (Exception, KeyboardInterrupt):
        print('{"status":"stopped","reason":"local_execution_failed"}')
    return 2


if __name__ == "__main__":
    sys.exit(main())
