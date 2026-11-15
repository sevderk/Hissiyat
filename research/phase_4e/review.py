"""Owner-only native review. Participant text is never serialized."""

import argparse
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import sys
from tempfile import NamedTemporaryFile

from research.phase_4c import prepare


CODEBOOK = "hissiyat_careernet_review_v1"
PER_COHORT = 40
STATE_FILE = "review.json"
KEY_FILE = "review.key"
PRIVACY = {
    "suitable": "Yerel araştırmaya uygun",
    "needs_review": "Ek mahremiyet incelemesi gerekli",
    "exclude": "Mahremiyet nedeniyle dışla",
}
EVIDENCE = {"none": "İşaretlenmedi", "direct": "Doğrudan", "contextual": "Bağlamsal"}
LABELS = {
    "education": ("Eğitim veya öğrenim kararı", "Okul, yeterlilik veya öğrenim yoluna ilişkin seçim ya da ihtiyaç."),
    "career": ("Kariyer hedefi veya beklentisi", "İstenen rol, kariyer yönü veya açık beklenti."),
    "employment": ("İstihdam belirsizliği", "İş bulma, sürdürme veya değiştirmeye ilişkin belirsizlik."),
    "opportunities": ("Gelecek fırsatlarına ilişkin kaygı", "Fırsat, zamanlama veya erişime ilişkin kaygı ya da tereddüt."),
    "reskilling": ("Yeni beceri veya mesleki gelişim", "Beceri edinme veya mesleki ilerleme kararı ya da ihtiyacı."),
    "information": ("Genel bilgi arama", "Bilgi veya rehberlik talebi. Tek başına B'ye dahil edilmez."),
    "emotion": ("Açıkça ifade edilen duygu", "Kişinin kendi duygusuna dair doğrudan ifade. Kaygı varsaymayın."),
    "experience": ("Kişisel deneyim", "Bir olay veya durumun birinci tekil şahıs anlatımı."),
}
B_DECISIONS = {
    "include": "Kişisel belirsizlik destekleniyor",
    "generic_advice": "Genel tavsiye talebi",
    "outside_scope": "Kapsam dışı",
    "hypothetical": "Varsayımsal veya kişisel bağ yok",
    "unclear": "Yetersiz veya belirsiz kanıt",
}


class ReviewError(ValueError):
    """An error without participant content."""


@dataclass(frozen=True)
class Item:
    review_id: str
    cohort: str
    title: str = field(repr=False)
    body: str = field(repr=False)


def review_items(payload, key, **source_checks):
    """Draw at most 40 candidates per cohort with a separate fixed rank."""
    aggregate, questions, general, enriched = prepare._screen_and_select(payload, **source_checks)
    if aggregate["status"] == "stopped_for_privacy":
        raise ReviewError("source_stopped_for_privacy")
    by_id = {question.question_id: question for question in questions}
    items = []
    def subset_rank(cohort, member):
        message = f"{CODEBOOK}:subset:{prepare.SEED}:{cohort}:{member.question_id}".encode("ascii")
        return sha256(message).digest(), member.question_id

    for cohort, members in (("A", general), ("B", enriched)):
        for member in sorted(members, key=lambda member: subset_rank(cohort, member))[:PER_COHORT]:
            question = by_id[member.question_id]
            message = f"{CODEBOOK}:{cohort}:{question.question_id}".encode("ascii")
            review_id = hmac.digest(key, message, "sha256").hex()
            items.append(Item(review_id, cohort, question.title, question.body))
    if not items:
        raise ReviewError("no_review_candidates")
    return items


def _require_local_session():
    import ctypes

    # Do not materialize a real review window through a remote Windows session.
    if ctypes.windll.user32.GetSystemMetrics(0x1000):
        raise ReviewError("remote_windows_session")
    session_id = ctypes.c_ulong()
    if (not ctypes.windll.kernel32.ProcessIdToSessionId(os.getpid(), ctypes.byref(session_id)) or
            session_id.value == 0 or session_id.value != ctypes.windll.kernel32.WTSGetActiveConsoleSessionId()):
        raise ReviewError("interactive_local_windows_session_required")


def validate_decision(decision, cohort):
    if not isinstance(decision, dict) or set(decision) != {"privacy", "labels", "insufficient", "b_decision"}:
        raise ReviewError("invalid_review_decision")
    privacy, labels, insufficient, b_decision = (decision[key] for key in
                                                 ("privacy", "labels", "insufficient", "b_decision"))
    if (not isinstance(privacy, str) or privacy not in PRIVACY or not isinstance(labels, dict)
            or type(insufficient) is not bool or not (b_decision is None or isinstance(b_decision, str))):
        raise ReviewError("invalid_review_decision")
    if privacy != "suitable":
        if labels or insufficient or b_decision is not None:
            raise ReviewError("privacy_decision_blocks_labels")
        return
    if any(label not in LABELS or evidence not in ("direct", "contextual") or
           (label == "emotion" and evidence != "direct") for label, evidence in labels.items()):
        raise ReviewError("invalid_label_evidence")
    if insufficient == bool(labels):
        raise ReviewError("choose_labels_or_insufficient_evidence")
    if (cohort == "A" and b_decision is not None) or (cohort == "B" and b_decision not in B_DECISIONS):
        raise ReviewError("choose_contextual_b_decision")
    if insufficient and b_decision is not None and b_decision != "unclear":
        raise ReviewError("insufficient_evidence_requires_unclear_b")


def _private_directory(path):
    directory = prepare._private_directory(path, phase="4e", allowed_files=(STATE_FILE, KEY_FILE))
    prepare._check_windows_access(directory, verify_files=True)
    for item in directory.iterdir():
        if item.stat().st_nlink != 1:
            raise ReviewError("unexpected_private_review_file")
    return directory


@contextmanager
def _locked_key(directory):
    import msvcrt

    path = directory / KEY_FILE
    if not path.exists():
        if (directory / STATE_FILE).exists():
            raise ReviewError("review_key_missing")
        with path.open("xb") as file:
            file.write(secrets.token_bytes(32))
    with path.open("r+b") as file:
        # Hold the byte past the key for the lifetime of the review window.
        file.seek(32)
        try:
            msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            raise ReviewError("review_workspace_in_use") from None
        try:
            if os.fstat(file.fileno()).st_size != 32:
                raise ReviewError("invalid_review_key")
            file.seek(0)
            yield file.read(32)
        finally:
            file.seek(32)
            msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)


def _read_state(directory, source):
    path = directory / STATE_FILE
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as file:
        raw = file.read(100_001)
    return _parse_state(raw, source)


def _unique_fields(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError
        result[name] = value
    return result


def _parse_state(raw, source):
    try:
        state = json.loads(raw, object_pairs_hook=_unique_fields)
        if (len(raw) > 100_000 or
                not isinstance(state, dict) or
                set(state) != {"source", "codebook", "delete_by_utc", "position", "items", "decisions"} or
                state["source"] != source or state["codebook"] != CODEBOOK or
                not isinstance(state["items"], dict) or not isinstance(state["decisions"], dict) or
                type(state["position"]) is not int or not isinstance(state["delete_by_utc"], str)):
            raise ValueError
        deadline = datetime.fromisoformat(state["delete_by_utc"])
        if deadline.tzinfo is None or deadline > _maximum_deadline():
            raise ValueError
        if not 0 <= state["position"] < len(state["items"]) <= PER_COHORT * 2:
            raise ValueError
        for review_id, cohort in state["items"].items():
            if not re.fullmatch(r"[a-f0-9]{64}", review_id) or cohort not in ("A", "B"):
                raise ValueError
        for review_id, decision in state["decisions"].items():
            validate_decision(decision, state["items"][review_id])
    except (ValueError, TypeError, KeyError):
        raise ReviewError("invalid_saved_review") from None
    if deadline <= datetime.now(timezone.utc):
        raise ReviewError("review_deadline_elapsed")
    return state


def _maximum_deadline():
    return prepare._retention_deadline(datetime.now(timezone.utc), prepare.PILOT_LAST_DAY.isoformat())


def _state_for_items(items, source, saved):
    index = {item.review_id: item.cohort for item in items}
    if len(index) != len(items):
        raise ReviewError("duplicate_review_item")
    if saved is not None:
        if list(saved["items"].items()) != list(index.items()):
            raise ReviewError("saved_review_selection_changed")
        return saved
    return {"source": source, "codebook": CODEBOOK, "delete_by_utc": _maximum_deadline().isoformat(),
            "position": 0, "items": index, "decisions": {}}


def _store_state(directory, state):
    if datetime.fromisoformat(state["delete_by_utc"]) <= datetime.now(timezone.utc):
        raise ReviewError("review_deadline_elapsed")
    _private_directory(directory)
    temporary = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory, delete=False) as file:
            temporary = Path(file.name)
            json.dump(state, file, ensure_ascii=True, indent=2)
            file.write("\n")
        temporary.replace(directory / STATE_FILE)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def review_progress(state):
    return {cohort: (sum(value == cohort and key in state["decisions"]
                         for key, value in state["items"].items()),
                     sum(value == cohort for value in state["items"].values()))
            for cohort in ("A", "B")}


def fictional_items(key):
    items = []
    for cohort in ("A", "B"):
        for number in range(1, 4):
            review_id = hmac.digest(key, f"fictional:{cohort}:{number}".encode("ascii"), "sha256").hex()
            items.append(Item(review_id, cohort, f"Kurgusal deneme {cohort}{number}",
                              "I am considering a fictional career in building musical instruments. "
                              "I am unsure whether I should learn repair skills or study sound engineering."))
    return items


def main():
    parser = argparse.ArgumentParser(description="Yerel CareerNet insan incelemesi")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fictional", action="store_true", help="Ağ erişimi olmadan kurgusal örnekleri aç.")
    mode.add_argument("--approved-careernet-v1.1", action="store_true", help="Bu açılış için ayrı onay gerekir.")
    parser.add_argument("--workspace", required=True, type=Path)
    args = parser.parse_args()

    try:
        from research.phase_4e.window import launch

        if not args.fictional:
            _require_local_session()
        _maximum_deadline()
        directory = _private_directory(args.workspace)
        source = "fictional" if args.fictional else prepare.REFERENCE["publisher_sha256"]
        with _locked_key(directory) as key:
            saved = _read_state(directory, source)
            if args.fictional:
                items = fictional_items(key)
            else:
                payload = prepare._download()
                items = review_items(payload, key)
                del payload
            state = _state_for_items(items, source, saved)
            _store_state(directory, state)
            progress = review_progress(state)
            print(f"İnceleme oturumu. A {progress['A'][0]}/{progress['A'][1]}, "
                  f"B {progress['B'][0]}/{progress['B'][1]}.", flush=True)
            launch(items, state, lambda: _store_state(directory, state))
        return 0
    except (ReviewError, prepare.PreparationError) as error:
        print(f"İnceleme durdu ({error.args[0]}).", file=sys.stderr)
    except (Exception, KeyboardInterrupt):
        print("İnceleme durdu (local_execution_failed).", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
