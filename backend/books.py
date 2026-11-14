"""Storybook mode: fixed texts, translated sentence by sentence. Owner: Person 3.

Add a book by dropping a .txt file in shared/books/: first line is the title, then one sentence per line.
Use only original or public-domain text. Run `python backend/books.py` for the self-check.
"""
from pathlib import Path

from backend.translate import translate

BOOK_DIR = Path(__file__).parent.parent / "shared" / "books"


def load_books():
    books = {}
    for f in sorted(BOOK_DIR.glob("*.txt")):
        lines = [ln.strip() for ln in f.read_text(encoding="utf-8").splitlines() if ln.strip()]
        if lines:
            books[f.stem] = {"title": lines[0], "sentences": lines[1:]}
    return books


BOOKS = load_books()


def list_books():
    return [{"id": i, "title": b["title"]} for i, b in BOOKS.items()]


def get_book(book_id):
    """Returns the book with every sentence translated, or None if the id is unknown."""
    book = BOOKS.get(book_id)  # lookup only, so a request can never reach a file path
    if book is None:
        return None
    return {"id": book_id, "title": book["title"],
            "sentences": [{"text": s, **translate(s)} for s in book["sentences"]]}


if __name__ == "__main__":
    assert list_books()[0] == {"id": "pips-morning", "title": "Pip's Morning"}
    b = get_book("pips-morning")
    assert b["sentences"][3]["face"] == "yes-no-question"
    assert [s["gloss"] for s in b["sentences"][-1]["signs"]] == ["ME", "LOVE", "YOU"]
    assert get_book("../translate") is None
    print("books self-check passed")
