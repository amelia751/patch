# ADK Google Search — 2026-08-21

Primary sources fetched this day:

- https://google.github.io/adk-docs/integrations/google-search/
- https://google.github.io/adk-docs/tools/limitations/
- https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/grounding/web-grounding-enterprise
- Installed `google-adk==2.1.0` (`google.adk.tools.google_search`, `enterprise_web_search`)

## What Google documents

1. `google_search` is a **built-in Gemini grounding tool**, not a Python function we implement.
2. It must live **alone** on the `LlmAgent` that owns it. Mixing it with `FunctionTool`s on the same agent is unsupported (Gemini 1.x hard-fails; Gemini 2+/3 still documented as "one tool per agent" for this built-in).
3. The supported workaround is the **Agent-as-Tool** pattern: a search-only child, wrapped in `AgentTool`, granted to the parent alongside our function tools. ADK 1.16+ also offers `bypass_multi_tools_limit=True`; the child pattern is what the official limitations page still shows first.
4. Do **not** put the search agent in `sub_agents` / `transfer_to_agent`. Built-in tools on transferred sub-agents are unsupported except the documented bypass. PatchAPI already forbids transfer (roadmap §9).
5. On Vertex / Gemini Enterprise, `enterprise_web_search` is the compliance-indexed sibling (`types.Tool(enterprise_web_search=...)`). Same "alone on the child" rule. Our smoke already uses Vertex + `google_search` on Gemini 3.5 Flash via `types.Tool(google_search=GoogleSearch())`, which ADK emits for every Gemini 2+ model id.
6. Grounding responses may include Search suggestion HTML (`renderedContent`). Production UIs that show those suggestions must render that HTML per Google's grounding policy. Our agents consume snippets as untrusted text and do not surface suggestion chips.

## What this means for PatchAPI

- Policy and PR are Python stages, not `LlmAgent`s. They cannot hold search.
- The four reasoning agents (Change Intelligence, Impact, Patch, Verification) each get the **same** search-only `AgentTool` child. Hits stay untrusted. They never replace the pinned feed, the scan, the skill, or sandbox evidence.
- Change Intelligence: search corroborates the deterministic parse. A live-page disagreement is recorded in the rationale; it does not veto the parse. `HUMAN_REQUIRED` only when the notice and the adapter disagree, or the adapter refuses.
- Impact / Patch / Verification: search confirms a public fact already in scope. It cannot invent a file, an API, or a PASS.
