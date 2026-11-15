
function ArrowIcon() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M5 12h14" />
      <path d="m13 6 6 6-6 6" />
    </svg>
  );
}

export default function Home({ go }) {
  return (
    <section className="manibus-landing">
      <div className="manibus-landing-inner">

        <p className="manibus-landing-eyebrow">
          INTRODUCING MANIBUS
        </p>

        <div className="manibus-landing-logo">
          <img
            src="/manibus-logo.png"
            alt="Manibus"
          />
        </div>

        <h1 className="manibus-landing-headline">
          Learning independently.
          <br />
          <span>Signing confidently.</span>
        </h1>

        <p className="manibus-landing-tagline">
          An AI tool enabling{" "}
          <strong>self-driven learning</strong> and{" "}
          <strong>critical sign language exposure</strong>
          <br className="desktop-break" />
          for deaf students.
        </p>

        <div className="manibus-landing-actions">
          <button
            type="button"
            className="manibus-landing-primary"
            onClick={() => go("Speak")}
          >
            Start translating
            <ArrowIcon />
          </button>
        </div>

        <blockquote className="manibus-landing-quote">
          <p>
            “Education is the kindling of a flame,
            not the filling of a vessel.”
          </p>
          <cite>— Socrates</cite>
        </blockquote>

      </div>
    </section>
  );
}
