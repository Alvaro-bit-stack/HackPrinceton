// Play/pause, replay, previous/next and a speed slider, shared by the Speak and Reader pages.
export default function PlayerControls({ playing, onPlay, onPause, onReplay, onPrev, onNext, canPrev, canNext, speed, onSpeed }) {
  return (
    <div className="controls" role="group" aria-label="Signing controls">
      {onPrev && <button type="button" onClick={onPrev} disabled={!canPrev} aria-label="Previous sentence" title="Previous sentence">⏮</button>}
      <button type="button" onClick={onReplay} aria-label="Replay" title="Replay">↺</button>
      {playing ? (
        <button type="button" className="primary big" onClick={onPause} aria-label="Pause" title="Pause (space)">⏸</button>
      ) : (
        <button type="button" className="primary big" onClick={onPlay} aria-label="Play" title="Play (space)">▶</button>
      )}
      {onNext && <button type="button" onClick={onNext} disabled={!canNext} aria-label="Next sentence" title="Next sentence">⏭</button>}
      <label className="speed">
        <span>Speed</span>
        <input type="range" min="0.5" max="1.5" step="0.25" value={speed} onChange={(e) => onSpeed(Number(e.target.value))} aria-valuetext={`${speed} times`} />
        <output>{speed}×</output>
      </label>
    </div>
  );
}
