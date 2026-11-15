// Playback controls shared by Translate and Read.
export default function PlayerControls({ playing, onPlay, onPause, onReplay, onPrev, onNext, canPrev, canNext }) {
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
    </div>
  );
}

export function AslSpeedSlider({ speed, onSpeed, id }) {
  return (
    <div className="manibus-speed-control">
      <div className="manibus-speed-heading">
        <label htmlFor={id}>ASL signing speed</label>
        <strong>{speed.toFixed(1)}×</strong>
      </div>
      <input
        id={id}
        type="range"
        min="0.5"
        max="2"
        step="0.1"
        value={speed}
        aria-valuetext={`${speed} times`}
        onChange={(event) => onSpeed(Number(event.target.value))}
      />
      <div className="manibus-speed-labels">
        <span>Slower</span>
        <span>Normal (1×)</span>
        <span>Faster</span>
      </div>
    </div>
  );
}
