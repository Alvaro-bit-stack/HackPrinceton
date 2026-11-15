import { useEffect, useRef, useState } from "react";
import { getBook, getBooks, getVocab, translate } from "../api.js";
import SignPlayer from "../components/SignPlayer.jsx";
import PlayerControls from "../components/PlayerControls.jsx";
import { SourceBadge } from "../components/Badges.jsx";
import { splitSentences, tokenize, wordsForGlosses } from "../lib/text.js";

const MAX_SENTENCES = 60; // each one is a translation request
const MAX_FILE_BYTES = 200_000;
const CONCURRENCY = 2;

// Interactive reader: a story or the parent's own text on one side, the signer on the other,
// with the sentence and the words being signed highlighted as it plays.
export default function Reader({ avatar }) {
  const [doc, setDoc] = useState(null); // { title, sentences: [{ text, status, data, error }] }
  const [vocab, setVocab] = useState([]);
  useEffect(() => { getVocab().then(setVocab).catch(() => {}); }, []);
  return doc
    ? <ReadingView doc={doc} setDoc={setDoc} vocab={vocab} avatar={avatar} />
    : <Picker onOpen={setDoc} />;
}

function Picker({ onOpen }) {
  const [books, setBooks] = useState(null);
  const [error, setError] = useState("");
  const [text, setText] = useState("");
  const [title, setTitle] = useState("");
  const [note, setNote] = useState("");
  const [opening, setOpening] = useState("");

  useEffect(() => {
    getBooks().then(setBooks).catch((e) => { setBooks([]); setError(e.message); });
  }, []);

  async function openBook(b) {
    setError("");
    setOpening(b.id);
    try {
      const book = await getBook(b.id);
      onOpen({ title: book.title, sentences: book.sentences.map((s) => ({ text: s.text, status: "ready", data: s })) });
    } catch (e) {
      setError(e.message);
    } finally {
      setOpening("");
    }
  }

  async function onFile(e) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setNote("");
    if (!/\.(txt|md)$/i.test(file.name) && file.type !== "text/plain") {
      return setNote("Manibus can read plain text files (.txt or .md). For a PDF or Word file, copy the text and paste it below.");
    }
    if (file.size > MAX_FILE_BYTES) return setNote("That file is too big. Try a shorter story (under 200 KB).");
    setText(await file.text());
    setTitle(file.name.replace(/\.(txt|md)$/i, ""));
  }

  function openText() {
    let sentences = splitSentences(text);
    if (!sentences.length) return setNote("Type or paste some text first.");
    let msg = "";
    if (sentences.length > MAX_SENTENCES) {
      msg = `Reading the first ${MAX_SENTENCES} sentences.`;
      sentences = sentences.slice(0, MAX_SENTENCES);
    }
    onOpen({ title: title.trim() || "My text", note: msg, own: true, sentences: sentences.map((s) => ({ text: s, status: "pending" })) });
  }

  return (
    <div className="reader-pick">
      <section className="panel">
        <h1>Pick a story</h1>
        {error && <p role="alert" className="error">{error}</p>}
        {books === null && <p className="loading" role="status"><span className="spinner" aria-hidden="true" /> Loading stories…</p>}
        {books?.length === 0 && !error && <p>No stories yet. Add a .txt file to shared/books/.</p>}
        <div className="book-grid">
          {books?.map((b) => (
            <button key={b.id} className="book" onClick={() => openBook(b)} disabled={Boolean(opening)}>
              <span className="book-cover" aria-hidden="true">📖</span>
              <span>{opening === b.id ? "Opening…" : b.title}</span>
            </button>
          ))}
        </div>
      </section>
      <section className="panel">
        <h2>Or read your own text</h2>
        <label className="field">
          Title <span className="muted">(optional)</span>
          <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Our day at the park" />
        </label>
        <label className="field">
          Text
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={8} placeholder="Paste a story, a note from school, a recipe…" />
        </label>
        <div className="row">
          <label className="file-btn">
            Upload a .txt file
            <input type="file" accept=".txt,.md,text/plain" onChange={onFile} />
          </label>
          <button type="button" className="primary" onClick={openText} disabled={!text.trim()}>Read it in sign</button>
        </div>
        {note && <p role="status" className="muted">{note}</p>}
        <p className="muted small">Each sentence is translated as it's needed, so long texts take a little while to get ready.</p>
      </section>
    </div>
  );
}

function ReadingView({ doc, setDoc, vocab, avatar }) {
  const [cur, setCur] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [finished, setFinished] = useState(false);
  const [auto, setAuto] = useState(true);
  const [speed, setSpeed] = useState(1);
  const [playKey, setPlayKey] = useState(0);
  const [range, setRange] = useState([-1, -1]);
  const textRef = useRef(null);
  const sentences = doc.sentences;
  const s = sentences[cur];
  const ready = sentences.filter((x) => x.status === "ready").length;

  // Translate the parent's own text a couple of sentences at a time, nearest the reader first.
  useEffect(() => {
    if (!doc.own) return;
    let cancelled = false;
    const queue = sentences.map((x, i) => (x.status === "pending" || x.status === "working" ? i : -1)).filter((i) => i >= 0);
    const update = (i, patch) => !cancelled && setDoc((d) => ({ ...d, sentences: d.sentences.map((x, n) => (n === i ? { ...x, ...patch } : x)) }));
    const worker = async () => {
      while (!cancelled && queue.length) {
        const i = queue.shift();
        update(i, { status: "working" });
        try {
          update(i, { status: "ready", data: await translate(sentences[i].text) });
        } catch (e) {
          update(i, { status: "error", error: e.message });
        }
      }
    };
    for (let n = 0; n < CONCURRENCY; n++) worker();
    return () => { cancelled = true; };
  }, [doc.own, doc.retry]);

  useEffect(() => {
    textRef.current?.querySelector(`[data-i="${cur}"]`)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [cur]);

  // A sentence with nothing to sign (only filler words) is skipped after a moment.
  useEffect(() => {
    if (!playing || s.status !== "ready" || s.data.signs.length) return;
    const t = setTimeout(onSentenceDone, 900);
    return () => clearTimeout(t);
  }, [playing, cur, s.status]);

  useEffect(() => {
    const onKey = (e) => {
      if (e.target.closest("input, textarea, select, button")) return;
      if (e.key === " ") { e.preventDefault(); playing ? setPlaying(false) : play(); }
      if (e.key === "ArrowRight") go(cur + 1);
      if (e.key === "ArrowLeft") go(cur - 1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  function go(i, keepPlaying = true) {
    if (i < 0 || i >= sentences.length) return;
    setRange([-1, -1]);
    setCur(i);
    setFinished(false);
    setPlayKey((k) => k + 1);
    if (keepPlaying) setPlaying(true);
  }

  function play() {
    if (finished) go(cur);
    else setPlaying(true);
  }

  function onSentenceDone() {
    if (auto && cur + 1 < sentences.length) return go(cur + 1);
    setPlaying(false);
    setFinished(true);
  }

  function retryFailed() {
    setDoc((d) => ({ ...d, retry: (d.retry || 0) + 1, sentences: d.sentences.map((x) => (x.status === "error" ? { ...x, status: "pending", error: "" } : x)) }));
  }

  const signs = s.status === "ready" ? s.data.signs : [];
  const lit = range[0] >= 0 ? wordsForGlosses(signs.slice(range[0], range[1] + 1).map((g) => g.gloss), vocab) : new Set();

  return (
    <div className="reader">
      <div className="reader-head">
        <button type="button" onClick={() => setDoc(null)}>← All stories</button>
        <h1>{doc.title}</h1>
        <span className="muted">Sentence {cur + 1} of {sentences.length}</span>
      </div>
      {doc.note && <p className="muted">{doc.note}</p>}
      {doc.own && ready < sentences.length && (
        <p className="loading" role="status">
          <span className="spinner" aria-hidden="true" /> Getting signs ready: {ready} of {sentences.length} sentences
        </p>
      )}
      <div className="progress" aria-hidden="true"><span style={{ width: `${((cur + (finished ? 1 : 0)) / sentences.length) * 100}%` }} /></div>

      <div className="reader-cols">
        <section className="panel text-panel" ref={textRef} aria-label="Story text">
          {sentences.map((x, i) => (
            <p
              key={i}
              data-i={i}
              className={`sentence${i === cur ? " current" : ""}${x.status === "error" ? " failed" : ""}`}
              onClick={() => go(i)}
              onKeyDown={(e) => { if (e.key === "Enter") go(i); }}
              tabIndex={0}
              role="button"
              aria-current={i === cur ? "true" : undefined}
              aria-label={`Sentence ${i + 1}: ${x.text}. Play from here.`}
            >
              {i === cur
                ? tokenize(x.text).map((t, n) => <span key={n} className={t.word && lit.has(t.word) ? "word-on" : ""}>{t.text}</span>)
                : x.text}
              {(x.status === "pending" || x.status === "working") && <span className="tag">getting ready…</span>}
            </p>
          ))}
        </section>

        <section className="panel signer-panel">
          {s.status === "error" && (
            <div role="alert" className="error">
              Couldn't translate this sentence: {s.error}{" "}
              <button type="button" onClick={retryFailed}>Try again</button>{" "}
              <button type="button" onClick={() => go(cur + 1)} disabled={cur + 1 >= sentences.length}>Skip</button>
            </div>
          )}
          {(s.status === "pending" || s.status === "working") && (
            <p className="loading" role="status"><span className="spinner" aria-hidden="true" /> Translating this sentence…</p>
          )}
          <SignPlayer
            signs={signs}
            face={s.data?.face}
            emotion={s.data?.emotion}
            intensity={s.data?.intensity}
            avatar={avatar}
            playing={playing && s.status === "ready"}
            speed={speed}
            playKey={playKey}
            onStep={(from, to) => setRange([from, to])}
            onDone={onSentenceDone}
            compact
          />
          <PlayerControls
            playing={playing}
            onPlay={play}
            onPause={() => setPlaying(false)}
            onReplay={() => go(cur)}
            onPrev={() => go(cur - 1)}
            onNext={() => go(cur + 1)}
            canPrev={cur > 0}
            canNext={cur + 1 < sentences.length}
            speed={speed}
            onSpeed={setSpeed}
          />
          <label className="check">
            <input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} /> Keep going to the next sentence
          </label>
          {s.status === "ready" && (
            <div className="understood">
              <p className="badges">
                <SourceBadge source={s.data.source} unsure={s.data.unsure} />
                {s.data.face !== "statement" && <span className="badge">{s.data.face === "wh-question" ? "what/where question" : "yes/no question"}</span>}
                {s.data.emotion !== "neutral" && <span className="badge">{s.data.emotion}</span>}
              </p>
            </div>
          )}
          <p className="muted small">Tip: press space to play or pause, ← → to move between sentences, or tap any sentence.</p>
        </section>
      </div>
    </div>
  );
}
