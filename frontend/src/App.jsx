import { useState } from "react";
import Translator from "./pages/Translator.jsx";
import Learn from "./pages/Learn.jsx";

const PAGES = { Translate: Translator, Learn };

export default function App() {
  const [page, setPage] = useState("Translate");
  const Page = PAGES[page];
  return (
    <>
      <nav>
        <strong>Sign Bridge</strong>
        {Object.keys(PAGES).map((name) => (
          <button key={name} onClick={() => setPage(name)} aria-current={page === name ? "page" : undefined}>
            {name}
          </button>
        ))}
      </nav>
      <main>
        <Page />
      </main>
    </>
  );
}
