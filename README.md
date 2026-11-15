# Manibus (HackPrinceton, Education track)

Helps hearing parents give their deaf child sign language at home.

## Main goal: speech to ASL
The parent speaks, and the app signs it. It also shows the parent the signs and the facial expression that goes with them, so they learn to sign it themselves.

## Pivot: storybook to ASL
If live speech isn't good enough to demo, the lead feature becomes a storybook reader: the app takes a children's book or any open text and signs it sentence by sentence, so a family can read together in ASL at home.

Why this beats a video: signed videos exist for only a handful of books, because each one takes a signer hours to record. This works on the specific text the family has. Because the text is fixed, every sentence can be translated ahead of time and checked by a Deaf signer before a child sees it, which live speech can never offer.

## Both run on one pipeline

```
speech  -> speech.js      \
                           -> (text, emotion) -> POST /translate -> ordered signs + face + emotion -> SignPlayer
book    -> shared/books/  /
```

Speech and books are two ways of feeding text into the same translator and the same signer. Work on the main goal is not wasted if we pivot, and the storybook page already exists.

## When to pivot
Decide at the hour-16 check-in. Say 20 everyday parent sentences to the app ("time for bed", "are you hungry?", "where is your shoe?").

- **Stay on speech** if at least 14 of the 20 come out fully signed, with no fingerspelled words, in under three seconds.
- **Lead with the storybook** otherwise. Free speech has an open vocabulary, so the app hits words it has no sign for. A book has a fixed word list we can cover completely.

Either way both pages ship. The decision is which one opens the pitch.

## Who owns what

| Person | Area | Files | Guide |
|---|---|---|---|
| 1. Signer / ML | The signing itself: sign library, the 3D signer, face expressions | `ml/`, `frontend/src/components/SignPlayer.jsx`, `frontend/public/models/` | [ml/README.md](ml/README.md) |
| 2. Frontend / UX | Speak page, Storybook page, overall look | `frontend/`, except the files owned by 1 and 3 | [frontend/README.md](frontend/README.md) |
| 3. Backend / AI | Speech-to-text, English-to-ASL translation, book loading, API, demo | `backend/`, `shared/books/`, `frontend/src/lib/speech.js` | [backend/README.md](backend/README.md) |

Shared by all three: [CONTRACT.md](CONTRACT.md) and `shared/vocab.json`.

If you use Claude Code, `CLAUDE.md` and `.claude/` set up a team of helper agents (cheap ones for searches, stronger ones for reviews). Opening the repo in Claude Code makes Sonnet the main model.

## Avoiding merge conflicts
- Edit only your own files. If you need a change in someone else's file, ask them.
- Changes to `CONTRACT.md` or `shared/vocab.json` are announced to the other two before they are pushed.
- Work on your own branch (`signer`, `frontend`, `backend`) and merge to `main` often, at least every few hours.
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
The starter is wired end to end with simple stand-ins, so each person can replace their part without waiting:
- **Speak page:** type or speak a sentence and see the sign list and the face cue.
- **Storybook page:** reads `shared/books/pips-morning.txt`, a short original story, one sentence per page.
- **Translation:** the full pipeline is built: phrase bank, language model, self-check and fallback. With an API key it translates into ASL order with emotion and meaning; without one it falls back to word-for-word and marks the result unsure. See [backend/README.md](backend/README.md).
- **Handoff notes:** what the frontend and the signer need to change for the new backend is in [handoff/](handoff/).
- **Signer:** shows each sign as a word on a card until the 3D signer or video clips go in.

## Stretch: child to parent
The Practice page and `ml/recognizer.py` read a child's signs from the camera. They work as a starter but are not on the critical path. Pick them up only after the main goal or the pivot demos cleanly.

## Honest limits to say in the pitch
- Nobody on the team is Deaf or fluent in ASL. Sign choices and grammar need review by a Deaf signer.
- Machine-signed ASL is weaker than a human signer. This is a bridge while the parent learns, not a replacement for signing with their child or for a human interpreter.
- Only use original or public-domain text in `shared/books/`.

## Credits
Sign data from ASL-LEX 2.0 (Sehyr, Caselli, Cohen-Goldberg & Emmorey, 2021, https://asl-lex.org), licensed CC BY-NC 4.0.
