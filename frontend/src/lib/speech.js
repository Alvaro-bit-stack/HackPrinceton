// Owner: Person 3. Speech-to-text and text-to-speech using the browser's built-in APIs.

// Listens for one spoken sentence and calls onText with it. Works in Chrome and Edge.
export function listen(onText, onError) {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
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

export function speak(text) {
  window.speechSynthesis.speak(new SpeechSynthesisUtterance(text));
}
