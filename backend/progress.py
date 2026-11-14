"""Which signs the family has used, and which early-childhood signs they haven't yet (catch-up, never a cap)."""
import json
import os
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend import asl_lex
from backend.translate import VOCAB

USAGE_PATH = Path(__file__).parent / "data" / "usage.json"
_lock = threading.Lock()
CAP = 20


def _load(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    # a hand-edited file must not crash /translate
    return [dict(u, signs=[g for g in u["signs"] if isinstance(g, str)]) for u in data
            if isinstance(u, dict) and isinstance(u.get("signs"), list)] if isinstance(data, list) else []


def log_usage(glosses, speaker=None, now=None, path=USAGE_PATH):
    if not glosses:
        return
    path = Path(path)
    entry = {"t": (now or datetime.now(timezone.utc)).isoformat(), "speaker": speaker, "signs": list(glosses)}
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = _load(path) + [entry]
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, path)  # readers never see a half-written file


def new_signs(glosses, path=USAGE_PATH):
    seen = {g for u in _load(path) for g in u["signs"]}
    return [g for g in dict.fromkeys(glosses) if g not in seen]


def progress(child_age_months=None, speaker=None, now=None, path=USAGE_PATH, lex=None, vocab=None):
    now = now or datetime.now(timezone.utc)
    # the raw entry list, not asl_lex.load(): that word index hides entries whose words an earlier entry took (e.g. water)
    lex_entries = lex.values() if lex is not None else (
        json.loads(asl_lex.LEX.read_text(encoding="utf-8"))["signs"] if asl_lex.LEX.exists() else [])
    vocab = VOCAB if vocab is None else vocab
    usage = [u for u in _load(path) if speaker is None or u.get("speaker") == speaker]
    used = list(dict.fromkeys(g for u in usage for g in u["signs"]))

    def window(start, end):
        out = set()
        for u in usage:
            try:
                if start <= datetime.fromisoformat(u["t"]) < end:  # a naive time raises TypeError here
                    out.update(u["signs"])
            except (KeyError, TypeError, ValueError):
                continue
        return len(out)

    week = timedelta(days=7)
    gloss_of = {v["asl_lex"]: v["gloss"] for v in vocab if v.get("asl_lex")}
    used_entries = {v["asl_lex"] for v in vocab if v["gloss"] in used and v.get("asl_lex")}
    entries = {e["entry"]: e for e in lex_entries}.values()
    todo = [e for e in entries if e.get("child_vocab") and e.get("age_learned_months") is not None
            and (child_age_months is None or e["age_learned_months"] <= child_age_months)
            and e["entry"] not in used_entries]
    todo.sort(key=lambda e: (e["age_learned_months"], -(e.get("frequency") or 0), -(e["iconicity"] if e.get("iconicity") is not None else -99)))
    in_app, not_yet = [], []
    for e in todo:
        item = {"entry": e["entry"], "english": e["english"], "age_learned_months": e["age_learned_months"]}
        if e["entry"] in gloss_of:
            in_app.append({"gloss": gloss_of[e["entry"]], **item})
        else:
            not_yet.append(item)
    return {"child_age_months": child_age_months, "speaker": speaker, "signs_used": used,
            "variety": {"this_week": window(now - week, now + timedelta(seconds=1)), "last_week": window(now - 2 * week, now - week)},
            "catch_up": {"in_app": in_app[:CAP], "not_yet_animated": not_yet[:CAP]}}
