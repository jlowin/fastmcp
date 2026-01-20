# Docs Style Guide (v3 Draft)

This guide defines a consistent voice and structure for FastMCP v3 docs. It is intended for doc authors and reviewers to align output across the entire documentation set.

## Goals
- Maximize discoverability and confidence.
- Reduce cognitive load and time-to-first-success.
- Separate concept, action, and reference so users can find what they need quickly.

## Voice and Tone
- Direct, confident, and practical.
- Prefer short sentences and active voice.
- Lead with mental models, then details.
- Avoid essay-style intros; lead with "what you can do" and "when to use it".
- Avoid defensive writing and "not just" constructions.
- Write like a colleague: expert reader, no hype, no sales language.

## Page Types and Templates

### Concept Pages
- Purpose: explain the mental model and why it exists.
- Structure:
  - 2–3 sentence intro: what it is + when to use it.
  - 1–2 diagrams or concise examples.
  - Links to the relevant how-to and reference pages.

### How-to Pages
- Purpose: get a task done quickly.
- Structure:
  - 1–2 sentence outcome.
  - Prerequisites (only if required).
  - Minimal runnable example.
  - Short checklist of common pitfalls.
  - Links to reference.

### Reference Pages
- Purpose: exhaustive details of parameters, options, and behavior.
- Structure:
  - One-line scope statement.
  - Tables or cards only; minimal narrative.
  - No long examples (link to how-to instead).

### Decision Guides
- Purpose: choose among multiple approaches (auth, deployment, providers).
- Structure:
  - Decision table or flow.
  - Short “If you are X, do Y.”
  - Link to the detailed how-tos.

### Tutorials (Use Sparingly)
- Purpose: end-to-end onboarding or demos.
- Structure:
  - Use a single cohesive scenario.
  - Limit to 1-2 pages.
  - Prefer linking to how-tos, not replacing them.

## Page Structure Conventions
- Start with a "Use this when" line for all non-reference pages.
- Keep introductions under 120 words.
- Headers should be short (2-3 words) and scannable, no colons.
- Use H2 for sections; avoid deep nesting.
- Keep one main goal per page.

## Code Examples
- Code blocks illustrate concepts already explained in prose.
- Avoid the "one sentence then code" pattern; explain before showing syntax.
- Every code block must be runnable.
- Include imports in each block.
- Use minimal code and avoid full sample apps in guides.
- Large examples belong in appendices or external repos.

## “Pitfalls” and “Gotchas”
- Keep to 1–3 items.
- Place immediately after the main example.
- Each item should describe the symptom and fix.

## Cross-Linking
- Link from guides to reference, not the other way around.
- Use consistent link names (e.g., “Reference: OAuth Proxy”).

## Avoid
- Parameter catalogs inside how-to pages.
- Long narratives before showing an example.
- Repeating the same guidance across Tools/Resources/Prompts.
- Redundant definitions (move them to shared pages).
- Mechanical enumerations of features or file-by-file summaries.
- Ending with generic "Best Practices" or "Next Steps" sections.

## Shared Content Targets
- Component metadata and tags.
- Component notifications.
- Component registration rules.
- Visibility and versioning.
- OAuth routing and .well-known rules.

## Quality Checks
- Does the page declare its intent in the first 2–3 lines?
- Are mental models explained before syntax?
- Is the example minimal and runnable?
- Are parameter details deferred to reference pages?
- Does the page avoid overlapping with another page’s responsibility?
- Does the document read coherently end-to-end?
