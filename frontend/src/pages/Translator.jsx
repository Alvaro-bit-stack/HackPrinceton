
import { useEffect, useRef, useState } from "react";
import { getFamily, translate } from "../api.js";
import SignPlayer from "../components/SignPlayer.jsx";
import PlayerControls, { AslSpeedSlider } from "../components/PlayerControls.jsx";

import {
  beginSentence,
  endSentence,
  faceRunning,
  neutralFaceFrame,
  pauseFaceEmotion,
  recordNeutralFace,
  resumeFaceEmotion,
  snapFace,
  startFaceEmotion,
  stopFaceEmotion,
} from "../lib/faceEmotion.js";

import { canListen, startListening } from "../lib/speech.js";

import { releaseVoice, startVoice, stopVoice } from "../lib/voice.js";

function capitalize(value) {
  if (!value) return "";
  return value.charAt(0).toUpperCase() + value.slice(1);
}

// All icons are SVGs. No emoji assets required.
function Icon({ name, size = 22 }) {
  const paths = {
    mic: (
      <>
        <rect x="9" y="2" width="6" height="12" rx="3" />
        <path d="M5 10a7 7 0 0 0 14 0" />
        <path d="M12 17v5M8 22h8" />
      </>
    ),
    arrow: <path d="M5 12h14m-6-6 6 6-6 6" />,
    camera: (
      <>
        <path d="M3 7h4l2-3h6l2 3h4v13H3V7Z" />
        <circle cx="12" cy="13" r="4" />
      </>
    ),
  };

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {paths[name]}
    </svg>
  );
}

export default function Translator({ avatar = "signer_glasses" }) {
  const [text, setText] = useState("");
  const [listening, setListening] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);

  const [members, setMembers] = useState([]);
  const [speaker, setSpeaker] = useState("");

  const [playing, setPlaying] = useState(true);
  const [done, setDone] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [playKey, setPlayKey] = useState(0);

  const cam = useCameraFace();
  const session = useRef(null);
  const messageInputRef = useRef(null);

  useEffect(() => {
    if (!listening) return;

    const input = messageInputRef.current;
    input.scrollTop = input.scrollHeight;
  }, [listening, text]);

  useEffect(() => {
    getFamily()
      .then((family) => setMembers(family.members || []))
      .catch(() => {});

    return () => {
      const recording = session.current;
      session.current = null;
      recording?.stop();
      releaseVoice();
    };
  }, []);

  async function send(sentence, extra = {}) {
    const clean = String(sentence || "").trim();

    if (!clean) return;

    if (clean.length > 300) {
      setError(
        "Please keep your message under 300 characters. Use Reader for longer text."
      );
      return;
    }

    setError("");
    setBusy(true);

    try {
      const response = await translate(clean, {
        speaker: speaker || undefined,
        ...extra,
      });

      setResult(response);
      setDone(false);
      setPlaying(true);
      setPlayKey((key) => key + 1);
    } catch (err) {
      setError(err?.message || "Translation failed. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  function sendMessage() {
    const extra = {};

    if (cam.ready) {
      const scores = cam.captureEmotion();

      if (scores) {
        extra.faceEmotions = scores;
      }

      const image = snapFace();
      if (image) {
        extra.faceFrames = [image];
        extra.faceNeutral = neutralFaceFrame();
      }
    }

    send(text, extra);
  }

  function finishRecording() {
    if (faceRunning()) cam.captureEmotion();
    session.current?.stop();
  }

  async function toggleMic() {
    if (listening) {
      finishRecording();
      return;
    }

    setError("");
    cam.resumeEmotion();

    const voiceOn = await startVoice();
    const cameraStream = cam.ready ? cam.videoRef.current?.srcObject : null;

    if (cameraStream) {
      beginSentence({ photos: true });
    }

    session.current = startListening({
      onInterim: setText,

      onError: (message) => {
        setError(message);
      },

      onEnd: (finalText) => {
        if (!session.current) return;

        setListening(false);
        session.current = null;

        const voice = voiceOn ? stopVoice() : {};
        if (finalText && faceRunning()) cam.captureEmotion();

        const face = cameraStream && cam.videoRef.current?.srcObject === cameraStream
          ? endSentence()
          : null;

        if (!finalText) {
          cam.resumeEmotion();
          return;
        }

        setText(finalText);

        send(finalText, {
          loudness: voice.loudness,
          pitch: voice.pitch,
          faceEmotions: face?.faceEmotions || undefined,
          faceFrames: face?.frames,
          faceNeutral: face?.neutralFrame,
        });
      },
    });

    if (session.current) {
      setListening(true);
    } else if (voiceOn) {
      stopVoice();
    }
  }

  return (
    <div className="manibus-translate-page">
      <header className="manibus-page-header">
        <h1>Translate to ASL.</h1>
      </header>

      <div className="speak manibus-workspace">
        {/* LEFT PANEL */}
        <section className="panel input-panel manibus-panel">
          <div className="manibus-panel-heading">
            <div>
              <span className="manibus-section-label">
                YOUR MESSAGE
              </span>
              <h2>What would you like to say?</h2>
            </div>
          </div>

          <div className="manibus-mic-section">
            <button
              type="button"
              className={`mic manibus-mic ${listening ? "live" : ""}`}
              onClick={toggleMic}
              disabled={!canListen || busy}
              aria-pressed={listening}
              aria-label={
                listening ? "Stop listening" : "Start listening"
              }
            >
              {listening ? (
                <span
                  className="manibus-stop-icon"
                  aria-hidden="true"
                />
              ) : (
                <Icon name="mic" size={25} />
              )}
            </button>

            <div className="manibus-mic-copy">
              <strong>
                {listening ? "Listening to you..." : "Speak naturally"}
              </strong>

              <p>
                {!canListen
                  ? "Voice input isn't supported here. Please type your message."
                  : listening
                    ? "Select Translate to ASL when you’re done."
                    : "Tap the microphone to start."}
              </p>
            </div>
          </div>

          <form
            className="manibus-message-form"
            onSubmit={(event) => {
              event.preventDefault();
              if (busy) return;

              if (listening) {
                finishRecording();
              } else {
                sendMessage();
              }
            }}
          >
            <CameraPreview cam={cam}>
              <div className="manibus-message-entry">
                <div className="manibus-message-label">
                  <label htmlFor="say">Message</label>
                  <span>{text.length} / 300</span>
                </div>
                <textarea
                  ref={messageInputRef}
                  id="say"
                  className="manibus-message-input"
                  value={text}
                  maxLength={300}
                  readOnly={listening}
                  onChange={(event) => {
                    setText(event.target.value);
                    cam.resumeEmotion();
                  }}
                  placeholder={listening ? "Listening…" : "Speak or type your message"}
                  rows={2}
                />
              </div>
            </CameraPreview>

            <button
              type="submit"
              className="primary manibus-submit"
              disabled={busy || (!listening && !text.trim())}
            >
              {busy ? "Translating..." : "Translate to ASL"}
              <Icon name="arrow" size={18} />
            </button>
          </form>

          {members.length > 0 && (
            <label className="field manibus-speaker">
              Who's speaking?
              <select
                value={speaker}
                onChange={(event) => setSpeaker(event.target.value)}
              >
                <option value="">Not specified</option>

                {members.map((member) => (
                  <option key={member.id} value={member.id}>
                    {member.name}
                  </option>
                ))}
              </select>
            </label>
          )}
        </section>

        {/* RIGHT PANEL: 3D GLASSES AVATAR */}
        <section
          className="panel output-panel manibus-panel manibus-output"
          aria-busy={busy}
        >
          <div className="manibus-panel-heading">
            <div>
              <span className="manibus-section-label">
                VISUAL TRANSLATION
              </span>
              <h2>ASL Interpreter</h2>
            </div>

            <span className="manibus-avatar-tag">
              3D SIGNER
            </span>
          </div>

          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}

          {busy && (
            <p className="loading" role="status">
              <span
                className="spinner"
                aria-hidden="true"
              />
              Preparing your translation...
            </p>
          )}

          <div className="manibus-signing-area">
            <SignPlayer
              signs={result?.signs || []}
              face={result?.face}
              emotion={result?.emotion}
              intensity={result?.intensity}
              avatar={avatar}
              playing={playing}
              speed={speed}
              playKey={playKey}
              onDone={() => {
                setPlaying(false);
                setDone(true);
              }}
            />
          </div>

          <AslSpeedSlider speed={speed} onSpeed={setSpeed} id="translate-asl-speed" />

          {result && (
            <div className="manibus-translation-details">
              <PlayerControls
                playing={playing}
                onPlay={() => {
                  if (done) {
                    setDone(false);
                    setPlayKey((key) => key + 1);
                  }
                  setPlaying(true);
                }}
                onPause={() => setPlaying(false)}
                onReplay={() => {
                  setDone(false);
                  setPlaying(true);
                  setPlayKey((key) => key + 1);
                }}
              />
            </div>
          )}

          <div className="manibus-avatar-footer">
            <span className="manibus-ready-dot" />
            <span>
              {busy
                ? "Translation in progress"
                : result
                  ? "Translation ready"
                  : "Ready to translate"}
            </span>
          </div>
        </section>
      </div>
    </div>
  );
}

function useCameraFace() {
  const videoRef = useRef(null);
  const [on, setOn] = useState(false);
  const [ready, setReady] = useState(false);
  const [state, setState] = useState("Starting camera…");
  const [live, setLive] = useState(null);
  const [captured, setCaptured] = useState(false);

  useEffect(() => {
    const video = videoRef.current;
    const controller = new AbortController();
    const { signal } = controller;
    let stream;
    let previewPlaying = false;

    function stopStream() {
      stream?.getTracks().forEach((track) => track.stop());
      if (video.srcObject === stream) video.srcObject = null;
    }

    async function connectCamera() {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: true });
        if (signal.aborted) {
          stopStream();
          return;
        }

        video.srcObject = stream;
        await video.play();
        if (signal.aborted) return;

        previewPlaying = true;
        setOn(true);
        setState("Starting emotion detection…");
        await startFaceEmotion(video, setLive, signal);
        if (signal.aborted) return;

        setReady(true);
        setState("");
      } catch (error) {
        if (signal.aborted) return;

        if (previewPlaying) {
          setState("Emotion detection is unavailable.");
        } else {
          stopStream();
          setState(error?.name === "NotAllowedError"
            ? "Camera blocked. Allow access in your browser and reopen Translate."
            : "Camera unavailable.");
        }
      }
    }

    connectCamera();

    return () => {
      controller.abort();
      stopFaceEmotion();
      stopStream();
    };
  }, []);

  function captureEmotion() {
    const scores = pauseFaceEmotion();
    setLive(scores);
    setCaptured(true);
    return scores;
  }

  function resumeEmotion() {
    resumeFaceEmotion();
    setCaptured(false);
  }

  async function calibrate() {
    resumeEmotion();
    setState("Hold a relaxed expression for two seconds…");
    const success = await recordNeutralFace();
    setState(success
      ? "Neutral face recorded."
      : "Couldn't detect your face. Please try again.");
  }

  return { videoRef, on, ready, state, live, captured, captureEmotion, resumeEmotion, calibrate };
}

function CameraPreview({ cam, children }) {
  const top = cam.live && Object.entries(cam.live).sort((a, b) => b[1] - a[1])[0];

  return (
    <div className="manibus-camera">
      <div className="manibus-capture">
        <div className="manibus-camera-preview">
          <video
            ref={cam.videoRef}
            className="webcam"
            muted
            playsInline
            aria-label="Camera preview"
          />
          {!cam.on && (
            <p className="manibus-camera-placeholder" role="status">
              <Icon name="camera" size={20} />
              {cam.state}
            </p>
          )}
        </div>

        {children}
      </div>

      {cam.on && (
        <div className="manibus-camera-controls">
          {cam.ready && (
            <>
              <span>
                {cam.captured
                  ? `Captured emotion: ${top ? capitalize(top[0]) : "No face detected"}`
                  : top
                    ? `Detected emotion: ${capitalize(top[0])}`
                    : "Looking for your face."}
              </span>
              <button type="button" onClick={cam.calibrate}>Record neutral face</button>
            </>
          )}
          {cam.state && <p className="manibus-camera-status" role="status">{cam.state}</p>}
        </div>
      )}

      <p className="manibus-camera-disclosure">
        Translations can send up to three camera snapshots and a neutral
        reference photo to the AI service for emotion detection.
      </p>
    </div>
  );
}
