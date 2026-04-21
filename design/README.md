# Design notes

Per-feature design notes for the congress-trades pipeline. One Markdown file per non-trivial feature — `design/{feature-name}.md` — capturing the scope, the decisions already made, and the test fixtures needed, so a fresh session can pick up mid-feature from the note plus the last commit without re-litigating choices.

## When to write one

Any backlog item that is more than a one-file surgical edit. The design note usually lands as its own commit *before* the implementation commits, so the plan is reviewable in isolation and the `[ ] → [~]` flip on the ROADMAP item is tied to a concrete artifact.

Triggers:

- Multi-file change.
- New module or subsystem.
- Non-obvious design choice with live options to rule out.
- Anything that reshapes the extracted schema, the scoring weights, the site render, or the GitHub Actions workflows.

## What to include

- **Scope** — what's in, what's explicitly out, and (if bundled) how the pieces relate.
- **Locked decisions** — numbered list of choices already made, each with a one-line rationale so the next agent knows why not to revisit them.
- **Sketches** — CSS/HTML/Python/JSON stubs if the note is pre-implementation; these set the shape without committing to line-exact code.
- **Test plan** — which test files and new cases the change will add or extend. Target test count after the change if the suite is non-trivial.
- **Non-goals** — what tempting extensions are deliberately out of scope, so future reviewers don't ask "why didn't you add X".
- **Responsibility table** — a `| Concern | Owner | Notes |` table at the bottom mapping each moving part to the file/function that owns it (and to "None / ephemeral" for things explicitly not persisted). This enforces the standing order that deterministic work lives in Python.
- **Commit plan** — the sequence of commits the feature will produce, and at which step the ROADMAP flip to `[~]` happens.

## Existing notes

- `soft-delete-convention.md` — standing convention for discarding files on this FUSE mount (reference, not a feature).
