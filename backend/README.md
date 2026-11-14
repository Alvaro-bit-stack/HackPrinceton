# Backend and AI integration (Person 3)

You own everything between the words and the sign list: hearing the parent, translating English into ASL order, and loading books.

| File | What it does |
|---|---|
| `backend/translate.py` | English text and emotion to an ordered sign list, grammar face and emotion. The heart of both the main goal and the pivot. |
| `shared/phrases.json` | The phrase bank of human-checked translations. |
| `backend/books.py` | Loads `shared/books/*.txt` and translates each sentence. |
| `backend/main.py` | The API routes in `CONTRACT.md`. |
| `shared/books/` | The texts for storybook mode. |
| `frontend/src/lib/speech.js` | Speech-to-text in the browser. |

Nobody else edits these.

## The translation workflow
Every sentence, spoken or from a book, goes through these steps in `translate.py`:

1. **Tag the emotion.** The input is a pair: the words and the speaker's tone, for example `("Stop!", "angry")`. If the tone isn't sent, work it out from the words.
2. **Phrase bank first.** If `shared/phrases.json` has a human-checked translation for the sentence, use it as is.
3. **Language model otherwise.** Give it the vocabulary, a few ASL grammar notes, the emotion, and the closest phrase-bank entries as examples. It returns signs in ASL order, the grammar face and the emotion, using only signs on the list. For a word with no sign, it rephrases with signs we have or marks the word for fingerspelling.
4. **Self-check.** A second call turns the sign list back into English. If the meaning changed, retry or flag it.
5. **Corrections feed back.** When a reviewer fixes a translation, add it to the phrase bank.

Steps 1 and 2 work today in a simple form. Steps 3 and 4 are yours to build.

## Tasks
1. Run the API and confirm the frontend reaches `/health`.
2. Build step 3: replace the word-for-word stub with the language-model call. Have it return the emotion in the same call, so it reads the whole sentence and not just keywords.
3. Build step 4: the back-translation self-check.
4. Get tone from the voice. The browser's speech recognition returns words only, so pick one: record the audio and run a speech-emotion model on it, or send the audio to a model that accepts audio. Then pass the result as `emotion`. Until then the emotion comes from the words.
5. Make speech reliable: test `speech.js` in a noisy room and keep the typed input as the fallback.
6. Cache book translations so storybook pages load instantly, and so a reviewer's fix sticks.
7. Add one or two more stories. Write them yourself or use public-domain text only.
8. Run the hour-16 pivot test in the root README and record the result.
9. Stretch, for the LangChain prize: a deepagents agent that prepares a whole book. It plans the work, translates each sentence, runs the self-check, and writes a report of missing signs and sentences that need a human look. Keep it out of the live speech path, where it would add delay.
10. Own the end-to-end demo.

## Run
```
pip install -r backend/requirements.txt
python backend/translate.py                      # self-check
python -m backend.books                          # self-check
uvicorn backend.main:app --reload --port 8000    # from the repo root
```

Put API keys in a `.env` file. It is git-ignored; never commit keys.
