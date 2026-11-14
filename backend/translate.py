"""English text (plus tone and face scores) -> ordered list of signs, grammar face, emotion and meaning.

Owner: Person 3. Run `python -m backend.tests` for the tests.

Pipeline: validate, phrase bank (no model), language model with validation and one retry,
back-translate self-check with one re-translate, word-for-word fallback when the model is unavailable.
"""
import json
import logging
import re
import time
from pathlib import Path

from backend import llm
from backend.llm import LLMUnavailable

log = logging.getLogger(__name__)

SHARED = Path(__file__).parent.parent / "shared"
VOCAB = json.loads((SHARED / "vocab.json").read_text())
WORD_TO_GLOSS = {w: v["gloss"] for v in VOCAB for w in v["english"]}
GLOSSES = {v["gloss"] for v in VOCAB}
FILLER = {"a", "an", "the", "do", "does", "did", "is", "are", "am", "to", "for", "of", "it", "time", "please"}
WH_WORDS = {"what", "where", "who", "why", "when", "how", "which"}
EMOTIONS = ("neutral", "happy", "sad", "angry", "surprised", "worried")
FACES = ("statement", "yes-no-question", "wh-question")
FACE_LABELS = ("neutral", "happy", "sad", "angry", "fearful", "disgusted", "surprised")
FACE_TO_EMOTION = {"fearful": "worried", "disgusted": "angry", **{e: e for e in FACE_LABELS if e not in ("fearful", "disgusted")}}
MAX_TEXT = 300
MAX_MEANING = 300
FACE_OVERRIDE = 0.6
FS_RE = re.compile(r"FS:[A-Za-z0-9'-]+")
EMOTION_WORDS = {"happy": {"love", "yay", "great", "good", "proud"}, "sad": {"sad", "sorry", "miss"},
                 "angry": {"stop", "angry", "mad"}, "surprised": {"wow", "whoa"},
                 "worried": {"careful", "hurt", "scared", "ouch"}}


def _key(text):
    return " ".join(re.findall(r"[a-z']+", text.lower()))


def load_phrases(path=SHARED / "phrases.json"):
    """Human-checked translations: [{"english", "signs": [...], "face"?, "emotion"?, "meaning"?}]."""
    return {_key(p["english"]): p for p in json.loads(path.read_text())}


PHRASES = load_phrases()


def guess_emotion(text):
    # ponytail: keyword match on the words only, so it cannot hear tone of voice.
    # Replace with the language model's reading of the sentence, or a speech-emotion model on the audio.
    words = set(re.findall(r"[a-z']+", text.lower()))
    return next((e for e, cues in EMOTION_WORDS.items() if words & cues), "neutral")


def grammar_face(text):
    words = re.findall(r"[a-z']+", text.lower())
    if any(w in WH_WORDS for w in words):
        return "wh-question"
    return "yes-no-question" if text.strip().endswith("?") else "statement"


class _OutOfTime(Exception):
    pass


def validate(text, emotion, face_emotions, meaning_hint):
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text must be a non-empty string")
    if len(text) > MAX_TEXT:
        raise ValueError(f"text must be at most {MAX_TEXT} characters")
    if emotion is not None and emotion not in EMOTIONS:
        raise ValueError(f"emotion must be one of {', '.join(EMOTIONS)}")
    if face_emotions is not None:
        if not isinstance(face_emotions, dict):
            raise ValueError("face_emotions must be an object")
        for k, v in face_emotions.items():
            if k not in FACE_LABELS:
                raise ValueError(f"unknown face emotion {k!r}")
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 1:
                raise ValueError(f"face emotion score for {k!r} must be a number from 0 to 1")
    if meaning_hint is not None and (not isinstance(meaning_hint, str) or len(meaning_hint) > MAX_MEANING):
        raise ValueError(f"meaning_hint must be a string of at most {MAX_MEANING} characters")


def face_emotion(face_emotions):
    """(emotion, score) of the top mapped face emotion, or None when absent or neutral (neutral never overrides)."""
    totals = {}
    for k, v in (face_emotions or {}).items():
        totals[FACE_TO_EMOTION[k]] = totals.get(FACE_TO_EMOTION[k], 0) + v
    if not totals:
        return None
    top = max(totals, key=totals.get)
    return None if top == "neutral" else (top, totals[top])


def validate_model_output(out):
    if not isinstance(out, dict):
        return ["reply must be a JSON object"]
    problems = []
    signs = out.get("signs")
    if not isinstance(signs, list) or not signs or not all(isinstance(s, str) for s in signs):
        problems.append("signs must be a non-empty list of strings")
    else:
        bad = [s for s in signs if s not in GLOSSES and not FS_RE.fullmatch(s)]
        if bad:
            problems.append(f"not allowed glosses (use a listed gloss or FS:WORD): {bad}")
    if out.get("face") not in FACES:
        problems.append(f"face must be one of {', '.join(FACES)}")
    if out.get("emotion") not in EMOTIONS:
        problems.append(f"emotion must be one of {', '.join(EMOTIONS)}")
    m = out.get("meaning")
    if not isinstance(m, str) or not m.strip() or len(m) > MAX_MEANING:
        problems.append(f"meaning must be a non-empty string of at most {MAX_MEANING} characters")
    return problems


def _signs_out(signs):
    return [{"gloss": s[3:].upper(), "known": False} if s.startswith("FS:") else {"gloss": s, "known": s in GLOSSES} for s in signs]


def _nearest(text, phrases, n=4):
    words = set(_key(text).split())
    scored = []
    for p in phrases.values():
        pw = set(_key(p["english"]).split())
        if words | pw and words & pw:
            scored.append((len(words & pw) / len(words | pw), p))
    return [p for _, p in sorted(scored, key=lambda x: -x[0])[:n]]


def translate(text, emotion=None, face_emotions=None, meaning_hint=None, *, phrases=None, model=None,
              corrections=None, budget_seconds=45, offline=False):
    """Returns {"signs": [{gloss, known}], "face", "emotion", "meaning", "source", "unsure"}.

    offline=True never calls the model (phrase bank, then fallback); used when serving books.
    """
    validate(text, emotion, face_emotions, meaning_hint)
    phrases = PHRASES if phrases is None else phrases
    model = llm if model is None else model
    key = _key(text)
    # saved corrections for this exact sentence act like the caller's own input; latest meaning and latest emotion each win
    fixes = [c for c in reversed(corrections or []) if _key(c.get("text") or "") == key]
    emotion = emotion or next((c["emotion"] for c in fixes if c.get("emotion") in EMOTIONS), None)
    meaning_hint = meaning_hint or next((c["meaning"] for c in fixes
                                         if isinstance(c.get("meaning"), str) and 0 < len(c["meaning"]) <= MAX_MEANING), None)
    face = face_emotion(face_emotions)
    strong = face[0] if face and face[1] >= FACE_OVERRIDE else None

    def result(signs, face_kind, emo, meaning, source, unsure):
        return {"signs": _signs_out(signs), "face": face_kind, "emotion": emo, "meaning": meaning,
                "source": source, "unsure": unsure}

    hit = phrases.get(key)
    if hit and not meaning_hint:
        emo = emotion or strong or hit.get("emotion") or guess_emotion(text)
        return result(hit["signs"], hit.get("face") or grammar_face(text), emo, hit.get("meaning") or text, "phrase-bank", False)

    def fallback():
        # ponytail: word-for-word in English order with filler dropped. This is not ASL grammar.
        words = [w for w in re.findall(r"[a-z']+", text.lower()) if w not in FILLER]
        r = result([], grammar_face(text), emotion or strong or guess_emotion(text), text, "fallback", True)
        r["signs"] = [{"gloss": WORD_TO_GLOSS.get(w, w.upper()), "known": w in WORD_TO_GLOSS} for w in words]
        return r

    if offline:
        return fallback()

    start = time.monotonic()

    def call(fn, **kw):
        remaining = budget_seconds - (time.monotonic() - start)
        if remaining < 1:
            raise _OutOfTime
        return fn(timeout=min(llm.timeout_seconds(), remaining), **kw)

    def generate(previous=None):
        for _ in range(2):  # one retry, telling the model what was wrong
            out = call(model.translate, sentence=text, face_emotions=face_emotions, emotion=emotion,
                       meaning_hint=meaning_hint, vocab=VOCAB, examples=_nearest(text, phrases),
                       corrections=(corrections or [])[-10:], previous=previous)
            problems = validate_model_output(out)
            if not problems:
                return dict(out)  # copy, since the emotion may be overwritten below
            previous = {"signs": out.get("signs") if isinstance(out, dict) else None, "problem": "; ".join(problems)}
        return None

    def passes(cand):
        r = call(model.back_translate, text=text, signs=cand["signs"], face=cand["face"], emotion=cand["emotion"])
        ok = isinstance(r, dict) and r.get("same_meaning") is True
        return ok, (str(r.get("problem")) if isinstance(r, dict) else "malformed check reply")

    best = None
    try:
        best = generate()
        if best is None:
            log.warning("model output invalid twice; using fallback")
            return fallback()
        best["emotion"] = emotion or best["emotion"]  # an explicit emotion is used as is
        ok, problem = passes(best)
        if not ok:
            retry = generate({"signs": best["signs"], "problem": problem or "the meaning changed"})
            if retry:
                best = retry
                best["emotion"] = emotion or best["emotion"]
                ok, _ = passes(best)
        unsure = not ok
    except (_OutOfTime, LLMUnavailable) as e:  # keep a valid candidate already in hand, marked unsure
        log.warning("translation degraded (%s): %s", type(e).__name__, e)  # never contains the API key
        if best is None:
            return fallback()
        unsure = True
    return result(best["signs"], best["face"], best["emotion"], best["meaning"], "model", unsure or bool(meaning_hint and hit))


if __name__ == "__main__":
    from backend.tests import run
    run()
