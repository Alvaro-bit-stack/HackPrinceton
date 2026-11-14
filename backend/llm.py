"""Language-model wrapper and prompts for translate.py. SDKs are imported lazily so the backend runs without them."""
import json
import os
from pathlib import Path

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


def call_json(system, user, timeout):
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
                                       messages=[{"role": "user", "content": user}])
            text = "".join(b.text for b in r.content if getattr(b, "type", "") == "text")
        else:
            import openai
            client = openai.OpenAI(api_key=key, timeout=timeout, max_retries=0)
            r = client.chat.completions.create(model=model, messages=[
                {"role": "system", "content": system}, {"role": "user", "content": user}])
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

{GRAMMAR_NOTES}

Reply with one JSON object and nothing else:
{{"signs": [gloss or "FS:WORD", ...], "face": "statement" | "yes-no-question" | "wh-question", "emotion": "neutral" | "happy" | "sad" | "angry" | "surprised" | "worried", "meaning": "<one short line>"}}"""


def translate_prompt(sentence, vocab, face_emotions=None, emotion=None, meaning_hint=None,
                     examples=(), corrections=(), previous=None):
    parts = ["Allowed glosses (gloss: English words):\n" + "\n".join(f"{v['gloss']}: {', '.join(v['english'])}" for v in vocab)]
    if face_emotions:
        parts.append(f"The parent's face emotion scores (0 to 1): {json.dumps(face_emotions)}. "
                     "The words outrank the face when they disagree.")
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
    return call_json(*translate_prompt(**kw), timeout)


def back_translate(timeout, **kw):
    return call_json(*back_translate_prompt(**kw), timeout)
