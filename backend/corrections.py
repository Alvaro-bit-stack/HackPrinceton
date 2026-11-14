"""Parent corrections, stored as a JSON list (single demo family). Git-ignored."""
import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

from backend.translate import EMOTIONS, MAX_MEANING, MAX_TEXT

PATH = Path(__file__).parent / "data" / "corrections.json"
_lock = threading.Lock()


def load_corrections(path=PATH):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    # a hand-edited file must not crash /translate; skip entries that are not correction objects
    return [c for c in data if isinstance(c, dict) and isinstance(c.get("text"), str)] if isinstance(data, list) else []


def save_correction(text, meaning=None, emotion=None, path=PATH):
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT:
        raise ValueError(f"text must be 1 to {MAX_TEXT} characters")
    if isinstance(meaning, str) and not meaning.strip():
        meaning = None  # an empty box means "meaning unchanged"
    if meaning is not None and (not isinstance(meaning, str) or not meaning.strip() or len(meaning) > MAX_MEANING):
        raise ValueError(f"meaning must be 1 to {MAX_MEANING} characters")
    if emotion is not None and emotion not in EMOTIONS:
        raise ValueError(f"emotion must be one of {', '.join(EMOTIONS)}")
    if meaning is None and emotion is None:
        raise ValueError("give a meaning, an emotion or both")
    path = Path(path)
    entry = {"text": text, "meaning": meaning, "emotion": emotion,
             "saved_at": datetime.now(timezone.utc).isoformat()}
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = load_corrections(path) + [entry]
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)  # readers never see a half-written file
    return entry
