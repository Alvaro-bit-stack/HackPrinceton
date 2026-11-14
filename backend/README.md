# Backend and AI integration (Person 3)

You own everything between the parent's words and the sign list: translating English into ASL order, reading the emotion, double-checking the translation, learning from corrections, and preparing books.

| File | What it does |
|---|---|
| `backend/translate.py` | The pipeline: validation, phrase bank, language model, self-check, fallback. Used by both the Speak page and the Storybook. |
| `backend/llm.py` | Talks to the model provider (Anthropic or OpenAI) and holds the prompts. |
| `backend/corrections.py` | Saves the parent's meaning and emotion corrections to `backend/data/corrections.json` (git-ignored). |
| `backend/books.py` | Serves books from saved translations and builds those translations offline. |
| `backend/main.py` | The API routes in `CONTRACT.md`. |
| `backend/tests.py` | Tests that run with a fake model: no key, no network. |
| `shared/phrases.json` | The phrase bank of signer-checked translations. |
| `backend/asl_lex.py`, `shared/asl_lex.json` | The ASL-LEX sign dictionary: import, lookup and the next-signs list. |
| `shared/books/` | Book texts (`.txt`) and their saved translations (`.signs.json`). |
| `frontend/src/lib/speech.js` | Speech-to-text in the browser. |

Nobody else edits these.

## The translation workflow
Every sentence, spoken or from a book, goes through these steps in `translate.py`:

1. **Validate.**
   - Text: 1 to 300 characters.
   - `emotion`: one of the six, if sent.
   - `face_emotions`: only the seven face-api.js labels, each with a value from 0 to 1.
   - Bad input returns HTTP 422.
2. **Apply a saved correction.** If the parent corrected this exact sentence before, their emotion and meaning are used.
3. **Phrase bank.** If a fluent signer has checked this sentence, use those signs. No model call is made.
   - **Emotion:** an explicit emotion wins. Otherwise a non-neutral face emotion scoring 0.6 or more. Otherwise the entry's own emotion, or a keyword guess, or neutral.
   - **Corrected meaning:** if the parent corrected the meaning of a bank sentence, the bank is skipped, because the checked signs no longer match what they meant.
4. **Language model.** It gets:
   - the sentence, the face scores and any explicit emotion or meaning;
   - the vocabulary;
   - short ASL grammar notes;
   - up to 4 similar phrase-bank entries and the last 10 corrections, as examples.

   It returns signs in ASL order, the grammar face, the emotion and a one-line meaning. The words outrank the face. Words with no sign come back marked for fingerspelling.
5. **Check the model's output.** Every sign must be in the vocabulary or marked for fingerspelling, and the face and emotion must be valid. If not, it retries once.
6. **Self-check.** A second call turns the signs back into English and judges whether the meaning survived. If it didn't, the model re-translates once with feedback. If it still fails, the result is returned with `unsure: true`.
7. **Time limit.** Each model call has a timeout (20 seconds by default, set with `LLM_TIMEOUT_SECONDS`), and the whole sentence has a 45-second budget. When the budget runs out, the best valid attempt is returned with `unsure: true`.
8. **Fallback.** With no API key, no SDK, or a model error and no valid attempt, it returns the old word-for-word version: `source: "fallback"`, `unsure: true`. The demo never crashes.

Parents correct meaning and emotion through `POST /corrections`. A correction to the signs themselves only goes into `shared/phrases.json` once a fluent signer confirms it, by editing the file.

## Setup
1. `pip install -r backend/requirements.txt`. It includes both provider SDKs; you only need the one you use.
2. Copy `backend/.env.example` to `.env` at the repo root, and fill in `LLM_PROVIDER` and the matching key.
   - `LLM_MODEL` defaults to `claude-sonnet-5-5` for Anthropic.
   - OpenAI has no default, so set `LLM_MODEL` yourself.
3. Your Claude Pro or ChatGPT subscription doesn't cover API calls. You need a separate API account with credits.

## Run
From the repo root:
```
python -m backend.tests                          # 25 tests, no key needed
python -m backend.evaluate                       # accuracy on 24 parent sentences (needs a key)
python -m backend.books build pips-morning       # translate a book once (needs a key)
python -m backend.books build --all              # every book
uvicorn backend.main:app --reload --port 8000    # the API
```

The build command prints how many sentences came from the phrase bank, the model or the fallback, how many are unsure, and any words with no sign. Commit the `.signs.json` files it writes, so the storybook works offline at the demo.

## ASL-LEX (sign dictionary)
`shared/asl_lex.json` is a trimmed copy of ASL-LEX 2.0: 2,723 signs, each with how common it is, how much it looks like its meaning (iconicity), whether it's on the ASL children's vocabulary checklist, the age children learn it, and its handshape and location. It is a dictionary of single signs, separate from the phrase bank. It's used in three places:

- **Linking:** every sign in `vocab.json` has an `asl_lex` field pointing at its entry. A test checks they all exist.
- **What to animate next:** `shared/next_signs.md` lists the children's-checklist signs we don't have clips for yet, earliest-learned first.
- **Spotting missing signs:** when a word is fingerspelled but ASL-LEX has a real sign for it, the book build report and `python -m backend.evaluate` list it under "real signs to animate next".

To rebuild both files after a new ASL-LEX release or a `vocab.json` change, download the archive from https://osf.io/zpha4/ and run:
```
python -m backend.asl_lex import "path/to/Data Files/signdata.csv"
```
Credit: ASL-LEX 2.0, Sehyr, Caselli, Cohen-Goldberg & Emmorey (2021), https://asl-lex.org, CC BY-NC 4.0. Non-commercial use only. The sign videos in the archive are not used.

## Family profile and progress (catch-up, not cap)
Children who miss early language can't afford a "simpler" version. So the child's age never makes a translation simpler; the prompt tells the model to sign the full meaning with the richest signs it has. The age is only used to show the parent which everyday signs they haven't used yet.

- `backend/family.py`: the family profile (child's name and age, members with an avatar id), at `backend/data/family.json`. Routes `GET` and `PUT /family`.
- `backend/progress.py`: logs the known signs from every `/translate` (with the optional `speaker`) to `backend/data/usage.json`, works out `new_signs`, and builds `GET /progress`: signs used, this week's variety vs last week's, and a catch-up list of ASL-LEX child-vocabulary signs learned by the child's age that the family hasn't used, split into signs the app can show and signs still to animate.
- Both files live in `backend/data/`, which is git-ignored. Delete them to reset.

```
curl -s -X PUT localhost:8000/family -H "Content-Type: application/json" \
  -d '{"child_name": "Maya", "child_age_months": 30, "members": [{"id": "mom", "name": "Mom", "avatar": null}]}'
curl -s "localhost:8000/progress?speaker=mom"
```

## Testing without the frontend
There are three levels, from fastest to most realistic.

1. **Logic tests (no key):** `python -m backend.tests` checks the pipeline rules with a fake model.
2. **Try the API by hand.** Start the server with `uvicorn backend.main:app --reload --port 8000`, then open http://localhost:8000/docs. FastAPI's built-in page lists every route; pick one, click "Try it out", edit the JSON and click Execute. Or use curl:
   ```
   curl -s localhost:8000/translate -H "Content-Type: application/json" \
     -d '{"text": "you ate all of it", "face_emotions": {"happy": 0.8, "surprised": 0.1}}'
   curl -s localhost:8000/corrections -H "Content-Type: application/json" \
     -d '{"text": "you ate all of it", "emotion": "surprised"}'
   curl -s localhost:8000/books/pips-morning
   ```
3. **Measure accuracy:** `python -m backend.evaluate` runs the 24 parent sentences in `backend/eval_sentences.json` through the real model. For each sentence it checks the question type, the emotion and the key signs, and records how long it took. The summary includes the hour-16 pivot number: how many sentences came out fully signed in under 3 seconds. It also writes a review sheet for a fluent signer to `backend/data/` (git-ignored).
   - `--offline` runs without the model, giving the word-for-word baseline to beat: 18/24 question types, 6/7 emotions, 25/28 key signs, 0 fully signed.
   - Add sentences to `eval_sentences.json` as you find ones the app gets wrong.
   - The script can't judge sign order or ASL grammar. That's what the signer's review sheet is for.

## Tasks
1. **Get an API key and test one real request.** The provider code in `llm.py` hasn't been run against the real SDKs yet. Translate one sentence with the server running and check the response.
2. **Build the sample book's translation** and commit `shared/books/pips-morning.signs.json`.
3. **Tune the prompts** in `llm.py` against 20 everyday parent sentences. Note which come back `unsure`.
4. **Get a fluent signer to check translations,** and add the good ones to `shared/phrases.json` with `meaning` and `emotion`.
5. **Make speech reliable.** Test `speech.js` in a noisy room, and keep typed input as the fallback.
6. **Add one or two more stories.** Write them yourself or use public-domain text only.
7. **Run the hour-16 pivot test** in the root README and record the result.
8. **Stretch, for the LangChain prize:** a deepagents agent that prepares a whole book. It plans the work, calls `translate()` for each sentence, reviews the unsure ones, and writes a report of missing signs. It fits as an alternative to `build_book`, and stays off the live speech path.
9. **Own the end-to-end demo.**

## What the other two need from you
Handoff notes are in [`handoff/frontend.md`](../handoff/frontend.md) and [`handoff/3d-signer.md`](../handoff/3d-signer.md).
