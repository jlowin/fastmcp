# Docs Rewrite Map (v3)

This map pairs the lifecycle IA with concrete page-level changes. It is a blueprint for restructuring and rewriting, not the final content.

## Intent Legend
- Concept: explain the idea and mental model.
- How-to: show the shortest path to accomplish a task.
- Reference: exhaustive parameters, schemas, and API surface.
- Decision: compare options and help users choose.
- Tutorial: end-to-end walkthrough with context (use sparingly).
- Troubleshooting: common failures and fixes.

## New Shared Pages (Proposed)
- Component metadata and tags (server and client usage).
- Component notifications (list_changed and runtime signals).
- Component registration rules (duplicate handling and conflicts).
- Component visibility (already exists; move all component-level repeats here).
- Component versioning (already exists; move component-level repeats here).
- OAuth routing and well-known checklist (move from deployment/http and auth guides).
- OpenAPI mapping and customization (advanced mapping from OpenAPI and FastAPI guides).

## Get Started
- Keep `docs/getting-started/*` (not reviewed in detail), but align tone with new style guide and keep these pages short.

## Build

### Core Server
- `docs/servers/server.mdx`
  - Action: split and redistribute.
  - New pages:
    - Build: Server Overview (Concept + minimal How-to).
    - Operate: Server Configuration (Reference + quick config snippet).
    - Run: Running a Server (How-to) merged with `docs/deployment/running-server.mdx`.
  - Notes: remove v2 tag filtering; link to Visibility and Versioning.

### Components
- `docs/servers/tools.mdx`
  - Action: split into Tools Overview, Tool Inputs, Tool Outputs, Tool Runtime.
  - Move shared sections (visibility, notifications, duplicates, versioning) to shared pages.
  - Move context usage to Run > Context Overview.

- `docs/servers/resources.mdx`
  - Action: split into Resources Overview, Resource Templates, Resource Results, Resource Classes.
  - Move shared sections to shared pages (visibility, notifications, duplicates, versioning).

- `docs/servers/prompts.mdx`
  - Action: split into Prompts Overview, Prompt Arguments, Prompt Results.
  - Move shared sections to shared pages.

### Providers
- `docs/servers/providers/overview.mdx`
  - Keep, add a "Provider selection" decision table and tighter call to action.

- `docs/servers/providers/local.mdx`
  - Keep, trim duplicate handling and visibility; link to shared pages.

- `docs/servers/providers/filesystem.mdx`
  - Keep, maintain tradeoff tone and guidance.

- `docs/servers/providers/mounting.mdx`
  - Action: split into Mounting Basics, Mounting External Servers, Operational Considerations.
  - Move tag filtering and visibility to shared pages.

- `docs/servers/providers/proxy.mdx`
  - Action: split into Proxy Quickstart, Session Behavior, Advanced Proxy Management.

- `docs/servers/providers/custom.mdx`
  - Keep, add a minimal example before the long API-backed example.

- `docs/servers/providers/transforms.mdx`
  - Action: reorganize into Transforms Overview, Namespacing, VersionFilter, TagFilter.

### Component Design
- `docs/servers/visibility.mdx`
  - Keep, but remove long examples that duplicate component docs.

- `docs/servers/versioning.mdx`
  - Keep, but move client-facing "how to request versions" to Connect section.

- `docs/servers/icons.mdx`
  - Keep as-is; add a short "when to use" intro.

## Run

### Context and Lifecycle
- `docs/servers/context.mdx`
  - Action: split into Context Overview, Session State, Dependencies, HTTP Request Data, Context Capabilities.

- `docs/servers/lifespan.mdx`
  - Keep; this is a model for concise how-to docs.

### Runtime Features
- `docs/servers/middleware.mdx`
  - Action: split into Middleware Overview, Hooks Reference, Built-in Middleware Catalog, Custom Middleware Patterns.

- `docs/servers/tasks.mdx`
  - Action: split into Background Tasks Overview, Task Configuration, Task Backends.
  - Move Docket deep dive to an advanced page.

- `docs/servers/progress.mdx`
  - Action: shorten; keep one example + a patterns table.

- `docs/servers/logging.mdx`
  - Action: shorten; keep one example + one structured log example; move method-by-method detail to reference.

- `docs/servers/sampling.mdx`
  - Action: split into Sampling Basics, Structured Output, Tool Use, Advanced Control.
  - Move handler fallback and provider-specific details to a separate page.

- `docs/servers/elicitation.mdx`
  - Action: split into Elicitation Basics and Elicitation Schema Limits.
  - Move multi-turn recipes to a short appendix.

## Connect

### Client Overview and Transports
- `docs/clients/client.mdx`
  - Keep as the client overview; add a short "Choosing transports" guide.

- `docs/clients/transports.mdx`
  - Keep; shorten; align with server transport language.

### Core Operations
- `docs/clients/tools.mdx`, `docs/clients/resources.mdx`, `docs/clients/prompts.mdx`
  - Action: trim repetitive metadata/tag filtering; point to a shared "Client metadata" page.
  - Keep operations focused on listing and invoking.

### Runtime Features
- `docs/clients/sampling.mdx`, `docs/clients/elicitation.mdx`, `docs/clients/tasks.mdx`
  - Action: tighten intros and add "handler template" blocks.

- `docs/clients/logging.mdx`, `docs/clients/progress.mdx`, `docs/clients/roots.mdx`
  - Keep and align style with new templates.

- `docs/clients/messages.mdx`
  - Action: keep only notification handling and list_changed guidance; link out to handler pages.

## Secure

### Authorization
- `docs/servers/authorization.mdx`
  - Keep; add a short "patterns" section and reduce reference detail.

### Authentication
- `docs/servers/auth/authentication.mdx`
  - Action: replace with an Auth Decision Guide (Decision).

- `docs/servers/auth/token-verification.mdx`, `docs/servers/auth/remote-oauth.mdx`, `docs/servers/auth/oauth-proxy.mdx`, `docs/servers/auth/oidc-proxy.mdx`, `docs/servers/auth/full-oauth-server.mdx`
  - Action: convert each to a short How-to plus separate Reference page.
  - Centralize OAuth routing and well-known guidance in a shared checklist page.

## Operate

### Observability
- `docs/servers/telemetry.mdx`
  - Keep; move attributes reference to a separate reference page.

### Storage and State
- `docs/servers/storage-backends.mdx`
  - Action: split into Storage Overview (Decision) and Storage Reference.
  - Move OAuth storage guidance into Secure or Operate auth pages.
  - Move cache storage details to Middleware or Operate.

### Deployment
- `docs/deployment/running-server.mdx`
  - Action: merge with server running content and shorten.

- `docs/deployment/http.mdx`
  - Action: split into HTTP Deployment, Framework Mounting, CORS, OAuth Routing (moved to Secure).

- `docs/deployment/server-configuration.mdx`
  - Action: split into fastmcp.json overview, schema reference, CLI workflows.

- `docs/deployment/fastmcp-cloud.mdx`
  - Action: shorten to a quickstart plus "how it works".

## Integrate

### FastAPI/OpenAPI
- `docs/integrations/fastapi.mdx`
  - Action: split into Decision, Generate from FastAPI, Mount into FastAPI.
  - Move large example into a short appendix.

- `docs/integrations/openapi.mdx`
  - Action: split into Quickstart and OpenAPI Mapping Reference.

### Auth Providers
- `docs/integrations/auth0.mdx`, `docs/integrations/google.mdx`, `docs/integrations/github.mdx`, and similar auth provider docs
  - Action: normalize into a shared template and shorten.
  - Template: prerequisites, provider config, minimal setup, production checklist, link to auth routing doc.

### AI Assistants and SDKs
- `docs/integrations/chatgpt.mdx`, `docs/integrations/claude-code.mdx`, `docs/integrations/claude-desktop.mdx`, `docs/integrations/cursor.mdx`, `docs/integrations/gemini-cli.mdx`, `docs/integrations/openai.mdx`, `docs/integrations/anthropic.mdx`, `docs/integrations/gemini.mdx`
  - Action: tighten to setup steps and a small troubleshooting block.

## Development
- `docs/development/contributing.mdx`, `docs/development/tests.mdx`, `docs/development/releases.mdx`, `docs/development/upgrade-guide.mdx`
  - Keep utilitarian; reduce narrative and keep task-first.

## Page Merge Candidates
- Server run details: `docs/servers/server.mdx` + `docs/deployment/running-server.mdx`.
- OAuth routing: `docs/deployment/http.mdx` + auth provider docs.
- Component metadata and tags: repeated sections across client/server component pages.
- Component notifications: repeated sections across tools/resources/prompts.

## Notes and Caveats
- Auth provider integrations appear highly similar; a template should reduce duplication.
- Some integration docs were sampled rather than exhaustively reviewed; expect similar patterns across the rest.
