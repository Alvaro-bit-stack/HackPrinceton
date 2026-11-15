// The only place the frontend talks to the backend. Shapes are defined in CONTRACT.md.
const BASE = import.meta.env.VITE_API ?? "http://localhost:8000";

// The backend explains a 422 in `detail`: a string for its own checks, a list for FastAPI's type checks.
function detailText(detail) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((d) => d.msg || JSON.stringify(d)).join("; ");
  return "";
}

async function request(path, options) {
  let res;
  try {
    res = await fetch(BASE + path, options);
  } catch {
    throw new Error("Can't reach the Manibus server. Is the backend running on port 8000?");
  }
  if (!res.ok) {
    let why = "";
    try { why = detailText((await res.json()).detail); } catch { /* body wasn't JSON */ }
    throw new Error(why || `The server answered ${res.status} for ${path}.`);
  }
  return res.json();
}

const post = (path, body) =>
  request(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

// opts: { emotion, faceEmotions, loudness, pitch, speaker, faceFrames, faceNeutral }; unset ones are left out.
export function translate(text, opts = {}) {
  const body = { text };
  if (opts.emotion) body.emotion = opts.emotion;
  if (opts.faceEmotions) body.face_emotions = opts.faceEmotions;
  if (opts.loudness != null) body.loudness = opts.loudness;
  if (opts.pitch != null) body.pitch = opts.pitch;
  if (opts.speaker) body.speaker = opts.speaker;
  if (opts.faceFrames?.length) body.face_frames = opts.faceFrames;
  if (opts.faceNeutral) body.face_neutral = opts.faceNeutral;
  return post("/translate", body);
}

// The parent fixes what the app understood: send a new meaning, a new emotion, or both.
export function correct(text, { meaning, emotion } = {}) {
  const body = { text };
  if (meaning?.trim()) body.meaning = meaning.trim();
  if (emotion) body.emotion = emotion;
  return post("/corrections", body);
}

export const recognize = (frames) => post("/recognize", { frames });
export const getVocab = () => request("/vocab");
export const getBooks = () => request("/books");
export const getBook = (id) => request(`/books/${encodeURIComponent(id)}`);
export const getFamily = () => request("/family");
export const getHealth = () => request("/health");
