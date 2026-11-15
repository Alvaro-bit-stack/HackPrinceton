
import { useState } from "react";
import Home from "./pages/Home.jsx";
import Translator from "./pages/Translator.jsx";
import Reader from "./pages/Reader.jsx";

const PAGES = {
  Home,
  Speak: Translator,
  Read: Reader,
};

export default function App() {
  const [page, setPage] = useState("Home");

  function navigate(destination) {
    if (!PAGES[destination]) return;
    setPage(destination);
    window.scrollTo(0, 0);
  }

  const Page = PAGES[page];

  return (
    <div className="manibus-app">
      <header className="topbar manibus-topbar">
        <button
          type="button"
          className="brand manibus-brand"
          onClick={() => navigate("Home")}
          aria-label="Go to Manibus home"
        >
          <img
            src="/manibus-logo.png"
            alt="Manibus"
            className="brand-logo"
          />
        </button>

        <nav
          className="manibus-nav"
          aria-label="Main navigation"
        >
          {[
            ["Home", "Home"],
            ["Speak", "Translate"],
            ["Read", "Read"],
          ].map(([id, label]) => (
            <button
              type="button"
              key={id}
              className={page === id ? "is-active" : ""}
              aria-current={
                page === id ? "page" : undefined
              }
              onClick={() => navigate(id)}
            >
              {label}
            </button>
          ))}
        </nav>
      </header>

      <main id="main" className="manibus-main">
        <Page
          avatar="signer_glasses"
          go={navigate}
        />
      </main>
    </div>
  );
}
