// Reads the parent's facial expression from the camera and turns it into the 7 emotion scores
// /translate accepts as `face_emotions`. Same rules as backend/dev.html, relative to the parent's own
// neutral face. Nothing leaves the browser except the scores (and photos, only if the parent opts in).
import { FaceLandmarker, FilesetResolver } from "@mediapipe/tasks-vision";

const WASM = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.35/wasm";
const MODEL = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task";
const GAIN = 3; // blendshape changes from a neutral face are small (often 0.1-0.3); scale before the rules
const TICK_MS = 100;

let landmarker = null;
let video = null, timer = null, onScoresCb = null;
let latest = null, neutral = {}, calibrating = null, neutralJpg = null;
let sampling = false, samples = [], ticks = 0, peaks = [], wantPhotos = false;

async function loadModel() {
  if (landmarker) return landmarker;
  const files = await FilesetResolver.forVisionTasks(WASM);
  const opts = { outputFaceBlendshapes: true, runningMode: "VIDEO", numFaces: 1 };
  try {
    landmarker = await FaceLandmarker.createFromOptions(files, { baseOptions: { modelAssetPath: MODEL, delegate: "GPU" }, ...opts });
  } catch {
    landmarker = await FaceLandmarker.createFromOptions(files, { baseOptions: { modelAssetPath: MODEL, delegate: "CPU" }, ...opts });
  }
  return landmarker;
}

const avg = (b, ...names) => names.reduce((a, n) => a + (b[n] || 0), 0) / names.length;
const clamp = (x) => Math.min(1, Math.max(0, x));

function cuesOf(raw) {
  const d = {};
  for (const [k, v] of Object.entries(raw)) d[k] = clamp((v - (neutral[k] || 0)) * GAIN);
  return {
    browDown: avg(d, "browDownLeft", "browDownRight"),
    browInnerUp: d.browInnerUp || 0,
    browOuterUp: avg(d, "browOuterUpLeft", "browOuterUpRight"),
    eyeSquint: avg(d, "eyeSquintLeft", "eyeSquintRight"),
    eyeWide: avg(d, "eyeWideLeft", "eyeWideRight"),
    noseSneer: avg(d, "noseSneerLeft", "noseSneerRight"),
    mouthPress: avg(d, "mouthPressLeft", "mouthPressRight"),
    mouthFrown: avg(d, "mouthFrownLeft", "mouthFrownRight"),
    mouthStretch: avg(d, "mouthStretchLeft", "mouthStretchRight"),
    upperLipUp: avg(d, "mouthUpperUpLeft", "mouthUpperUpRight"),
    smile: avg(d, "mouthSmileLeft", "mouthSmileRight"),
    cheekSquint: avg(d, "cheekSquintLeft", "cheekSquintRight"),
    jawOpen: d.jawOpen || 0,
  };
}

// Brows carry most of the signal for the hard emotions: down = anger, inner-up alone = sadness, all up = surprise/fear.
function emotionsOf(c) {
  const e = {
    angry: clamp(0.45 * c.browDown + 0.2 * c.eyeSquint + 0.15 * c.mouthPress + 0.1 * c.noseSneer + 0.1 * c.mouthFrown - 0.3 * c.smile),
    sad: clamp(0.45 * Math.max(0, c.browInnerUp - 0.6 * c.browOuterUp) + 0.4 * c.mouthFrown + 0.15 * c.mouthPress - 0.3 * c.smile),
    surprised: clamp(0.35 * c.browOuterUp + 0.15 * c.browInnerUp + 0.25 * c.eyeWide + 0.25 * c.jawOpen - 0.3 * c.browDown),
    fearful: clamp(0.3 * c.browInnerUp + 0.15 * c.browOuterUp + 0.3 * c.eyeWide + 0.25 * c.mouthStretch - 0.3 * c.browDown),
    disgusted: clamp(0.45 * c.noseSneer + 0.3 * c.upperLipUp + 0.25 * c.browDown - 0.3 * c.smile),
    happy: clamp(0.65 * c.smile + 0.35 * c.cheekSquint),
  };
  e.neutral = clamp(1 - 3 * Math.max(...Object.values(e))); // neutral only when nothing else is showing
  return normalize(e);
}

function normalize(e) {
  const total = Object.values(e).reduce((a, b) => a + b, 0) || 1;
  for (const k in e) e[k] = Math.round((e[k] / total) * 1000) / 1000;
  return e;
}

function snap() { // small JPEG of the current frame, base64 without the data: prefix
  if (!video?.videoWidth) return null;
  const c = document.createElement("canvas");
  c.width = 256;
  c.height = Math.round((256 * video.videoHeight) / video.videoWidth);
  c.getContext("2d").drawImage(video, 0, 0, c.width, c.height);
  return c.toDataURL("image/jpeg", 0.75).split(",")[1];
}

function considerPeak(emo) { // keep the 3 most expressive moments, at least 300 ms apart
  const score = Math.max(...Object.entries(emo).filter(([k]) => k !== "neutral").map(([, v]) => v)) + 0.001;
  const now = performance.now();
  const near = peaks.findIndex((p) => Math.abs(p.t - now) < 300);
  if (near >= 0) { if (score > peaks[near].score) peaks[near] = { t: now, score, jpg: snap() }; return; }
  if (peaks.length < 3) { peaks.push({ t: now, score, jpg: snap() }); return; }
  const low = peaks.reduce((m, p, i) => (p.score < peaks[m].score ? i : m), 0);
  if (score > peaks[low].score) peaks[low] = { t: now, score, jpg: snap() };
}

function tick() {
  if (!video || video.readyState < 2) return;
  const res = landmarker.detectForVideo(video, performance.now());
  const shapes = res.faceBlendshapes?.[0];
  if (sampling) ticks++;
  if (!shapes) { latest = null; onScoresCb?.(null); return; }
  const raw = Object.fromEntries(shapes.categories.map((c) => [c.categoryName, c.score]));
  if (calibrating) calibrating.push(raw);
  latest = emotionsOf(cuesOf(raw));
  if (sampling) { samples.push(latest); if (wantPhotos) considerPeak(latest); }
  onScoresCb?.(latest);
}

// Starts reading faces from a playing <video>. onScores(scores | null) fires about 10 times a second.
export async function startFaceEmotion(videoEl, onScores, signal) {
  await loadModel();
  if (signal?.aborted) return;
  stopFaceEmotion();
  video = videoEl;
  onScoresCb = onScores;
  resumeFaceEmotion();
}

export function pauseFaceEmotion() {
  if (video && timer === null) tick();
  clearInterval(timer);
  timer = null;
  return latest;
}

export function resumeFaceEmotion() {
  if (video && timer === null) timer = setInterval(tick, TICK_MS);
}

export function stopFaceEmotion() {
  clearInterval(timer);
  timer = null; video = null; latest = null; sampling = false;
}

export const faceRunning = () => timer !== null;
export const currentFaceScores = () => latest;
export const hasNeutralFace = () => Object.keys(neutral).length > 0;
export const neutralFaceFrame = () => neutralJpg;

// Collects 2 seconds of the parent's relaxed face as the baseline. Resolves true if a face was seen.
export function recordNeutralFace() {
  const got = (calibrating = []);
  return new Promise((resolve) => {
    setTimeout(() => {
      if (calibrating !== got) return resolve(false); // a newer press restarted calibration
      calibrating = null;
      if (!got.length) return resolve(false);
      neutral = {};
      for (const r of got) for (const [k, v] of Object.entries(r)) neutral[k] = (neutral[k] || 0) + v / got.length;
      neutralJpg = snap();
      resolve(true);
    }, 2000);
  });
}

// Call when the parent starts talking; photos are only kept if the parent opted in.
export function beginSentence({ photos = false } = {}) {
  samples = []; peaks = []; ticks = 0; wantPhotos = photos; sampling = true;
}

// Call when the parent stops. Returns { faceEmotions, frames, neutralFrame }; faceEmotions is null
// when a face was seen in fewer than half the frames, since then the scores would mislead.
export function endSentence() {
  sampling = false;
  const frames = peaks.map((p) => p.jpg).filter(Boolean);
  if (!samples.length || samples.length < ticks / 2) return { faceEmotions: null, frames, neutralFrame: neutralJpg };
  // Expressions are brief, so take each score's 75th percentile (its strong moments), then renormalize.
  const out = {};
  for (const k of Object.keys(samples[0])) {
    if (k === "neutral") continue;
    const v = samples.map((s) => s[k]).sort((a, b) => a - b);
    out[k] = v[Math.min(v.length - 1, Math.floor(v.length * 0.75))];
  }
  out.neutral = Math.max(0, 1 - 3 * Math.max(...Object.values(out)));
  return { faceEmotions: normalize(out), frames, neutralFrame: neutralJpg };
}

// One snapshot right now, for typed sentences when the parent opted in to photos.
export const snapFace = () => snap();
