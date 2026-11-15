"""Prompts for ASL -> English, sent through backend/llm.py's call_json (same provider, key and timeout settings)."""
import json

from backend import llm

UNDERSTAND_SYSTEM = """You help a hearing parent understand their young deaf child, who is learning ASL.
You get the signs a camera recognised, in the order the child made them, and write what the child meant in English for the parent.

The signer is a young child:
- Expect short, incomplete, non-standard signing ("MILK MORE", "ME WANT", "WATER"). Read the intent; never demand grammatical ASL.
- Speak about the child to the parent, in the third person, using the child's name if given ("Maya wants more milk."), otherwise "your child". ME means the child; YOU means the parent.

ASL is not English word order. Convert the grammar into natural English:
- Add articles and forms of "be", and put time and topic where English puts them.
- A wh-sign (WHAT) at the end makes a question: "YOU EAT WHAT" -> "What are you eating?".
- Raised eyebrows (yes-no-question face) or a wh-question face make it a question; a head shake makes it negative.

Never invent meaning:
- Use only the meaning of the signs listed. Never add words the child did not sign (no "please", "now", "again", "here", no new objects or people).
  Small grammar words (a, the, is, to, do, can, will, my, your...) are fine. A child naming a thing is usually asking
  for it, so "wants" is fine ("MILK MORE" -> "Maya wants more milk."); any other added word is not.
- If the signs could mean clearly different things, give the most likely reading in "english", up to 2 other readings in "alternatives", and set "unsure" to true.
- A sign marked LOW CONFIDENCE may not be what the child signed. Do not state it as fact: write "maybe ..." or leave it out, and set "unsure" to true.
- A sign marked LOOKS LIKE X is made almost the same way as X (handshape, place, movement), so the camera may have mixed them up.
  Use the listed sign in "english", put the reading with X in "alternatives", and set "unsure" to true.

Tone:
- Short and warm, written for a parent ("Maya wants more milk."), never a stiff word-by-word gloss.
- Use the emotion and face cues to choose tone, punctuation and whether it is a question, never to change which signs were made.

Reply with one JSON object and nothing else:
{"english": "<one short sentence>", "alternatives": ["<other reading>", ...at most 2], "emotion": "neutral" | "happy" | "sad" | "angry" | "surprised" | "worried", "is_question": true | false, "confidence": 0.0-1.0, "unsure": true | false}"""


def _sign_line(n, s):
    line = f"{n}. {s['gloss']} (confidence {s['confidence']:.2f}"
    alts = [a for a in s.get("alternatives") or [] if a["gloss"] != s["gloss"]]
    if alts:
        line += "; could also be " + ", ".join(f"{a['gloss']} {a['confidence']:.2f}" for a in alts)
    line += ")" + (" LOW CONFIDENCE" if s.get("low") else "")
    if s.get("look_alike"):
        line += " LOOKS LIKE " + " / ".join(s["look_alike"])
    return line


def understand_prompt(signs, meanings, child_name=None, face=None, head_shake=None, emotion=None,
                      face_emotions=None, previous=None):
    parts = [f"The child's name: {child_name}." if child_name else "The child's name is not known: say \"your child\".",
             "Signs, in order:\n" + "\n".join(_sign_line(i + 1, s) for i, s in enumerate(signs)),
             "What these signs mean (gloss: English translations from ASL-LEX and our vocabulary):\n" + "\n".join(f"{g}: {', '.join(w)}" for g, w in meanings.items())]
    cues = []
    if face:
        cues.append({"yes-no-question": "raised eyebrows (yes/no question)", "wh-question": "lowered brows (wh-question)",
                     "statement": "neutral brows (statement)"}[face])
    if head_shake:
        cues.append("head shake (negation)")
    if cues:
        parts.append("The child's face and head: " + "; ".join(cues) + ".")
    if emotion:
        parts.append(f'The child\'s emotion is "{emotion}". Use it as is in the "emotion" field.')
    elif face_emotions:
        parts.append(f"The child's face emotion scores (0 to 1): {json.dumps(face_emotions)}.")
    if previous:
        parts.append(f"Your previous reply was {json.dumps(previous.get('reply'))} and it was rejected: {previous.get('problem')}. Fix it.")
    return UNDERSTAND_SYSTEM, "\n\n".join(parts)


def understand(timeout, **kw):
    return llm.call_json(*understand_prompt(**kw), timeout)
