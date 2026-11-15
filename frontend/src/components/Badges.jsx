const SOURCES = {
  "phrase-bank": { label: "Checked by a fluent signer", cls: "ok" },
  model: { label: "AI translation", cls: "" },
  fallback: { label: "Word-by-word (AI offline)", cls: "warn" },
};

// Where a translation came from, and whether Manibus is unsure of it.
export function SourceBadge({ source, unsure }) {
  const s = SOURCES[source] || { label: source, cls: "" };
  return (
    <>
      <span className={`badge ${s.cls}`}>{s.label}</span>
      {unsure && source !== "fallback" && <span className="badge warn" title="Check the meaning below">Not sure about this one</span>}
    </>
  );
}
