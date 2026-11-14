"""API that connects the recogniser, the translator and the frontend. Owner: Person 3.

Run from the repo root:  uvicorn backend.main:app --reload --port 8000
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Literal, Optional

from backend.books import get_book, list_books
from backend.corrections import load_corrections, save_correction
from backend.translate import VOCAB, translate
from ml.recognizer import predict

app = FastAPI(title="HackPrinceton sign bridge")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])


Emotion = Literal["neutral", "happy", "sad", "angry", "surprised", "worried"]


class TranslateIn(BaseModel):
    text: str
    # the speaker's tone, when the frontend knows it; otherwise the backend decides from the words and face
    emotion: Optional[Emotion] = None
    face_emotions: Optional[dict[str, float]] = None


class CorrectionIn(BaseModel):
    text: str
    meaning: Optional[str] = None
    emotion: Optional[Emotion] = None


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
    try:
        return translate(body.text, body.emotion, body.face_emotions, corrections=load_corrections())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.post("/corrections")
def corrections_route(body: CorrectionIn):
    try:
        e = save_correction(body.text, body.meaning, body.emotion)  # use the cleaned values, e.g. blank meaning -> None
        return translate(body.text, emotion=e["emotion"], meaning_hint=e["meaning"], corrections=load_corrections())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


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
