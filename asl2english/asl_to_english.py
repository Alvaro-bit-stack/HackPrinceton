"""Ordered recognised signs (with confidences) plus optional face and head cues -> short, warm English for the parent.

Pipeline, matching backend/translate.py: validate, language model with output validation and one retry with
feedback, deterministic fallback when the model is unavailable, out of time or invalid twice. Never crashes.
Rules enforced in code, not left to the model: low-confidence signs are always flagged and make the result
unsure; a question face makes it a question; words the child did not sign are rejected; an explicit emotion wins.
ASL-LEX 2.0 (asl2english/lexicon.json) adds every English translation of each sign, and look-alike pairs: when the
recogniser's runner-up looks like its top guess (same handshape, location, movement...), both readings are offered.
"""
import logging
import re
import time

from backend.llm import LLMUnavailable, timeout_seconds
from backend.translate import EMOTIONS, FACE_LABELS, FACE_OVERRIDE, FACES, GLOSSES, face_emotion
from asl2english import prompts
from asl2english.lexicon import LOOK_ALIKES, MEANINGS

log = logging.getLogger(__name__)

LOW_CONFIDENCE = 0.6   # same bar as the recogniser's own threshold (ml/model.npz min_confidence 0.62)
LOOK_ALIKE_FEATURES = 11  # of ASL-LEX's 16 phonological features; see check_look_alikes.py for how this was chosen
LOOK_ALIKE_MIN = 0.1      # a look-alike runner-up below this confidence is not worth raising
MAX_SIGNS = 12
MAX_ALTERNATIVES = 3   # per sign, from the recogniser's ranked list
MAX_ENGLISH = 200
MAX_NAME = 60
QUESTION_FACES = {"yes-no-question", "wh-question"}
DEFAULT_MODEL = prompts  # anything with .understand(timeout=..., **kw); tests swap in a fake

# Words English needs that carry no new meaning, plus words for reporting and hedging ("Maya might be signing milk").
FUNCTION_WORDS = set("""a an the some any is am are was were be being been do does did has have had
i me my mine you your yours he him his she her hers it its we us our they them their this that these those
to of for with and or but so if at on in up can could will would should may might shall let
your child maybe perhaps possibly probably something thing like sure think seems signing signs signed sign says said
asking asks asked telling tells want wants""".split())  # a child naming a thing is asking for it: "MILK" -> "Maya wants milk."
NEGATION = {"not", "no", "never", "nothing", "none"}
IRREGULAR = {"ate": "eat", "eaten": "eat", "drank": "drink", "drunk": "drink", "gave": "give", "given": "give",
             "slept": "sleep", "sleepy": "sleep", "mommy's": "mommy", "daddy's": "daddy", "loving": "love"}


class _OutOfTime(Exception):
    pass


def _is_num01(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= 1


def _check_sign(s, what):
    if not isinstance(s, dict):
        raise ValueError(f"{what} must be an object")
    if s.get("gloss") not in GLOSSES:
        raise ValueError(f"{what} gloss must be one of the vocabulary signs, got {s.get('gloss')!r}")
    if not _is_num01(s.get("confidence")):
        raise ValueError(f"{what} confidence must be a number from 0 to 1")


def validate(signs, face=None, head_shake=None, emotion=None, face_emotions=None, child_name=None):
    if not isinstance(signs, list) or not 1 <= len(signs) <= MAX_SIGNS:
        raise ValueError(f"signs must be a list of 1 to {MAX_SIGNS} signs")
    for i, s in enumerate(signs):
        _check_sign(s, f"sign {i + 1}")
        alts = s.get("alternatives") or []
        if not isinstance(alts, list) or len(alts) > MAX_ALTERNATIVES:
            raise ValueError(f"sign {i + 1} alternatives must be a list of at most {MAX_ALTERNATIVES}")
        for a in alts:
            _check_sign(a, f"sign {i + 1} alternative")
    validate_cues(face, head_shake, emotion, face_emotions, child_name)


def validate_cues(face=None, head_shake=None, emotion=None, face_emotions=None, child_name=None):
    if face is not None and face not in FACES:
        raise ValueError(f"face must be one of {', '.join(FACES)}")
    if head_shake is not None and not isinstance(head_shake, bool):
        raise ValueError("head_shake must be true or false")
    if emotion is not None and emotion not in EMOTIONS:
        raise ValueError(f"emotion must be one of {', '.join(EMOTIONS)}")
    if face_emotions is not None:
        if not isinstance(face_emotions, dict):
            raise ValueError("face_emotions must be an object")
        for k, v in face_emotions.items():
            if k not in FACE_LABELS:
                raise ValueError(f"unknown face emotion {k!r}")
            if not _is_num01(v):
                raise ValueError(f"face emotion score for {k!r} must be a number from 0 to 1")
    if child_name is not None and (not isinstance(child_name, str) or not child_name.strip() or len(child_name) > MAX_NAME):
        raise ValueError(f"child_name must be text of at most {MAX_NAME} characters")


def _words(text):
    """Lowercase words with contractions split: "doesn't" -> "not", "does"; "she's" -> "she"."""
    out = []
    for w in re.findall(r"[a-z]+(?:'[a-z]+)?", text.lower().replace("\u2019", "'")):
        base, _, suffix = w.partition("'")
        if suffix == "t":  # n't
            out.append("not")
            base = {"won": "will", "can": "can", "ain": "is"}.get(base, base[:-1] if base.endswith("n") else base)
        out.append(base)
    return out


def _matches(word, allowed):
    if word in allowed or IRREGULAR.get(word) in allowed:
        return True
    for cut, add in (("s", ""), ("es", ""), ("ies", "y"), ("ed", ""), ("d", ""), ("ing", ""), ("ing", "e")):
        if word.endswith(cut) and len(word) - len(cut) >= 2 and word[: -len(cut)] + add in allowed:
            return True
    return False


def invented_words(english, glosses, child_name=None, negation_ok=False):
    """Words in `english` that no signed gloss accounts for (grammar and hedging words excepted)."""
    allowed = set(FUNCTION_WORDS)
    for g in glosses:
        for meaning in MEANINGS.get(g, []):  # ASL-LEX phrases count word by word: "go to bed" allows "bed"
            allowed.update(_words(meaning))
        allowed.update(p.lower() for p in g.split("-"))
    if child_name:
        allowed.update(_words(child_name))
    if negation_ok:
        allowed.update(NEGATION)
    return sorted({w for w in _words(english) if not _matches(w, allowed)})


def validate_model_output(out, *, glosses, child_name, question_required, negation_ok, look_alike=False):
    if not isinstance(out, dict):
        return ["reply must be a JSON object"]
    problems = []
    texts = []
    english = out.get("english")
    if not isinstance(english, str) or not english.strip() or len(english) > MAX_ENGLISH:
        problems.append(f"english must be a non-empty string of at most {MAX_ENGLISH} characters")
    else:
        texts.append(english)
    alts = out.get("alternatives", [])
    if not isinstance(alts, list) or len(alts) > 2 or not all(isinstance(a, str) and a.strip() and len(a) <= MAX_ENGLISH for a in alts):
        problems.append("alternatives must be a list of at most 2 non-empty strings")
    else:
        texts.extend(alts)
    if out.get("emotion") not in EMOTIONS:
        problems.append(f"emotion must be one of {', '.join(EMOTIONS)}")
    q = out.get("is_question")
    if not isinstance(q, bool):
        problems.append("is_question must be true or false")
    elif question_required and not q:
        problems.append("the child's face marked a question, so is_question must be true and the English a question")
    elif isinstance(english, str) and english.strip() and q != english.strip().endswith("?"):
        problems.append("english must end with '?' exactly when is_question is true")
    if not _is_num01(out.get("confidence")):
        problems.append("confidence must be a number from 0 to 1")
    if not isinstance(out.get("unsure"), bool):
        problems.append("unsure must be true or false")
    extra = sorted({w for t in texts for w in invented_words(t, glosses, child_name, negation_ok)})
    if extra:
        problems.append(f"uses words the child did not sign: {extra}. Use only the signed meanings")
    if look_alike and isinstance(alts, list) and not alts:
        problems.append("a sign marked LOOKS LIKE may be the other sign: give that reading in alternatives")
    return problems


def look_alikes_of(sign):
    """Ranked alternatives that look like this sign in ASL-LEX phonology and got a real share of the confidence."""
    return [a["gloss"] for a in sign.get("alternatives") or []
            if a["gloss"] != sign["gloss"] and a["confidence"] >= LOOK_ALIKE_MIN
            and LOOK_ALIKES.get(frozenset((sign["gloss"], a["gloss"])), 0) >= LOOK_ALIKE_FEATURES]


def _signed_emotion(emotion, face_emotions):
    face = face_emotion(face_emotions)
    strong = face[0] if face and face[1] >= FACE_OVERRIDE else None
    return emotion, strong


def nothing_signed(emotion=None):
    """Result when the recogniser found no sign in the clip."""
    return {"english": "", "alternatives": [], "emotion": emotion or "neutral", "is_question": False,
            "confidence": 0.0, "unsure": True, "low_confidence_signs": [], "look_alike_signs": [], "source": "none"}


def fallback(signs, low, face=None, emotion=None, strong=None, looks=()):
    """Deterministic: the glosses as plain lowercase words, low-confidence ones hedged, look-alikes offered. Always unsure."""
    def word(s):
        w = ("maybe " if s["gloss"] in low else "") + s["gloss"].lower().replace("-", " ")
        others = look_alikes_of(s)
        return w + (f" (or {' or '.join(o.lower().replace('-', ' ') for o in others)})" if others else "")
    is_question = face in QUESTION_FACES or signs[-1]["gloss"] == "WHAT"
    mean = sum(s["confidence"] for s in signs) / len(signs)
    return {"english": " ".join(word(s) for s in signs) + ("?" if is_question else ""), "alternatives": [],
            "emotion": emotion or strong or "neutral", "is_question": is_question,
            "confidence": round(0.3 * mean, 2), "unsure": True, "low_confidence_signs": low,
            "look_alike_signs": list(looks), "source": "fallback"}


def understand(signs, face=None, head_shake=None, emotion=None, face_emotions=None, child_name=None, *,
               model=None, budget_seconds=15):
    """signs: [{"gloss", "confidence", "alternatives"?: [{"gloss", "confidence"}]}] in signing order.
    Returns {"english", "alternatives", "emotion", "is_question", "confidence", "unsure", "low_confidence_signs",
    "look_alike_signs": [{"gloss", "could_be": [...]}], "source"}.
    Raises ValueError on bad input (the route turns it into HTTP 422)."""
    validate(signs, face, head_shake, emotion, face_emotions, child_name)
    model = model or DEFAULT_MODEL
    child_name = child_name.strip() if child_name else None
    low = list(dict.fromkeys(s["gloss"] for s in signs if s["confidence"] < LOW_CONFIDENCE))
    emotion, strong = _signed_emotion(emotion, face_emotions)
    glosses = {s["gloss"] for s in signs} | {a["gloss"] for s in signs for a in s.get("alternatives") or []}
    negation_ok = bool(head_shake) or "NO" in glosses
    question_required = face in QUESTION_FACES
    shown = [dict(s, low=s["gloss"] in low, look_alike=look_alikes_of(s)) for s in signs]
    looks = [{"gloss": s["gloss"], "could_be": s["look_alike"]} for s in shown if s["look_alike"]]
    start = time.monotonic()

    def call(previous):
        remaining = budget_seconds - (time.monotonic() - start)
        if remaining < 1:
            raise _OutOfTime
        return model.understand(timeout=min(timeout_seconds(), remaining), signs=shown,
                                meanings={g: MEANINGS[g] for g in sorted(glosses)}, child_name=child_name, face=face,
                                head_shake=head_shake, emotion=emotion, face_emotions=face_emotions, previous=previous)

    out, previous = None, None
    try:
        for _ in range(2):  # one retry, telling the model what was wrong
            reply = call(previous)
            problems = validate_model_output(reply, glosses=glosses, child_name=child_name,
                                             question_required=question_required, negation_ok=negation_ok,
                                             look_alike=bool(looks))
            if not problems:
                out = reply
                break
            previous = {"reply": reply if isinstance(reply, dict) else None, "problem": "; ".join(problems)}
    except (_OutOfTime, LLMUnavailable) as e:
        log.warning("understanding degraded (%s): %s", type(e).__name__, e)  # names the failure only; never the input
    if out is None:
        if previous:
            log.warning("model output invalid twice; using fallback")
        return fallback(signs, low, face, emotion, strong, looks)

    alternatives = [a.strip() for a in out.get("alternatives", [])][:2]
    emo = emotion or (strong if strong and out["emotion"] == "neutral" else out["emotion"])
    mean = sum(s["confidence"] for s in signs) / len(signs)
    return {"english": out["english"].strip(), "alternatives": alternatives, "emotion": emo,
            "is_question": out["is_question"], "confidence": round(out["confidence"] * mean, 2),
            "unsure": out["unsure"] or bool(alternatives) or bool(low) or bool(looks), "low_confidence_signs": low,
            "look_alike_signs": looks, "source": "model"}
