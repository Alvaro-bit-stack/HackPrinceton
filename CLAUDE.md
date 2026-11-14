# Kitchen brigade: when to delegate

The main session runs on Sonnet. Four subagents live in `.claude/agents/`:

| Agent | Model | Use for |
|---|---|---|
| prep-cook | Haiku | searches, naming, boilerplate |
| line-cook | Sonnet | features, UI, tests, refactoring |
| sous-chef | Opus | hard debugging, complex/risky changes, reviews |
| head-chef | Fable (read-only) | architecture, high-impact planning |

## Delegation rules
- **Don't delegate what you can finish in a few tool calls.** A quick read, a one-line fix or a single grep is cheaper done directly than via a subagent.
- **Pick the cheapest capable tier.** Delegate when the work is self-contained and would flood this context (wide searches, multi-file features, long debugging).
- **Escalate on struggle, one tier at a time.** If a subagent replies starting with `ESCALATE:`, or fails the same task twice, re-dispatch to the tier it names with its findings included. Subagents cannot call each other; the main session routes.
- **Go straight to head-chef** only for decisions that are expensive to reverse: architecture, data models, public APIs, large migrations. Head-chef plans; another tier executes.

## Verification
- Every code change ends with the relevant tests run and the result reported. No "done" with failing or unrun tests.
- **Important changes** (auth, payments, data migrations, shared core modules, anything >~200 lines or touching many files) get a review by **sous-chef** before they're called done.
- **High-impact or architectural changes** also get a final fit check from **head-chef**.
