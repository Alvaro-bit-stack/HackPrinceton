// Measures how loud and how high the parent spoke, compared with their own normal voice, as the
// -1..1 `loudness` and `pitch` that /translate accepts. Audio never leaves the browser.
// Same method as backend/dev.html: the first sentence sets the baseline (mics differ, so absolute volume means nothing).
import { PitchDetector } from "pitchy";

let audio = null, levels = [], pitches = [], running = false;
let baselineDb = null, baselinePitch = null;

export async function startVoice() {
  levels = []; pitches = []; running = true;
  try {
    if (!audio) {
      const ctx = new AudioContext();
      const mic = await navigator.mediaDevices.getUserMedia({ audio: true });
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 2048;
      ctx.createMediaStreamSource(mic).connect(analyser);
      audio = { ctx, mic, analyser, buf: new Float32Array(analyser.fftSize), timer: null, detector: PitchDetector.forFloat32Array(analyser.fftSize) };
    }
    await audio.ctx.resume();
    if (!running || audio.timer) return true; // stopped before the mic was ready
    audio.timer = setInterval(() => {
      audio.analyser.getFloatTimeDomainData(audio.buf);
      let sum = 0;
      for (const x of audio.buf) sum += x * x;
      const db = 10 * Math.log10(sum / audio.buf.length + 1e-12);
      if (db > -55) { // fixed noise gate: a very noisy room counts as speech
        levels.push(db);
        const [hz, clarity] = audio.detector.findPitch(audio.buf, audio.ctx.sampleRate);
        if (clarity > 0.9 && hz > 70 && hz < 500) pitches.push(hz); // voiced frames in human speaking range
      }
    }, 100);
    return true;
  } catch {
    return false;
  }
}

// Returns { loudness, pitch }; either is null when too little speech was heard.
export function stopVoice() {
  running = false;
  if (audio?.timer) { clearInterval(audio.timer); audio.timer = null; }
  if (levels.length < 3) return { loudness: null, pitch: null };
  const db = levels.reduce((a, b) => a + b, 0) / levels.length;
  if (baselineDb === null) baselineDb = db;
  const loudness = Math.max(-1, Math.min(1, Math.round(((db - baselineDb) / 12) * 100) / 100)); // ~12 dB louder = 1
  let pitch = null;
  if (pitches.length >= 3) {
    const hz = pitches.slice().sort((a, b) => a - b)[Math.floor(pitches.length / 2)]; // median resists octave errors
    if (baselinePitch === null) baselinePitch = hz;
    pitch = Math.max(-1, Math.min(1, Math.round(((12 * Math.log2(hz / baselinePitch)) / 6) * 100) / 100)); // ~6 semitones = 1
  }
  return { loudness, pitch };
}

export function resetVoiceBaseline() {
  baselineDb = null;
  baselinePitch = null;
}

// Frees the microphone, e.g. when leaving the page.
export function releaseVoice() {
  stopVoice();
  audio?.mic.getTracks().forEach((t) => t.stop());
  audio?.ctx.close();
  audio = null;
}
