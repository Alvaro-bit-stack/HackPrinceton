import { useRef, useState } from "react";
import { recognize, translate } from "../api.js";
import SignPlayer from "../components/SignPlayer.jsx";
import Webcam from "../components/Webcam.jsx";
import { listen, speak } from "../lib/speech.js";

export default function Translator() {
  const [text, setText] = useState("");
  const [result, setResult] = useState({ signs: [], face: "statement" });
  const [childSign, setChildSign] = useState(null);
  const [error, setError] = useState("");
  const busy = useRef(false);

  async function send(sentence) {
    setText(sentence);
    setError("");
    try {
      setResult(await translate(sentence));
    } catch {
      setError("Couldn't reach the translator. Is the backend running?");
    }
  }

  async function onFrames(frames) {
    if (busy.current) return; // one request at a time
    busy.current = true;
    try {
      const r = await recognize(frames);
      if (r.sign) setChildSign(r);
    } catch {
      /* backend down: the parent side already shows the error */
    } finally {
      setTimeout(() => (busy.current = false), 500);
    }
  }

  return (
    <div className="columns">
      <section>
        <h2>You speak, the app signs</h2>
        <form onSubmit={(e) => { e.preventDefault(); send(text); }}>
          <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Do you want more milk?" aria-label="What you want to say" />
          <button type="submit">Sign it</button>
          <button type="button" onClick={() => listen(send, setError)}>Speak</button>
        </form>
        {error && <p role="alert">{error}</p>}
        <SignPlayer signs={result.signs} face={result.face} />
      </section>
      <section>
        <h2>Your child signs, the app reads</h2>
        <Webcam onFrames={onFrames} />
        <p className="sign-card" aria-live="polite">{childSign ? childSign.sign : "…"}</p>
        {childSign && (
          <p>
            Looks like {childSign.sign} ({Math.round(childSign.confidence * 100)}% sure){" "}
            <button onClick={() => speak(childSign.sign.toLowerCase())}>Say it aloud</button>
          </p>
        )}
      </section>
    </div>
  );
}
