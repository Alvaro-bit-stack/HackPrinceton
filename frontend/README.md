# frontend: everything the family sees (Person 2)

A React app with two pages: the two-way translator and the practice page.

| File | What it does |
|---|---|
| `src/App.jsx` | Navigation between pages. |
| `src/pages/Translator.jsx` | Parent speaks and the app signs; child signs and the app reads. |
| `src/pages/Learn.jsx` | Practice page with gentle hints. |
| `src/components/SignPlayer.jsx` | Shows the signs. Currently words on cards; swap in the 3D signer or video clips. |
| `src/components/Webcam.jsx` | Camera view that feeds hand landmarks to the page. |
| `src/api.js` | Calls to the backend. |
| `src/styles.css` | Styles. |

`src/lib/handTracker.js` belongs to Person 1 and `src/lib/speech.js` to Person 3. Import them, don't edit them.

## Tasks
1. Run the app against the backend and confirm both pages load.
2. Replace the word cards in `SignPlayer.jsx` with the signer: load `public/models/signer.glb` with three.js, or play a video clip per sign.
3. Show the face cue clearly, since it is how the parent learns the grammar.
4. Make the practice page child-friendly: big targets, few words, a reward when a sign lands.
5. Handle the unhappy paths: no camera, no microphone, backend down.
6. Polish for the demo: one clean screen per direction.

## Run
```
cd frontend
npm install
npm run dev        # http://localhost:5173
```
