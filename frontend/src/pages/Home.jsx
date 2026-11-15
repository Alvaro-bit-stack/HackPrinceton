import { useEffect, useState } from "react";
import { getHealth } from "../api.js";

const CARDS = [
  { page: "Speak", icon: "🎤", title: "Speak", text: "Talk or type to your child. Manibus signs it in ASL, with the feeling in your face and voice." },
  { page: "Read", icon: "📖", title: "Read", text: "Read a story or your own text together. Each sentence is signed while the words light up." },
  { page: "Practice", icon: "✋", title: "Practice", text: "Try a sign on camera and get a gentle hint." },
];

// Landing page: what Manibus is for and where to start.
export default function Home({ go }) {
  const [server, setServer] = useState("checking");
  useEffect(() => {
    getHealth().then(() => setServer("ok")).catch(() => setServer("down"));
  }, []);

  return (
    <div className="home">
      <section className="hero">
        <h1>Sign with your child, every day</h1>
        <p>
          Most deaf children are born to hearing parents. Manibus helps you talk to your child in American Sign Language
          as you go about your day: say something and a friendly 3D signer shows you how to sign it.
        </p>
      </section>
      <div className="cards">
        {CARDS.map((c) => (
          <button key={c.page} className="card" onClick={() => go(c.page)}>
            <span className="card-icon" aria-hidden="true">{c.icon}</span>
            <strong>{c.title}</strong>
            <span>{c.text}</span>
          </button>
        ))}
      </div>
      {server === "down" && (
        <p role="alert" className="error">
          The Manibus server isn't answering. Start it with <code>uvicorn backend.main:app --port 8000</code> from the project folder.
        </p>
      )}
      <p className="muted small">
        Translations are a starting point, not a replacement for a fluent signer. Anything marked “not sure” is worth checking.
      </p>
    </div>
  );
}
