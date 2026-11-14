"""Storybook mode: fixed texts, translated sentence by sentence. Owner: Person 3.

Add a book by dropping a .txt file in shared/books/: first line is the title, then one sentence per line.
Use only original or public-domain text.
Build the model translations offline (a reviewer can check them), then commit the cache:
  python -m backend.books build <id>      or      python -m backend.books build --all
GET never calls the model and never writes files.
"""
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

from backend.translate import PHRASES, _key, translate

BOOK_DIR = Path(__file__).parent.parent / "shared" / "books"


def load_books(book_dir=BOOK_DIR):
    books = {}
    for f in sorted(Path(book_dir).glob("*.txt")):
        raw = f.read_text(encoding="utf-8")
        lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
        if lines:
            books[f.stem] = {"title": lines[0], "sentences": lines[1:],
                             "source_hash": hashlib.sha256(raw.encode("utf-8")).hexdigest()}
    return books


def _sentence(s, **kw):
    try:
        return {"text": s, **translate(s, **kw)}
    except ValueError:  # a book line too long for /translate must not break the whole book
        return {"text": s, "signs": [], "face": "statement", "emotion": "neutral", "meaning": s,
                "source": "fallback", "unsure": True}


def list_books(book_dir=BOOK_DIR):
    return [{"id": i, "title": b["title"]} for i, b in load_books(book_dir).items()]


def build_book(book_id, *, book_dir=BOOK_DIR, model=None, phrases=None):
    """Translates every sentence with the real pipeline and writes the cache, even if some fell back."""
    book = load_books(book_dir).get(book_id)
    if book is None:
        raise KeyError(book_id)
    out = {"id": book_id, "title": book["title"], "source_hash": book["source_hash"],
           "sentences": [_sentence(s, model=model, phrases=phrases) for s in book["sentences"]]}
    path = Path(book_dir) / f"{book_id}.signs.json"
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)
    return out


def get_book(book_id, *, book_dir=BOOK_DIR, phrases=None):
    """Returns the book with every sentence translated, or None if the id is unknown."""
    phrases = PHRASES if phrases is None else phrases
    book = load_books(book_dir).get(book_id)  # lookup by id only, so a request can never reach a file path
    if book is None:
        return None
    try:
        cache = json.loads((Path(book_dir) / f"{book_id}.signs.json").read_text(encoding="utf-8"))
        cached = {s["text"]: s for s in cache["sentences"]} if cache["source_hash"] == book["source_hash"] else {}
    except (OSError, ValueError, KeyError, TypeError):
        cached = {}
    sentences = []
    for s in book["sentences"]:
        # the bank is re-applied at read time so a new human-checked phrase beats an older model translation
        if s in cached and _key(s) not in phrases:
            sentences.append(cached[s])
        else:
            sentences.append(_sentence(s, phrases=phrases, offline=True))
    return {"id": book_id, "title": book["title"], "sentences": sentences}


def _report(book_id, built):
    sents = built["sentences"]
    count = lambda src: sum(s["source"] == src for s in sents)
    unknown = sorted({g["gloss"] for s in sents for g in s["signs"] if not g["known"]})
    print(f"{book_id}: {len(sents)} sentences, phrase-bank {count('phrase-bank')}, model {count('model')}, "
          f"fallback {count('fallback')}, unsure {sum(s['unsure'] for s in sents)}, unknown glosses {unknown or 'none'}")


def main(argv):
    if len(argv) == 2 and argv[0] == "build":
        ids = list(load_books()) if argv[1] == "--all" else [argv[1]]
        for i in ids:
            try:
                _report(i, build_book(i))
            except KeyError:
                print(f"no book with id {i!r}")
                return 1
        return 0
    print("usage: python -m backend.books build <id> | build --all")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
