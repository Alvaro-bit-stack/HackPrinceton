// The only place the frontend talks to the backend. Shapes are defined in CONTRACT.md.
const BASE = import.meta.env.VITE_API ?? "http://localhost:8000";

async function post(path, body) {
  const res = await fetch(BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${path} failed with ${res.status}`);
  return res.json();
}

// emotion is optional: pass the speaker's tone when you know it, e.g. translate("Stop!", "angry")
export const translate = (text, emotion) => post("/translate", { text, emotion });
export const recognize = (frames) => post("/recognize", { frames });
export const getVocab = () => fetch(BASE + "/vocab").then((r) => r.json());
export const getBooks = () => fetch(BASE + "/books").then((r) => r.json());
export const getBook = (id) => fetch(`${BASE}/books/${encodeURIComponent(id)}`).then((r) => r.json());
