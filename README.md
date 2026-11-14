# Sign Bridge (HackPrinceton, Education track)

Helps hearing parents communicate with their deaf child, and learn to sign while they do it.

- **Parent to child:** the parent speaks, the app shows the signs in order, and it cues the parent on the face that goes with them so they can sign along.
- **Child to parent:** the child signs to the camera and the app shows and speaks the word.
- **Practice:** a page where the parent or child practises one sign at a time with gentle hints.

## How it fits together

```
parent's voice -> speech.js -> POST /translate -> translate.py -> SignPlayer
child's hands  -> handTracker.js -> POST /recognize -> recognizer.py -> text and speech
```

The exact request and response shapes are in [CONTRACT.md](CONTRACT.md).

## Who owns what

| Person | Area | Files | Guide |
|---|---|---|---|
| 1. Computer vision / ML | Recognising the child's signs | `ml/`, `frontend/src/lib/handTracker.js` | [ml/README.md](ml/README.md) |
| 2. Frontend / UX | Everything the family sees | `frontend/` except `src/lib/` | [frontend/README.md](frontend/README.md) |
| 3. Backend / AI | API, translation, speech, tutor, demo | `backend/`, `frontend/src/lib/speech.js` | [backend/README.md](backend/README.md) |

Shared by all three: `CONTRACT.md` and `shared/vocab.json`.

## Avoiding merge conflicts
- Edit only your own files. If you need a change in someone else's file, ask them.
- Changes to `CONTRACT.md` or `shared/vocab.json` are announced to the other two before they are pushed.
- Work on your own branch (`ml`, `frontend`, `backend`) and merge to `main` often, at least every few hours.
- Person 3 does the integration, so the wiring has one editor.

## Run it

Backend, from the repo root:
```
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload --port 8000
```

Frontend:
```
cd frontend
npm install
npm run dev
```

Then open http://localhost:5173. Use Chrome, since speech recognition needs it.

## What works today
The starter is wired end to end with simple stand-ins, so each person can replace their part without waiting on the others:
- `translate.py` maps words to signs one for one. It is not ASL grammar yet.
- `recognizer.py` matches handshape against recorded examples. It has no examples yet, so it returns nothing until Person 1 records some.
- `SignPlayer.jsx` shows each sign as a word on a card until the 3D signer or video clips go in.

## Honest limits to say in the pitch
- Nobody on the team is Deaf or fluent in ASL. Sign choices and grammar need review by a Deaf signer.
- The app gives hints, never "correct" or "wrong".
- It is a bridge while the parent learns, not a replacement for signing with their child.
- Camera video is processed in the browser; only hand landmark positions are sent to the backend, and nothing is stored.
