import { useState } from "react";
import Translator from "./pages/Translator.jsx";
import Reader from "./pages/Reader.jsx";
import Learn from "./pages/Learn.jsx";
import Home from "./pages/Home.jsx";

const PAGES = { Home, Speak: Translator, Read: Reader, Practice: Learn };
const AVATARS = [
  { id: "signer_glasses", name: "Glasses" }, // first = default: it has a clip for every vocab sign and A-Z
  { id: "signer_tshirt", name: "T-shirt" },
];

export default function App() {
  const [page, setPage] = useState("Home");
  const [avatar, setAvatar] = useState(() => localStorage.getItem("manibus-avatar") || AVATARS[0].id);
  const Page = PAGES[page];

  function pickAvatar(id) {
    setAvatar(id);
    localStorage.setItem("manibus-avatar", id);
  }

  return (
    <>
      <a href="#main" className="skip">Skip to content</a>
      <header className="topbar">
        <button className="brand" onClick={() => setPage("Home")} aria-label="Manibus home">
          <span aria-hidden="true">🤟</span> Manibus
        </button>
        <nav aria-label="Main">
          {Object.keys(PAGES).filter((n) => n !== "Home").map((name) => (
            <button key={name} onClick={() => setPage(name)} aria-current={page === name ? "page" : undefined}>
              {name}
            </button>
          ))}
        </nav>
        <label className="avatar-pick">
          Signer
          <select value={avatar} onChange={(e) => pickAvatar(e.target.value)}>
            {AVATARS.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
          </select>
        </label>
      </header>
      <main id="main">
        <Page avatar={avatar} go={setPage} />
      </main>
    </>
  );
}
