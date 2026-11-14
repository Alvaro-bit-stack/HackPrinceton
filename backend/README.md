# backend: API and AI integration (Person 3)

Connects the pieces: speech in, signs out, and the child's signs back to text.

| File | What it does |
|---|---|
| `backend/main.py` | The API routes in `CONTRACT.md`. |
| `backend/translate.py` | English text to an ordered sign list and a face tag. |
| `frontend/src/lib/speech.js` | Speech-to-text and text-to-speech in the browser. |

Nobody else edits these files.

## Tasks
1. Run the API and confirm the frontend reaches `/health`.
2. Replace the word-for-word stub in `translate.py` with a language-model call that returns signs in ASL order, using only glosses from `shared/vocab.json`.
3. Add whole-phrase matching: for the 30 most common parent phrases, return one phrase ID so the player can show a single recording.
4. Get `speech.js` working: the parent's speech becomes text, and the child's recognised sign is read aloud.
5. Add the tutor: after a practice attempt, return one short, kind hint. It never says "wrong".
6. Stretch, for the LangChain prize: a deepagents planner that picks next week's signs from the family's practice history.
7. Run the end-to-end demo script and own the final integration.

## Run
```
pip install -r backend/requirements.txt
python backend/translate.py                      # self-check
uvicorn backend.main:app --reload --port 8000    # from the repo root
```

Put API keys in a `.env` file. It is git-ignored; never commit keys.
