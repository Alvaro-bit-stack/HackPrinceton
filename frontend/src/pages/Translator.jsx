import { useState } from "react";
import { translate } from "../api.js";
import SignPlayer from "../components/SignPlayer.jsx";
import { listen } from "../lib/speech.js";

// Main goal: the parent speaks (or types) and the app signs it.
export default function Translator() {
  const [text, setText] = useState("");
  const [result, setResult] = useState({ signs: [], face: "statement" });
  const [error, setError] = useState("");

  async function send(sentence) {
    setText(sentence);
    setError("");
    try {
      setResult(await translate(sentence));
    } catch {
      setError("Couldn't reach the translator. Is the backend running?");
    }
  }

  return (
    <section>
      <h2>Say it, and the app signs it</h2>
      <form onSubmit={(e) => { e.preventDefault(); send(text); }}>
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Do you want more milk?" aria-label="What you want to say" />
        <button type="submit">Sign it</button>
        <button type="button" onClick={() => listen(send, setError)}>Speak</button>
      </form>
      {error && <p role="alert">{error}</p>}
      <SignPlayer signs={result.signs} face={result.face} emotion={result.emotion} />
    </section>
  );
}
