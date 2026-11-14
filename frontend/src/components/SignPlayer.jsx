import { useEffect, useState } from "react";

const FACE_CUE = {
  "statement": "",
  "yes-no-question": "Raise your eyebrows: it's a yes/no question.",
  "wh-question": "Lower your eyebrows: it's a what/where/who question.",
};

// Steps through the signs one at a time and tells the parent which face goes with them.
// Placeholder: shows each sign as a word. Swap the card for the 3D signer or a video clip
// (put signer.glb in frontend/public/models/).
export default function SignPlayer({ signs, face }) {
  const [i, setI] = useState(0);

  useEffect(() => {
    setI(0);
    if (!signs.length) return;
    const id = setInterval(() => setI((n) => Math.min(n + 1, signs.length - 1)), 1200);
    return () => clearInterval(id);
  }, [signs]);

  if (!signs.length) return <p>Signs will show here.</p>;
  const sign = signs[i];
  return (
    <div>
      <div className="sign-card" aria-live="polite">
        {sign.gloss}
        {!sign.known && <small> (fingerspell)</small>}
      </div>
      <p>{signs.map((s, n) => (n === i ? <strong key={n}>{s.gloss} </strong> : <span key={n}>{s.gloss} </span>))}</p>
      {FACE_CUE[face] && <p className="cue">{FACE_CUE[face]}</p>}
    </div>
  );
}
