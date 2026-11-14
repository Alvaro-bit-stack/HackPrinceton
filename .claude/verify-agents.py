#!/usr/bin/env python3
"""Check the kitchen-brigade subagent setup. Run from the project root: python3 .claude/verify-agents.py"""
import json, pathlib, sys

EXPECTED = {"prep-cook": "haiku", "line-cook": "sonnet", "sous-chef": "opus", "head-chef": "fable"}
WRITE_TOOLS = {"Edit", "Write", "Bash", "NotebookEdit"}
root = pathlib.Path(__file__).resolve().parent
errors = []

for name, model in EXPECTED.items():
    path = root / "agents" / f"{name}.md"
    if not path.exists():
        errors.append(f"missing {path}"); continue
    text = path.read_text()
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        errors.append(f"{name}: bad frontmatter"); continue
    # ponytail: flat key: value parser; switch to PyYAML if frontmatter grows nested fields
    meta = dict(l.split(":", 1) for l in text[4:].split("\n---\n")[0].splitlines() if ":" in l)
    meta = {k.strip(): v.strip() for k, v in meta.items()}
    tools = {t.strip() for t in meta.get("tools", "").split(",") if t.strip()}
    if meta.get("name") != name: errors.append(f"{name}: name is {meta.get('name')!r}")
    if meta.get("model") != model: errors.append(f"{name}: model is {meta.get('model')!r}, want {model!r}")
    if len(meta.get("description", "")) < 40: errors.append(f"{name}: description too short for auto-delegation")
    if name == "head-chef" and (not tools or tools & WRITE_TOOLS):
        errors.append(f"head-chef must be read-only, has tools: {sorted(tools) or 'ALL (inherited)'}")
    print(f"{'ok ' if not [e for e in errors if e.startswith(name)] else 'ERR'} {name:10} model={meta.get('model'):7} tools={','.join(sorted(tools)) or 'all'}")

settings = json.loads((root / "settings.json").read_text())
if settings.get("model") != "sonnet": errors.append(f"settings.json model is {settings.get('model')!r}, want 'sonnet'")
else: print("ok  main session model=sonnet")

print("\n" + ("\n".join("ERROR: " + e for e in errors) if errors else "All checks passed."))
sys.exit(1 if errors else 0)
