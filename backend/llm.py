"""Language-model wrapper and prompts for translate.py. SDKs are imported lazily so the backend runs without them."""
import json
import os
import re
from pathlib import Path

from backend import asl_lex

ROOT = Path(__file__).parent.parent
DEFAULT_MODELS = {"anthropic": "claude-sonnet-5-5"}
KEY_VARS = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}


class LLMUnavailable(Exception):
    """No usable model reply; callers fall back to the offline stub."""


def _load_env():
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(ROOT / ".env")  # does not override variables already set


def timeout_seconds():
    try:
        return float(os.environ.get("LLM_TIMEOUT_SECONDS") or 20)
    except ValueError:
        return 20.0


def extract_json(text):
    """First {...} object in the reply; tolerates ```json fences and surrounding prose."""
    start = text.find("{")
    if start < 0:
        raise LLMUnavailable("reply had no JSON object")
    try:
        obj, _ = json.JSONDecoder().raw_decode(text[start:])
    except ValueError:
        raise LLMUnavailable("reply was not valid JSON") from None
    if not isinstance(obj, dict):
        raise LLMUnavailable("reply JSON was not an object")
    return obj


def _user_content(provider, user, images):
    """images: validated base64 JPEGs, in the order the prompt text describes them.
    ponytail: anthropic and openai only; add a branch here for gemini (inline_data parts) when we switch."""
    if not images:
        return user
    if provider == "anthropic":
        return [*({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b}} for b in images),
                {"type": "text", "text": user}]
    return [{"type": "text", "text": user},
            *({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b}", "detail": "low"}} for b in images)]


def call_json(system, user, timeout, images=None):
    _load_env()
    provider = (os.environ.get("LLM_PROVIDER") or "anthropic").lower()
    if provider not in KEY_VARS:
        raise LLMUnavailable(f"unknown LLM_PROVIDER {provider!r}")
    key = os.environ.get(KEY_VARS[provider])
    if not key:
        raise LLMUnavailable(f"{KEY_VARS[provider]} is not set")
    model = os.environ.get("LLM_MODEL") or DEFAULT_MODELS.get(provider)
    if not model:
        raise LLMUnavailable("LLM_MODEL is required for openai")
    try:
        if provider == "anthropic":
            import anthropic
            client = anthropic.Anthropic(api_key=key, timeout=timeout, max_retries=0)
            r = client.messages.create(model=model, max_tokens=1024, system=system,
                                       messages=[{"role": "user", "content": _user_content(provider, user, images)}])
            text = "".join(b.text for b in r.content if getattr(b, "type", "") == "text")
        else:
            import openai
            client = openai.OpenAI(api_key=key, timeout=timeout, max_retries=0)
            r = client.chat.completions.create(model=model, messages=[
                {"role": "system", "content": system}, {"role": "user", "content": _user_content(provider, user, images)}])
            text = r.choices[0].message.content or ""
    except ImportError:
        raise LLMUnavailable(f"{provider} SDK is not installed") from None
    except Exception as e:  # the exception text could echo request details, so report only its type
        raise LLMUnavailable(f"{provider} request failed ({type(e).__name__})") from None
    return extract_json(text)


GRAMMAR_NOTES = """ASL grammar notes (a simplification, pending review by a fluent signer):
- Drop articles and forms of "be".
- Time first, then topic before comment.
- A wh-word usually goes at the end of the sentence.
- Yes/no questions use raised eyebrows; negation uses a headshake.
- If a word has no sign, rephrase using the available signs.
- Mark names and words with no sign as FS:WORD (fingerspelling)."""

TRANSLATE_SYSTEM = f"""You translate a hearing parent's English into ASL for their young deaf child.
Use only the glosses in the allowed list below, plus FS:WORD for names and words with no sign.
Never simplify for the child's age: sign the full meaning with the richest allowed signs, because a young child learns language by seeing complete, rich signing.

{GRAMMAR_NOTES}

Tone rules:
- Infer the emotion from what the parent intends, not only from feeling words. A warning, rule or consequence is firm: "angry" with low-to-medium intensity. Praise is "happy". "Be careful" or danger is "worried". Bad news or comfort is "sad". Amazement is "surprised". Use "neutral" only for plain information or routine requests.
- Intensity is 0 to 1, how strong the feeling is (sign size and speed): 0.2 calm, 0.5 clear, 0.8 or more very strong.

Reply with one JSON object and nothing else:
{{"signs": [gloss or "FS:WORD", ...], "face": "statement" | "yes-no-question" | "wh-question", "emotion": "neutral" | "happy" | "sad" | "angry" | "surprised" | "worried", "intensity": 0.0-1.0, "tone_reason": "<one short line: which signals decided the emotion and intensity>", "meaning": "<one short line>"}}"""


def dictionary_notes(sentence, vocab):
    """ASL-LEX lines for sentence words outside the allowed list: which allowed gloss is the same sign, or that it has no clip yet."""
    known = {w for v in vocab for w in v["english"]}
    gloss_of = {v["asl_lex"]: v["gloss"] for v in vocab if v.get("asl_lex")}
    notes = []
    for w in dict.fromkeys(re.findall(r"[a-z]+", sentence.lower())):
        entry = None if w in known else asl_lex.has_sign(w)
        if entry:
            g = gloss_of.get(entry)
            notes.append(f"{w}: ASL-LEX sign {entry!r}, " + (f"same sign as {g}" if g else "not animated yet"))
    return notes


def translate_prompt(sentence, vocab, face_emotions=None, emotion=None, meaning_hint=None,
                     examples=(), corrections=(), previous=None, loudness=None, pitch=None,
                     face_frames=None, face_neutral=None):
    parts = ["Allowed glosses (gloss: English words):\n" + "\n".join(f"{v['gloss']}: {', '.join(v['english'])}" for v in vocab)]
    if notes := dictionary_notes(sentence, vocab):
        parts.append("ASL-LEX dictionary entries for other words in this sentence. Use the allowed gloss named; "
                     "for a sign not animated yet, rephrase with allowed glosses, or fingerspell it if the meaning needs it:\n" + "\n".join(notes))
    if face_emotions:
        parts.append(f"The parent's face emotion scores (0 to 1): {json.dumps(face_emotions)}. "
                     "The words decide the emotion when they carry intent. The face decides when the words are ambiguous "
                     '(a sentence that could be praise or a scolding). A face that disagrees with clear words (a parent smiling while warning, '
                     "to soften it) does not change the emotion but can lower the intensity.")
    if face_frames:
        first = 2 if face_neutral else 1
        parts.append("Photos of the parent's face are attached. " +
                     ("Image 1 is their relaxed, neutral face, for reference. " if face_neutral else "") +
                     f"Images {first} to {first + len(face_frames) - 1} are the strongest moments while they said this sentence. "
                     "Read their emotion from how the face changes" + (" compared with the neutral photo" if face_neutral else "") + ": "
                     "lowered brows and pressed lips mean angry or firm; inner brows raised with mouth corners down mean sad; "
                     "inner brows raised with wide or tense eyes mean worried; a smile with raised cheeks means happy; "
                     "brows up with eyes wide open means surprised. When the words are neutral or ambiguous, the face decides "
                     "the emotion, even when the expression is subtle. When the words clearly carry intent, the words decide "
                     "which emotion and the face sets the intensity. Never answer 'neutral' when the face clearly shows an emotion. "
                     "Say what you saw in tone_reason.")
    if loudness is not None:
        parts.append(f"The parent's voice loudness relative to their normal: {loudness:+.2f} (-1 much quieter, 0 normal, +1 much louder). "
                     "Loudness tells how strong the feeling is, not which feeling.")
    if pitch is not None:
        parts.append(f"The parent's voice pitch relative to their normal: {pitch:+.2f} (-1 much lower, 0 normal, +1 much higher). "
                     "Raised pitch suggests a stronger, more agitated or excited feeling; lower, flat pitch suggests calm or sadness. "
                     "Like loudness, it mainly sets intensity; the words and face decide which feeling.")
    if emotion:
        parts.append(f'The emotion is "{emotion}". Use it as is in the "emotion" field.')
    if meaning_hint:
        parts.append(f'The parent says they meant: "{meaning_hint}". Follow it.')
    if examples:
        parts.append("Example translations:\n" + "\n".join(
            f"{e['english']!r} -> {json.dumps(e['signs'])}" + (f" face={e['face']}" if e.get("face") else "") for e in examples[:4]))
    if corrections:
        parts.append("Recent corrections from the parent:\n" + "\n".join(json.dumps(c) for c in corrections[-10:]))
    if previous:
        parts.append(f"Your previous attempt was {json.dumps(previous.get('signs'))} and it was rejected: {previous.get('problem')}. Fix it.")
    parts.append(f"Sentence: {sentence}")
    return TRANSLATE_SYSTEM, "\n\n".join(parts)


BACK_SYSTEM = """You check an ASL translation. Given the signs, the face and the emotion, write the English they express,
then judge whether it keeps the meaning of the original sentence.
Reply with one JSON object and nothing else: {"english": str, "same_meaning": bool, "problem": str}"""


def back_translate_prompt(text, signs, face, emotion):
    return BACK_SYSTEM, f"Original sentence: {text}\nSigns: {json.dumps(signs)}\nFace: {face}\nEmotion: {emotion}"


def translate(timeout, **kw):
    images = ([kw["face_neutral"]] if kw.get("face_neutral") else []) + list(kw.get("face_frames") or [])
    if not kw.get("face_frames"):
        images = []  # a neutral photo alone says nothing about this sentence
    return call_json(*translate_prompt(**kw), timeout, images=images)


def back_translate(timeout, **kw):
    return call_json(*back_translate_prompt(**kw), timeout)
