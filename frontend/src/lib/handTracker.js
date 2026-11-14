// Owner: Person 1. Runs MediaPipe hand tracking on a <video> element in the browser.
import { FilesetResolver, HandLandmarker } from "@mediapipe/tasks-vision";

const WASM = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@latest/wasm";
const MODEL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task";
let landmarker;

// Calls onHands with a list of hands every frame; each hand is 21 [x, y, z] points.
// Returns a function that stops tracking.
export async function startHandTracking(video, onHands) {
  if (!landmarker) {
    const vision = await FilesetResolver.forVisionTasks(WASM);
    landmarker = await HandLandmarker.createFromOptions(vision, {
      baseOptions: { modelAssetPath: MODEL },
      runningMode: "VIDEO",
      numHands: 2,
    });
  }
  let running = true;
  const loop = () => {
    if (!running) return;
    if (video.readyState >= 2) {
      const result = landmarker.detectForVideo(video, performance.now());
      onHands(result.landmarks.map((hand) => hand.map((p) => [p.x, p.y, p.z])));
    }
    requestAnimationFrame(loop);
  };
  loop();
  return () => {
    running = false;
  };
}
