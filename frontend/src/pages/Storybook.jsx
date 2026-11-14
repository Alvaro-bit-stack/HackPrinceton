import { useEffect, useState } from "react";
import { getBook, getBooks } from "../api.js";
import SignPlayer from "../components/SignPlayer.jsx";

// Pivot: a fixed text (a children's book) signed one sentence at a time.
export default function Storybook() {
  const [books, setBooks] = useState([]);
  const [book, setBook] = useState(null);
  const [i, setI] = useState(0);
  const [error, setError] = useState("");

  useEffect(() => {
    getBooks().then(setBooks).catch(() => setError("Couldn't load the books. Is the backend running?"));
  }, []);

  async function open(id) {
    setError("");
    try {
      setBook(await getBook(id));
      setI(0);
    } catch {
      setError("Couldn't open that book.");
    }
  }

  if (error) return <p role="alert">{error}</p>;
  if (!book) {
    return (
      <section>
        <h2>Pick a story</h2>
        <div className="chips">
          {books.map((b) => <button key={b.id} onClick={() => open(b.id)}>{b.title}</button>)}
        </div>
      </section>
    );
  }
  const s = book.sentences[i];
  return (
    <section>
      <h2>{book.title}</h2>
      <p className="story-text">{s.text}</p>
      <SignPlayer signs={s.signs} face={s.face} />
      <p>
        <button onClick={() => setI(i - 1)} disabled={i === 0}>Back</button>{" "}
        <span>Page {i + 1} of {book.sentences.length}</span>{" "}
        <button onClick={() => setI(i + 1)} disabled={i === book.sentences.length - 1}>Next</button>{" "}
        <button onClick={() => setBook(null)}>All stories</button>
      </p>
    </section>
  );
}
