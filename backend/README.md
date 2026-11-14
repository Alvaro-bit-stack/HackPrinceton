# Backend and AI integration (Person 3)

You own everything between the words and the sign list: hearing the parent, translating English into ASL order, and loading books.

| File | What it does |
|---|---|
| `backend/translate.py` | English text to an ordered sign list and a face tag. The heart of both the main goal and the pivot. |
| `backend/books.py` | Loads `shared/books/*.txt` and translates each sentence. |
| `backend/main.py` | The API routes in `CONTRACT.md`. |
| `shared/books/` | The texts for storybook mode. |
| `frontend/src/lib/speech.js` | Speech-to-text in the browser. |

Nobody else edits these.

## Tasks
1. Run the API and confirm the frontend reaches `/health`.
2. Replace the word-for-word stub in `translate.py` with a language-model call that returns signs in ASL order, using only glosses from `shared/vocab.json`, plus the face tag.
3. Make speech reliable: test `speech.js` in a noisy room and keep the typed input as the fallback.
4. Cache book translations so storybook pages load instantly, and so a reviewer can correct a sentence once and have it stick.
5. Add one or two more stories. Write them yourself or use public-domain text only.
6. Run the hour-16 pivot test in the root README and record the result.
7. Stretch, for the LangChain prize: a deepagents agent that takes a whole book, plans the translation, checks every sign against the vocabulary and lists the signs still missing.
8. Own the end-to-end demo.

## Run
```
pip install -r backend/requirements.txt
python backend/translate.py                      # self-check
python -m backend.books                          # self-check
uvicorn backend.main:app --reload --port 8000    # from the repo root
```

Put API keys in a `.env` file. It is git-ignored; never commit keys.
