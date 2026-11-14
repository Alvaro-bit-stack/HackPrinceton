# Frontend (Person 2)

Everything the family sees, except the signer itself.

| File | What it does |
|---|---|
| `src/App.jsx` | Navigation between pages. |
| `src/pages/Translator.jsx` | Speak page, the main goal: the parent speaks and the app signs. |
| `src/pages/Storybook.jsx` | Storybook page, the pivot: a book signed one sentence per page. |
| `src/pages/Learn.jsx`, `src/components/Webcam.jsx` | Practice page, a stretch feature. |
| `src/api.js` | Calls to the backend. |
| `src/styles.css` | Styles. |

Not yours: `src/components/SignPlayer.jsx` and `public/models/` belong to Person 1, `src/lib/speech.js` to Person 3, and `src/lib/handTracker.js` to Person 1. Import them, don't edit them.

## Tasks
1. Run the app against the backend and confirm the Speak and Storybook pages work.
2. Speak page: make it one clear action. Big microphone button, the sentence heard, then the signing.
3. Storybook page: make it feel like a picture book. Large text, the signer beside it, easy page turns, and a replay button.
4. Show the face cue prominently on both pages, since it is how the parent learns the grammar.
5. Handle the unhappy paths: no microphone, speech not understood, backend down.
6. Make it child-friendly: big targets, few words, calm colours.

## Run
```
cd frontend
npm install
npm run dev        # http://localhost:5173
```
