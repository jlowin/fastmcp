# Critical Instruction
- Provide redirects for every existing doc to its new destination.
- Include all v2 docs under a dedicated "V2" dropdown, preserving the current v2 hierarchy.

# Get Started
- Welcome
- Installation
- Quickstart
- Updates

# Servers
- Overview
- Components
  - Tools
  - Resources
  - Prompts
- Composition
  - Providers Overview
  - Local
  - FileSystem
  - Proxying
  - Mounting
  - Custom
  - Transforms
- Runtime
  - Context
  - Lifespan
  - Middleware
  - Tasks
  - Progress
  - Sampling
  - Elicitation
- Auth & Authorization
  - Auth Decision Guide
  - Server Auth
    - Quickstart
    - Routing & Well-Known
    - Reference
  - Authorization
- Design & Metadata
  - Visibility
  - Versioning
  - Metadata & Tags
  - Notifications
  - Registration Rules
  - Icons
- Observability & State
  - Logging
  - Telemetry
  - Storage Backends

# Clients
- Overview
- Transports
- Operations
  - Tools
  - Resources
  - Prompts
  - Messages
- Runtime Features
  - Sampling
  - Elicitation
  - Tasks
  - Progress
  - Logging
  - Roots
- Auth
  - OAuth
  - Bearer

# Integrations
- FastAPI
- OpenAPI
- OpenAPI Mapping
- Auth Providers
  - Auth0
  - AuthKit
  - AWS Cognito
  - Azure
  - Descope
  - Discord
  - GitHub
  - Google
  - OCI
  - Scalekit
  - Supabase
  - WorkOS
- Authorization
  - Eunomia Authorization
  - Permit
- AI Assistants
  - ChatGPT
  - Claude Code
  - Claude Desktop
  - Cursor
  - Gemini CLI
  - MCP JSON Configuration
- AI SDKs
  - Anthropic
  - Gemini
  - OpenAI

# Deployment
- Running Server
- HTTP Deployment
- Framework Mounting
- CORS
- Server Configuration
  - Overview
  - Reference
- CLI Usage
- FastMCP Cloud

# Development
- Contributing
- Tests
- Releases
- Upgrade Guide
- Changelog

# V2
- Preserve existing v2 sections and pages under this dropdown.

# Research Notes

## Scope
- Reviewed core server docs: `docs/servers/server.mdx`, `docs/servers/tools.mdx`, `docs/servers/resources.mdx`, `docs/servers/prompts.mdx`, `docs/servers/context.mdx`, `docs/servers/middleware.mdx`, `docs/servers/visibility.mdx`, `docs/servers/versioning.mdx`
- Reviewed auth stack: `docs/servers/auth/authentication.mdx`, `docs/servers/auth/token-verification.mdx`, `docs/servers/auth/remote-oauth.mdx`, `docs/servers/auth/oauth-proxy.mdx`, `docs/servers/auth/oidc-proxy.mdx`
- Reviewed deployment and integrations: `docs/deployment/http.mdx`, `docs/integrations/fastapi.mdx`, `docs/integrations/openapi.mdx`
- Reviewed provider framing: `docs/servers/providers/overview.mdx`, `docs/servers/providers/transforms.mdx`, `docs/servers/providers/filesystem.mdx`
- Reviewed client basics: `docs/clients/client.mdx`, `docs/clients/transports.mdx`, `docs/clients/tools.mdx`

## Cross-Cutting Issues
- Mixed intent: many pages blend concept, tutorial, and reference in one scroll, so the user has to read too much to find the exact step.
- Monoliths: several core pages exceed 400-1000 lines, which hides key actions and makes navigation feel heavy.
- Repetition: visibility, notifications, duplicate-handling, and context snippets repeat across tools/resources/prompts, which makes maintenance harder and adds noise.
- v2 legacy and v3 guidance are interleaved; deprecations are buried inside parameter cards instead of being surfaced as a clear migration path.
- Over-indexed on internal API detail inside guides (long ParamField cards) rather than short guides plus separate reference pages.

## Style Critique
- Long narrative intros delay first action. The pages often explain the protocol, then finally show how to do the thing.
- Explanations are often written as essays instead of task-focused steps, especially in auth and deployment docs.
- Param tables embedded mid-guide disrupt flow; users are forced into reference mode when they are still trying to finish a task.
- Large examples (FastAPI/OpenAPI) read like tutorials and dominate the page; they are hard to skim and reuse.
- Many subsections repeat the same phrasing patterns across pages, which creates a sense of copy/paste rather than a coherent narrative.

## Monoliths and Proposed Splits

### `docs/servers/server.mdx` (396 lines)
- Current content mixes: constructor reference, components overview, tag filtering (deprecated), running server, custom routes, mounting, proxying, OpenAPI, config.
- Proposed split:
  - Server Overview: what FastMCP is, minimal creation.
  - Server Configuration: constructor params and settings (reference).
  - Running a Server: run vs http_app, transport entry points.
  - Composition: mount/proxy/openapi moved to Providers in Build.
  - Remove v2 tag filtering content; link to Visibility and migration notes.

### `docs/servers/tools.mdx` (1077 lines)
- Overloaded with core definition, arguments, output schemas, errors, timeouts, visibility, notifications, context, duplicate behavior, versioning.
- Proposed split:
  - Tools Overview: purpose, minimal examples, naming.
  - Tool Inputs: validation, typing, Annotated/Field.
  - Tool Outputs: ToolResult, structured outputs, schemas.
  - Tool Runtime: timeouts, errors, context access.
  - Shared sections (visibility, notifications, duplicates, versioning) move to shared component docs.

### `docs/servers/resources.mdx` (745 lines)
- Mixes resource basics, templates, RFC 6570 details, return types, resource classes, notifications, duplication, versioning.
- Proposed split:
  - Resources Overview: what and when, simple static vs dynamic.
  - Resource Templates: URI template syntax and examples.
  - Resource Results: ResourceResult + content types.
  - Resource Classes: File/Directory/Http resources as a reference page.

### `docs/servers/prompts.mdx` (460 lines)
- Mixes prompt basics, argument typing, result types, visibility, notifications, duplicates, versioning.
- Proposed split:
  - Prompts Overview: what they are, string vs Message.
  - Prompt Arguments: typed strings, constraints, guidance.
  - Prompt Results: Message and PromptResult reference.

### `docs/servers/context.mdx` (653 lines)
- One page covers context basics, state, prompts/resources access, notifications, HTTP deps, auth token access, dependency injection, request metadata.
- Proposed split:
  - Context Overview: how to get context, request-scoped usage.
  - Session State: persistence, storage backends, TTL.
  - Context Capabilities: logging/progress/sampling/elicitation (short). 
  - HTTP Request Data: headers, request access, transport details.
  - Dependencies: Depends, custom dependencies, advanced patterns.

### `docs/servers/middleware.mdx` (847 lines)
- Mixes conceptual explanation, hook reference, component access patterns, and built-in middleware tutorials.
- Proposed split:
  - Middleware Overview: mental model, hook categories.
  - Middleware Hooks Reference: signature and semantics (reference).
  - Built-in Middleware Catalog: logging, timing, caching, rate limiting, ping.
  - Custom Middleware Patterns: examples and best practices.

### `docs/deployment/http.mdx` (737 lines)
- Combines deployment, auth, CORS, SSE polling, framework mounting, scaling, environment variables, OAuth token security, and well-known routes.
- Proposed split:
  - HTTP Deployment: run vs ASGI, URL paths, base deployment.
  - Mounting in Web Frameworks: Starlette/FastAPI (short guide).
  - Scaling and Stateless Mode: sessions and load balancers.
  - OAuth Routing and Well-Known: move to Secure/Operate as dedicated how-to.
  - CORS: separate how-to with minimal config and pitfalls.

## Auth Docs Issues and Reframe
- `docs/servers/auth/authentication.mdx` is concept-heavy and repeats the same problem framing as remote/proxy docs.
- `docs/servers/auth/oauth-proxy.mdx` is 500+ lines and buries the most actionable routing guidance inside parameter cards and deep sections.
- Actionable mounting guidance currently lives in `docs/deployment/http.mdx#mounting-authenticated-servers`, far from auth docs.
- Proposed structure:
  - Auth Decision Guide: pick Token Verification vs Remote OAuth vs OAuth Proxy vs Full OAuth.
  - Auth Implementation Quickstart: minimal steps per model.
  - Auth Routing and Well-Known: clear checklist for mount prefixes, issuer_url, base_url, and .well-known.
  - Auth Reference: parameter catalog per provider class.

## Integrations Style Issues
- `docs/integrations/fastapi.mdx` and `docs/integrations/openapi.mdx` read like tutorials with long sample apps.
- The same large example is repeated across sections, and context for when to use each option is buried.
- Proposed restructure:
  - Short intro + decision table (generate vs mount).
  - Minimal quickstart snippets.
  - Dedicated page for OpenAPI mapping and customization.
  - Move large sample app to an appendix or examples repo link.

## Tone and Structure Guidelines
- Lead with intent: a short "Use this when" and "Outcome" sentence at the top of each page.
- Separate concept vs task vs reference; each page should declare its type and stick to it.
- Keep guides short, then link to reference pages for parameter tables.
- Prefer checklists and "gotchas" sections for operational docs (auth, deployment, scaling).
- Use smaller, targeted code blocks; keep full examples in dedicated example sections or appendices.

## Duplicate Sections to Consolidate
- Visibility control: currently repeated in tools/resources/prompts; move to `docs/servers/visibility.mdx` and link out.
- Notifications: similar repeated sections across components; move to a single "Component Notifications" page.
- Duplicate handling (on_duplicate_*): move to a "Component Registration Rules" page.
- Context usage snippets: move to Context Overview and keep other pages linking out.

## Notes on What Works
- Provider overview is short, concept-first, and points to next actions; this is a good template for new pages. `docs/servers/providers/overview.mdx`
- Filesystem provider balances "why" with "how" and includes tradeoffs; use that tone across Build docs. `docs/servers/providers/filesystem.mdx`
- Authorization page is more focused than auth stack docs; good baseline for Secure section. `docs/servers/authorization.mdx`

## Additional Review: Run + Operate

### `docs/servers/logging.mdx`
- Good use of basic example, but the page leans heavily into method-by-method reference and repeated examples.
- Suggest a concise "When to log to client vs server" section and move the method card to a reference page.
- Reduce example count; keep one "happy path" and one structured logging example.

### `docs/servers/progress.mdx`
- Solid structure and examples, but text is repetitive and could be shorter.
- "Why use" and "progress patterns" sections overlap with short repeated prose.
- Suggest a compact guidance section + minimal patterns table, then example links.

### `docs/servers/elicitation.mdx`
- Great coverage but long; reads as a mini reference and tutorial in one.
- The "response types" section is dense; propose a separate "schema limits" reference and a shorter guide page.
- Multi-turn examples are helpful; keep one, move the rest to a "recipes" appendix.

### `docs/servers/sampling.mdx`
- Overlong and heavy on reference cards; multiple advanced flows in one doc.
- Consider split into: Sampling basics, Structured output, Tool use, Advanced control (sample_step) + handler fallback.
- The flow would improve by moving handler fallback and OpenAI/Anthropic details to a distinct section or page.

### `docs/servers/tasks.mdx`
- Clear narrative but still long; blends protocol explanation, config, backends, and Docket deep dive.
- Suggest: overview + quickstart + "choose your backend" card, then a separate "Docket advanced" page.

### `docs/servers/telemetry.mdx`
- Strong, concise, and operational. This is close to target style.
- Potential trim: long attributes reference could move to a separate "Telemetry reference" page.

### `docs/servers/lifespan.mdx`
- Very strong structure; short, practical, clear. Use as a style model for other Run pages.

### `docs/servers/storage-backends.mdx`
- Good decision guidance but long and highly procedural.
- Suggest moving long OAuth storage guidance to Secure/Operate auth docs.
- Move cache storage details to Middleware or Operate, and keep a short "backend chooser" here.

### `docs/servers/icons.mdx`
- Short and focused, good fit. Consider adding a tiny "when to use" line and leaving the rest as-is.

## Providers + Composition

### `docs/servers/providers/local.mdx`
- Clear and compact. Repeats duplicate handling and visibility; those should centralize in shared docs.

### `docs/servers/providers/mounting.mdx`
- Useful but long; mixes composition, proxy mounting, namespacing, conflict resolution, and performance.
- Suggest split into "Mounting basics" + "Mounting external servers" + "Operational considerations".
- Tag filtering and visibility should live with Visibility/Authorization, not Mounting.

### `docs/servers/providers/proxy.mdx`
- Good rationale, but includes a lot of advanced use in one page.
- Split into "Proxy quickstart" + "Proxy session behavior" + "Advanced proxy management".

### `docs/servers/providers/custom.mdx`
- Strong narrative. Could use a smaller, faster "minimal provider" example up top.
- The long API-backed provider example is good but should be optional or placed after a summary.

## Deployment + Configuration

### `docs/deployment/running-server.mdx`
- Monolithic: transport explainer + CLI + reload + async + custom routes.
- Suggest split into "Run locally" (stdio/http), "CLI usage", and "HTTP deployment" links.
- The transport explanations are long; can become a short comparison table and a single recommended choice per use case.

### `docs/deployment/http.mdx`
- Already called out in earlier notes as too dense and mixing auth, CORS, and routing.
- Should be reduced to core deployment patterns, with auth routing moved into Secure.

### `docs/deployment/server-configuration.mdx` (fastmcp.json)
- Very long and reads like schema documentation embedded inside a guide.
- Suggest split into:
  - Conceptual overview: what fastmcp.json is and when to use it.
  - Reference: schema fields and examples.
  - CLI integration: override rules and workflows.

### `docs/deployment/fastmcp-cloud.mdx`
- Marketing tone and screenshots are fine, but it reads like a product landing page.
- Consider a shorter "Quickstart" with minimal steps and a smaller "How it works" section.

## Client Docs

### `docs/clients/resources.mdx`, `docs/clients/prompts.mdx`, `docs/clients/tools.mdx`
- Clear but repetitive and reference-heavy.
- Suggest a shared "Client operations" overview, then smaller, focused pages for each component type.
- Metadata/tag filtering sections are repeated; consolidate into a "Client metadata and tags" page.

### `docs/clients/sampling.mdx`, `docs/clients/elicitation.mdx`, `docs/clients/tasks.mdx`
- More concise than server counterparts, but still heavy on reference cards.
- Tighten intros and add a quick "handler template" for fast setup.

### `docs/clients/messages.mdx`
- Good structure; however, it overlaps with dedicated handler docs (logging/progress/sampling).
- Suggest keeping only notifications + list_changed guidance, and link to specific handlers.

### `docs/clients/logging.mdx`, `docs/clients/progress.mdx`, `docs/clients/roots.mdx`
- These are concise and serve as good model pages (especially progress, roots).

## Integrations
- Auth provider integrations (Auth0/Google/GitHub and likely others) read like full tutorials with many steps and repeated copy. They are useful but too long and similar to each other.
- Suggest a shared template: prerequisites, provider-specific config, minimal example, production checklist, then link to a shared "OAuth routing and well-known" page.
- Integration docs should clearly state intent: "Use this when you need X" and refer back to the Secure docs for general OAuth concepts.
- FastAPI/OpenAPI guides are too long and should be split into decision + minimal quickstart + optional advanced mapping.

## Development Docs
- Not a primary focus for the IA, but style is inconsistent with core docs.
- Suggest keeping these utilitarian: short, task-based, less narrative; avoid long prose.

## Holistic Recommendations (Style, Tone, Structure)
- **Declare page intent upfront**: Concept vs How-to vs Reference. The reader should know within 2-3 lines.
- **Single responsibility per page**: Avoid mixing schema reference, rationale, and tutorial in one scroll.
- **Short, high-signal intros**: State what the reader will achieve and when to use it.
- **Decision-first structure**: For complex domains (auth, deployment), start with a decision guide, then deep dives.
- **Move long parameter tables to reference pages**: Keep guides action-driven.
- **Reduce duplicated guidance**: Centralize visibility, duplicates, metadata, and notifications in shared docs.
- **Prefer minimal runnable examples**: Keep examples tight; move big sample apps to an appendix or repository.
- **Consistent voice**: Direct, confident, and practical; avoid long philosophical framing in technical how-tos.
- **Operational docs should read like checklists**: Especially for OAuth routing, deployment, and security.
- **Use brief "pitfalls" callouts**: Highlight the 1-2 most common mistakes rather than long narrative warnings.
