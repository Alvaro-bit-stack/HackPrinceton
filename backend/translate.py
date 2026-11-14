"""English text (plus the speaker's emotion) -> ordered list of signs, grammar face and emotion.

Owner: Person 3. Run `python backend/translate.py` for the self-check.

Pipeline, in order:
  1. Emotion: use the one sent with the request, otherwise guess it from the text.
  2. Phrase bank: if a human-checked translation exists for this sentence, use it as is.
  3. Language model: translate into ASL order using only signs in vocab.json.   (to build)
  4. Self-check: turn the signs back into English and compare the meaning.      (to build)
"""
import json
import re
from pathlib import Path

SHARED = Path(__file__).parent.parent / "shared"
VOCAB = json.loads((SHARED / "vocab.json").read_text())
WORD_TO_GLOSS = {w: v["gloss"] for v in VOCAB for w in v["english"]}
GLOSSES = {v["gloss"] for v in VOCAB}
FILLER = {"a", "an", "the", "do", "does", "did", "is", "are", "am", "to", "for", "of", "it", "time", "please"}
WH_WORDS = {"what", "where", "who", "why", "when", "how", "which"}
EMOTIONS = ("neutral", "happy", "sad", "angry", "surprised", "worried")
EMOTION_WORDS = {"happy": {"love", "yay", "great", "good", "proud"}, "sad": {"sad", "sorry", "miss"},
                 "angry": {"stop", "angry", "mad"}, "surprised": {"wow", "whoa"},
                 "worried": {"careful", "hurt", "scared", "ouch"}}


def _key(text):
    return " ".join(re.findall(r"[a-z']+", text.lower()))


def load_phrases(path=SHARED / "phrases.json"):
    """Human-checked translations: [{"english": "...", "signs": ["GLOSS", ...], "face": "..."}]."""
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


def translate(text, emotion=None, phrases=None):
    """Returns {"signs": [{gloss, known}], "face": ..., "emotion": ..., "checked": bool}."""
    phrases = PHRASES if phrases is None else phrases
    emotion = emotion if emotion in EMOTIONS else guess_emotion(text)
    hit = phrases.get(_key(text))
    if hit:
        return {"signs": [{"gloss": g, "known": g in GLOSSES} for g in hit["signs"]],
                "face": hit.get("face") or grammar_face(text), "emotion": emotion, "checked": True}
    # ponytail: word-for-word in English order with filler dropped. This is not ASL grammar.
    # Replace with steps 3 and 4 above; keep the return shape.
    words = re.findall(r"[a-z']+", text.lower())
    signs = [{"gloss": WORD_TO_GLOSS.get(w, w.upper()), "known": w in WORD_TO_GLOSS} for w in words if w not in FILLER]
    return {"signs": signs, "face": grammar_face(text), "emotion": emotion, "checked": False}


if __name__ == "__main__":
    r = translate("Do you want more milk?")
    assert [s["gloss"] for s in r["signs"]] == ["YOU", "WANT", "MORE", "MILK"] and r["face"] == "yes-no-question"
    assert r["emotion"] == "neutral" and r["checked"] is False
    assert translate("What do you want?")["face"] == "wh-question"
    assert translate("Time for bed")["signs"] == [{"gloss": "SLEEP", "known": True}]
    assert translate("I love pizza")["signs"][-1] == {"gloss": "PIZZA", "known": False}
    assert translate("I love you")["emotion"] == "happy"
    assert translate("I love you", emotion="sad")["emotion"] == "sad"          # the caller's tone wins
    assert translate("Hello", emotion="not-a-real-emotion")["emotion"] == "neutral"
    bank = {_key("Do you want more milk?"): {"english": "x", "signs": ["MILK", "MORE", "YOU", "WANT"]}}
    r = translate("do you want MORE milk", phrases=bank)                       # punctuation and case ignored
    assert [s["gloss"] for s in r["signs"]] == ["MILK", "MORE", "YOU", "WANT"] and r["checked"] is True
    assert load_phrases() == {} or all("signs" in p for p in load_phrases().values())
    print("translate self-check passed")
