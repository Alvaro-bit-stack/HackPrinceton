"""The Manibus API with ASL -> English added. Serves every existing route (/translate, /recognize, /books, ...)
unchanged, plus POST /understand: the child signs to the camera, the parent reads what they said.

Run from the repo root instead of backend.main:  uvicorn asl2english.asl2eng:app --reload --port 8000
"""
import logging
from typing import Literal, Optional

from fastapi import HTTPException
from pydantic import BaseModel, Field

from asl2english.asl_to_english import nothing_signed, understand, validate_cues
from asl2english.recognize import MAX_FRAMES, recognize_signs, validate_frames
from backend.family import load_family
from backend.main import Emotion, app

__all__ = ["app"]


class UnderstandIn(BaseModel):
    # each frame: the 21 (x, y, z) hand landmarks from MediaPipe, or null when no hand was seen
    frames: list[Optional[list[list[float]]]] = Field(..., min_length=1, max_length=MAX_FRAMES)
    face: Optional[Literal["statement", "yes-no-question", "wh-question"]] = None  # the child's brows, if the frontend reads them
    head_shake: Optional[bool] = None
    emotion: Optional[Emotion] = None
    face_emotions: Optional[dict[str, float]] = None


def _child_name():
    try:
        return load_family().get("child_name")
    except (OSError, ValueError):
        logging.warning("family profile not readable; using 'your child'")
        return None


@app.post("/understand")
def understand_route(body: UnderstandIn):
    """Frames are used for this request only: never stored or logged."""
    try:
        validate_frames(body.frames)
        validate_cues(body.face, body.head_shake, body.emotion, body.face_emotions)
        rec = recognize_signs(body.frames)
        signs = [{"gloss": s["glosses"][0]["gloss"], "confidence": s["glosses"][0]["confidence"],
                  "alternatives": s["glosses"][1:]} for s in rec["signs"]]
        result = (understand(signs, body.face, body.head_shake, body.emotion, body.face_emotions, _child_name())
                  if signs else nothing_signed(body.emotion))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    result["signs"] = rec["signs"]
    result["recognizer"] = rec["recognizer"]
    return result
