import { useEffect, useRef, useState } from "react";
import { correct, getFamily, translate } from "../api.js";
import SignPlayer from "../components/SignPlayer.jsx";
import PlayerControls from "../components/PlayerControls.jsx";
import { SourceBadge } from "../components/Badges.jsx";
import {
  beginSentence, currentFaceScores, endSentence, hasNeutralFace, neutralFaceFrame, recordNeutralFace, snapFace, startFaceEmotion, stopFaceEmotion,
} from "../lib/faceEmotion.js";
import { canListen, startListening } from "../lib/speech.js";
import { releaseVoice, resetVoiceBaseline, startVoice, stopVoice } from "../lib/voice.js";

const EMOTIONS = ["neutral", "happy", "sad", "angry", "surprised", "worried"];
const EMOJI = { neutral: "😐", happy: "😊", sad: "😢", angry: "😠", surprised: "😮", worried: "😟", fearful: "😨", disgusted: "🤢" };

// Main goal: the parent speaks (or types) and the app signs it, with the feeling in their face and voice.
export default function Translator({ avatar }) {
  const [text, setText] = useState("");
  const [heard, setHeard] = useState("");
  const [listening, setListening] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const [sent, setSent] = useState("");
  const [feeling, setFeeling] = useState(""); // "" = let the app decide
  const [members, setMembers] = useState([]);
  const [speaker, setSpeaker] = useState("");
  const [useVoice, setUseVoice] = useState(true);
  const [playing, setPlaying] = useState(true);
  const [done, setDone] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [playKey, setPlayKey] = useState(0);
  const [fixing, setFixing] = useState(false);
  const cam = useCameraFace();
  const session = useRef(null);

  useEffect(() => {
    getFamily().then((f) => setMembers(f.members || [])).catch(() => {});
    return () => { session.current?.stop(); releaseVoice(); };
  }, []);

  async function send(sentence, extra = {}) {
    const clean = sentence.trim();
    if (!clean) return;
    if (clean.length > 300) return setError("That's a lot at once. Keep it under 300 characters, or use the Reader for longer text.");
    setText(clean);
    setSent(clean);
    setError("");
    setFixing(false);
    setBusy(true);
    try {
      const r = await translate(clean, { emotion: feeling || undefined, speaker: speaker || undefined, ...extra });
      setResult(r);
      setDone(false);
      setPlaying(true);
      setPlayKey((k) => k + 1);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  function sendTyped() {
    const extra = {};
    if (cam.on) {
      const now = currentFaceScores();
      if (now) extra.faceEmotions = now;
      if (cam.photos) { const jpg = snapFace(); if (jpg) extra.faceFrames = [jpg]; extra.faceNeutral = neutralFaceFrame(); }
    }
    send(text, extra);
  }

  async function toggleMic() {
    if (listening) return session.current?.stop();
    setError("");
    setHeard("");
    if (cam.on) beginSentence({ photos: cam.photos });
    const voiceOn = useVoice && (await startVoice());
    session.current = startListening({
      onInterim: setHeard,
      onError: (msg) => setError(msg),
      onEnd: (finalText) => {
        setListening(false);
        session.current = null;
        const voice = voiceOn ? stopVoice() : {};
        const face = cam.on ? endSentence() : null;
        if (!finalText) return;
        setHeard(finalText);
        send(finalText, {
          loudness: voice.loudness, pitch: voice.pitch,
          faceEmotions: face?.faceEmotions || undefined,
          faceFrames: cam.photos ? face?.frames : undefined,
          faceNeutral: cam.photos ? face?.neutralFrame : undefined,
        });
      },
    });
    if (session.current) setListening(true);
    else if (voiceOn) stopVoice();
  }

  async function applyFix(meaning, emotion) {
    setBusy(true);
    setError("");
    try {
      setResult(await correct(sent, { meaning, emotion }));
      setFixing(false);
      setDone(false);
      setPlaying(true);
      setPlayKey((k) => k + 1);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="speak">
      <section className="panel input-panel">
        <h1>Say it, and Manibus signs it</h1>
        <div className="mic-row">
          <button
            className={`mic${listening ? " live" : ""}`}
            onClick={toggleMic}
            disabled={!canListen || busy}
            aria-pressed={listening}
            aria-label={listening ? "Stop listening" : "Start listening"}
          >
            <span aria-hidden="true">{listening ? "■" : "🎤"}</span>
          </button>
          <div className="mic-help">
            {!canListen ? (
              <p>This browser can't listen. Use Chrome or Edge, or type below.</p>
            ) : listening ? (
              <p><strong>Listening…</strong> tap again when you're done.</p>
            ) : (
              <p>Tap the microphone and talk to your child like you normally would.</p>
            )}
            {heard && <p className="heard" aria-live="polite">“{heard}”</p>}
          </div>
        </div>

        <form className="type-row" onSubmit={(e) => { e.preventDefault(); sendTyped(); }}>
          <label htmlFor="say" className="sr-only">What you want to say</label>
          <input id="say" value={text} maxLength={300} onChange={(e) => setText(e.target.value)} placeholder="Or type: Do you want more milk?" />
          <button type="submit" className="primary" disabled={busy || !text.trim()}>Sign it</button>
        </form>

        <fieldset className="feelings">
          <legend>How do you feel saying it? <span className="muted">(optional)</span></legend>
          <button type="button" aria-pressed={feeling === ""} onClick={() => setFeeling("")}>✨ Let Manibus tell</button>
          {EMOTIONS.map((e) => (
            <button type="button" key={e} aria-pressed={feeling === e} onClick={() => setFeeling(e)}>{EMOJI[e]} {e}</button>
          ))}
        </fieldset>

        <details className="options">
          <summary>Face, voice and family options</summary>
          <FaceOptions cam={cam} />
          <label className="check">
            <input type="checkbox" checked={useVoice} onChange={(e) => setUseVoice(e.target.checked)} />
            Use how loud and high my voice is to set how strongly it's signed (audio never leaves this device)
          </label>
          <button type="button" className="link" onClick={resetVoiceBaseline}>Reset my normal voice level</button>
          {members.length > 0 && (
            <label className="field">
              Who's talking?
              <select value={speaker} onChange={(e) => setSpeaker(e.target.value)}>
                <option value="">Not saying</option>
                {members.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
              </select>
            </label>
          )}
        </details>
      </section>

      <section className="panel output-panel" aria-busy={busy}>
        {error && <p role="alert" className="error">{error}</p>}
        {busy && <p className="loading" role="status"><span className="spinner" aria-hidden="true" /> Translating… (Manibus translates, then double-checks)</p>}
        <SignPlayer
          signs={result?.signs || []}
          face={result?.face}
          emotion={result?.emotion}
          intensity={result?.intensity}
          newSigns={result?.new_signs}
          avatar={avatar}
          playing={playing}
          speed={speed}
          playKey={playKey}
          onDone={() => { setPlaying(false); setDone(true); }}
        />
        {result && (
          <>
            <PlayerControls
              playing={playing}
              onPlay={() => { if (done) { setDone(false); setPlayKey((k) => k + 1); } setPlaying(true); }}
              onPause={() => setPlaying(false)}
              onReplay={() => { setDone(false); setPlaying(true); setPlayKey((k) => k + 1); }}
              speed={speed}
              onSpeed={setSpeed}
            />
            <div className="understood">
              <p><span className="muted">Manibus understood:</span> <strong>{result.meaning}</strong></p>
              <p className="badges">
                <SourceBadge source={result.source} unsure={result.unsure} />
                <span className="badge">{EMOJI[result.emotion] || ""} {result.emotion}</span>
                {typeof result.intensity === "number" && (
                  <span className="badge" title={result.tone_reason || ""}>
                    strength <span className="meter"><span style={{ width: `${Math.round(result.intensity * 100)}%` }} /></span>
                  </span>
                )}
              </p>
              {result.new_signs?.length > 0 && (
                <p className="new-note">🌱 New for your family: {result.new_signs.join(", ")}. Great way to grow your child's words!</p>
              )}
              {!fixing ? (
                <button type="button" onClick={() => setFixing(true)} disabled={busy}>That's not what I meant</button>
              ) : (
                <FixForm initial={result} onCancel={() => setFixing(false)} onSubmit={applyFix} busy={busy} />
              )}
            </div>
          </>
        )}
      </section>
    </div>
  );
}

function FixForm({ initial, onSubmit, onCancel, busy }) {
  const [meaning, setMeaning] = useState("");
  const [emotion, setEmotion] = useState(initial.emotion || "");
  const changed = meaning.trim() || (emotion && emotion !== initial.emotion);
  return (
    <form className="fix" onSubmit={(e) => { e.preventDefault(); if (changed) onSubmit(meaning, emotion !== initial.emotion ? emotion : undefined); }}>
      <label className="field">
        What did you mean?
        <input value={meaning} maxLength={300} onChange={(e) => setMeaning(e.target.value)} placeholder="e.g. I'm surprised, not proud" />
      </label>
      <label className="field">
        How did you feel?
        <select value={emotion} onChange={(e) => setEmotion(e.target.value)}>
          {EMOTIONS.map((e) => <option key={e} value={e}>{EMOJI[e]} {e}</option>)}
        </select>
      </label>
      <p>
        <button type="submit" className="primary" disabled={busy || !changed}>Fix it</button>{" "}
        <button type="button" onClick={onCancel}>Cancel</button>
      </p>
      <p className="muted small">Manibus remembers this for next time. Corrections to the signs themselves go to a fluent signer.</p>
    </form>
  );
}

// Camera + face-reading state for the Speak page. Off until the parent turns it on.
function useCameraFace() {
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const [on, setOn] = useState(false);
  const [state, setState] = useState(""); // status line
  const [live, setLive] = useState(null);
  const [photos, setPhotos] = useState(false);

  async function start() {
    setState("Starting the camera and face reader…");
    try {
      streamRef.current = await navigator.mediaDevices.getUserMedia({ video: true });
      videoRef.current.srcObject = streamRef.current;
      await videoRef.current.play();
      await startFaceEmotion(videoRef.current, setLive);
      setOn(true);
      setState(hasNeutralFace() ? "" : "Tip: press “Record my neutral face” first so I can read you better.");
    } catch (e) {
      stop();
      setState(e?.name === "NotAllowedError" ? "The camera is blocked. Allow it in the browser to use face reading." : `Face reading isn't available: ${e?.message || e}`);
    }
  }
  function stop() {
    stopFaceEmotion();
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    setOn(false);
    setLive(null);
  }
  async function calibrate() {
    setState("Hold a relaxed, neutral face for 2 seconds…");
    const ok = await recordNeutralFace();
    setState(ok ? "Got it! Your neutral face is recorded." : "I couldn't see your face. Try again facing the camera.");
  }
  useEffect(() => () => stop(), []);
  return { videoRef, on, state, live, photos, setPhotos, start, stop, calibrate };
}

function FaceOptions({ cam }) {
  const top = cam.live && Object.entries(cam.live).sort((a, b) => b[1] - a[1])[0];
  return (
    <div className="face-opts">
      <label className="check">
        <input type="checkbox" checked={cam.on} onChange={(e) => (e.target.checked ? cam.start() : cam.stop())} />
        Read my face with the camera to sign the feeling too (only emotion scores are sent)
      </label>
      <div className={cam.on ? "face-live" : "face-live hidden"}>
        <video ref={cam.videoRef} className="webcam small" muted playsInline aria-label="Your camera" />
        {cam.on && (
          <div>
            <p aria-live="polite">{top ? <>I see: <strong>{EMOJI[top[0]]} {top[0]}</strong></> : "Looking for your face…"}</p>
            <button type="button" onClick={cam.calibrate}>Record my neutral face</button>
            <label className="check">
              <input type="checkbox" checked={cam.photos} onChange={(e) => cam.setPhotos(e.target.checked)} />
              Also send up to 3 face snapshots to the AI for a better read (never stored)
            </label>
          </div>
        )}
      </div>
      {cam.state && <p className="muted small">{cam.state}</p>}
    </div>
  );
}
