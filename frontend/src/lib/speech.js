// Owner: Person 3. Speech-to-text and text-to-speech using the browser's built-in APIs.

const SR = typeof window !== "undefined" && (window.SpeechRecognition || window.webkitSpeechRecognition);
export const canListen = Boolean(SR);

// Listens for one spoken sentence and calls onText with it. Works in Chrome and Edge.
export function listen(onText, onError) {
  if (!SR) {
    onError?.("This browser can't listen. Use Chrome, or type instead.");
    return null;
  }
  const rec = new SR();
  rec.lang = "en-US";
  rec.onresult = (e) => onText(e.results[0][0].transcript);
  rec.onerror = (e) => onError?.(`Couldn't hear that (${e.error}). Try again or type instead.`);
  rec.start();
  return rec;
}

// Keeps listening until stop() is called, showing words as they are heard.
// onInterim(text) fires while talking; onEnd(finalText) fires once when listening stops.
export function startListening({ onInterim, onEnd, onError }) {
  if (!SR) {
    onError?.("This browser can't listen. Use Chrome or Edge, or type instead.");
    return null;
  }
  const rec = new SR();
  rec.lang = "en-US";
  rec.interimResults = true;
  rec.continuous = true;
  let finalText = "";
  rec.onresult = (e) => {
    let interim = "";
    for (let i = e.resultIndex; i < e.results.length; i++) {
      if (e.results[i].isFinal) finalText += e.results[i][0].transcript;
      else interim += e.results[i][0].transcript;
    }
    onInterim?.((finalText + interim).trim());
  };
  rec.onerror = (e) => {
    if (e.error === "no-speech" || e.error === "aborted") return;
    const why = e.error === "not-allowed" ? "the microphone is blocked; allow it in the browser" : e.error;
    onError?.(`Couldn't hear that (${why}). Try again or type instead.`);
  };
  rec.onend = () => onEnd?.(finalText.trim());
  rec.start();
  return { stop: () => rec.stop() };
}

export function speak(text) {
  window.speechSynthesis.speak(new SpeechSynthesisUtterance(text));
}
