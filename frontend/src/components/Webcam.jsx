import { useEffect, useRef, useState } from "react";
import { startHandTracking } from "../lib/handTracker.js";

const WINDOW = 15; // frames kept for one recognition request

// Shows the camera and calls onFrames with the last few frames of the first visible hand.
export default function Webcam({ onFrames }) {
  const videoRef = useRef(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let stop = () => {};
    let stream;
    let cancelled = false;
    const frames = [];
    (async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: true });
        if (cancelled) return stream.getTracks().forEach((t) => t.stop());
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
        stop = await startHandTracking(videoRef.current, (hands) => {
          if (!hands.length) return;
          frames.push(hands[0]);
          if (frames.length > WINDOW) frames.shift();
          onFrames([...frames]);
        });
      } catch (e) {
        setError("Camera isn't available. Allow camera access in the browser and reload.");
      }
    })();
    return () => {
      cancelled = true;
      stop();
      stream?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  return error ? <p role="alert">{error}</p> : <video ref={videoRef} className="webcam" muted playsInline />;
}
