"""English text -> ordered list of signs plus the face the signer should make.

Owner: Person 3. Run `python backend/translate.py` for the self-check.
"""
import json
import re
from pathlib import Path

VOCAB = json.loads((Path(__file__).parent.parent / "shared" / "vocab.json").read_text())
WORD_TO_GLOSS = {w: v["gloss"] for v in VOCAB for w in v["english"]}
FILLER = {"a", "an", "the", "do", "does", "did", "is", "are", "am", "to", "for", "of", "it", "time", "please"}
WH_WORDS = {"what", "where", "who", "why", "when", "how", "which"}


def translate(text):
    words = re.findall(r"[a-z']+", text.lower())
    if any(w in WH_WORDS for w in words):
        face = "wh-question"
    elif text.strip().endswith("?"):
        face = "yes-no-question"
    else:
        face = "statement"
    # ponytail: word-for-word in English order with filler dropped. This is not ASL grammar.
    # Replace with an LLM call that returns signs in ASL order, limited to the glosses in vocab.json.
    signs = [{"gloss": WORD_TO_GLOSS.get(w, w.upper()), "known": w in WORD_TO_GLOSS} for w in words if w not in FILLER]
    return {"signs": signs, "face": face}


if __name__ == "__main__":
    r = translate("Do you want more milk?")
    assert [s["gloss"] for s in r["signs"]] == ["YOU", "WANT", "MORE", "MILK"] and r["face"] == "yes-no-question"
    assert translate("What do you want?")["face"] == "wh-question"
    assert translate("Time for bed")["signs"] == [{"gloss": "SLEEP", "known": True}]
    assert translate("I love pizza")["signs"][-1] == {"gloss": "PIZZA", "known": False}
    print("translate self-check passed")
