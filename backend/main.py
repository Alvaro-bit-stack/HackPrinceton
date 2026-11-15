"""API that connects the recogniser, the translator and the frontend. Owner: Person 3.

Run from the repo root:  uvicorn backend.main:app --reload --port 8000
"""
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import Annotated, Literal, Optional

from backend.books import get_book, list_books
from backend.corrections import load_corrections, save_correction
from backend.family import load_family, save_family
from backend.progress import log_usage, new_signs, progress
from backend.translate import MAX_FRAME_CHARS, MAX_FRAMES, VOCAB, translate
from ml.recognizer import predict

app = FastAPI(title="HackPrinceton sign bridge")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_methods=["*"], allow_headers=["*"])


Emotion = Literal["neutral", "happy", "sad", "angry", "surprised", "worried"]


class TranslateIn(BaseModel):
    text: str
    # the speaker's tone, when the frontend knows it; otherwise the backend decides from the words and face
    emotion: Optional[Emotion] = None
    face_emotions: Optional[dict[str, float]] = None
    loudness: Optional[float] = Field(None, ge=-1, le=1)  # parent's voice vs their own normal; sets intensity only
    pitch: Optional[float] = Field(None, ge=-1, le=1)  # same idea for voice pitch
    face_frames: Optional[list[Annotated[str, Field(max_length=MAX_FRAME_CHARS)]]] = Field(None, max_length=MAX_FRAMES)  # opt-in: up to 3 base64 JPEG snapshots of the strongest moments
    face_neutral: Optional[str] = Field(None, max_length=MAX_FRAME_CHARS)  # opt-in: the parent's neutral-face snapshot, for comparison
    speaker: Optional[str] = Field(None, pattern=r"^[a-z0-9-]{1,30}$")  # a family member id


class CorrectionIn(BaseModel):
    text: str
    meaning: Optional[str] = None
    emotion: Optional[Emotion] = None


class MemberIn(BaseModel):
    id: str
    name: str
    avatar: Optional[str] = None


class FamilyIn(BaseModel):
    child_name: Optional[str] = None
    child_age_months: Optional[int] = None
    members: list[MemberIn] = []


class RecognizeIn(BaseModel):
    frames: list[list[list[float]]]


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/dev", include_in_schema=False)
def dev_page():
    # local test bench: speak + face in, raw signer output shown; same origin, so no CORS change
    return FileResponse(Path(__file__).parent / "dev.html")


@app.get("/vocab")
def vocab():
    return VOCAB


@app.post("/translate")
def translate_route(body: TranslateIn):
    try:
        result = translate(body.text, body.emotion, body.face_emotions, corrections=load_corrections(), loudness=body.loudness, pitch=body.pitch,
                           face_frames=body.face_frames, face_neutral=body.face_neutral)
        known = [s["gloss"] for s in result["signs"] if s["known"]]
        result["new_signs"] = new_signs(known)
        try:
            log_usage(known, body.speaker)
        except OSError:
            logging.warning("usage log not written", exc_info=True)  # progress is a nice-to-have; never lose the translation
        return result
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.post("/corrections")
def corrections_route(body: CorrectionIn):
    try:
        e = save_correction(body.text, body.meaning, body.emotion)  # use the cleaned values, e.g. blank meaning -> None
        result = translate(body.text, emotion=e["emotion"], meaning_hint=e["meaning"], corrections=load_corrections())
        result["new_signs"] = new_signs([s["gloss"] for s in result["signs"] if s["known"]])  # not logged: /translate already did
        return result
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.get("/family")
def family_get():
    return load_family()


@app.put("/family")
def family_put(body: FamilyIn):
    try:
        return save_family(body.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.get("/progress")
def progress_route(speaker: Optional[str] = Query(None, pattern=r"^[a-z0-9-]{1,30}$")):
    return progress(load_family()["child_age_months"], speaker)


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
