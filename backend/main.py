"""API that connects the recogniser, the translator and the frontend. Owner: Person 3.

Run from the repo root:  uvicorn backend.main:app --reload --port 8000
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.books import get_book, list_books
from backend.translate import VOCAB, translate
from ml.recognizer import predict

app = FastAPI(title="HackPrinceton sign bridge")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])


class TranslateIn(BaseModel):
    text: str


class RecognizeIn(BaseModel):
    frames: list[list[list[float]]]


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/vocab")
def vocab():
    return VOCAB


@app.post("/translate")
def translate_route(body: TranslateIn):
    return translate(body.text)


@app.get("/books")
def books_route():
    return list_books()


@app.get("/books/{book_id}")
def book_route(book_id: str):
    book = get_book(book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="No book with that id")
    return book


@app.post("/recognize")
def recognize_route(body: RecognizeIn):
    return predict(body.frames)
