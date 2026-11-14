import { useEffect, useRef, useState } from "react";
import { getVocab, recognize } from "../api.js";
import Webcam from "../components/Webcam.jsx";

// Practice page: pick a sign, try it on camera, get a gentle hint. Never says "wrong".
export default function Learn() {
  const [vocab, setVocab] = useState([]);
  const [target, setTarget] = useState(null);
  const [hint, setHint] = useState("");
  const [error, setError] = useState("");
  const busy = useRef(false);

  useEffect(() => {
    getVocab().then(setVocab).catch(() => setError("Couldn't load the sign list. Is the backend running?"));
  }, []);

  async function onFrames(frames) {
    if (!target || busy.current) return;
    busy.current = true;
    try {
      const r = await recognize(frames);
      setHint(r.sign === target ? "That's it!" : "Not yet, keep going.");
    } catch {
      /* keep the last hint */
    } finally {
      setTimeout(() => (busy.current = false), 500);
    }
  }

  return (
    <div className="columns">
      <section>
        <h2>Pick a sign to practise</h2>
        {error && <p role="alert">{error}</p>}
        <div className="chips">
          {vocab.map((v) => (
            <button key={v.gloss} onClick={() => { setTarget(v.gloss); setHint(""); }} aria-pressed={target === v.gloss}>
              {v.gloss}
            </button>
          ))}
        </div>
      </section>
      <section>
        <h2>{target ? `Try signing ${target}` : "Choose a sign first"}</h2>
        {target && <Webcam onFrames={onFrames} />}
        <p className="cue" aria-live="polite">{hint}</p>
      </section>
    </div>
  );
}
