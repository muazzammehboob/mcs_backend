# MCS Backend — Consolidated Specification & Decision Record

**Status:** This is the single canonical reference for the MCS backend build, superseding the need to re-share the original six source documents. It merges the product requirements, architecture decisions, and every open question resolved during planning into one file. Hand this file alone to a fresh planning conversation instead of the original document set.

**What this file is not:** This is not an implementation plan or a TaskSpec. No code structure, file layout, or step-by-step build instructions are finalized here beyond what's already locked in the build order. The implementation plan/prompt package for GLM 5.2 / Kimi 2.6 is a separate deliverable, produced after this spec is confirmed correct.

**Project nature:** A **personal, single-user, local-first, BYOK** chat assistant with a branching-conversation UI (already built, out of scope for this backend work). Not a production system — no multi-tenant concerns, no auth, no hardened security posture beyond "don't leak the API key." Built for the owner's own daily use, with an explicit design goal of being highly customizable (persona, instructions, generation parameters, effort level) rather than a fixed black box.

---

## 1. Mission & Definition of Done

Build a **Python (3.12+) FastAPI backend** for the Multidimensional Conversation System (MCS): a tree of conversation Branches forking from exact Prompt/Response Pairs, with reusable `@mention` Nodes, AI-generated Summary Nodes, disposable Temporary Branches, and a 3D Eagle View graph. The frontend/branching UI already exists (v1 prototype validated the core UX). This backend must get the **behavior** exactly right: correct lineage, correct token accounting, correct Gemini calls, correct Summary lifecycle, correct persistence across sessions/devices.

**v1 prototype status:** v1's code is not being reused or migrated — this is a fresh implementation. However, the bugs discovered in v1 (§15 of the requirements doc) are now **permanent correctness requirements** for v2, not historical trivia:
- Lineage must include both prompt and response turns, not prompt-only.
- Token Meter must accumulate full ancestor chain, not just the active branch.
- "Branch from here" / "Delete" actions belong to the completed Pair (response side), never the prompt bubble, and are unavailable while a response is pending.

---

## 2. Source Document Authority Order (for any future planning conversation)

1. **`mcs-v2-requirements.md`** — product/behavior spec. Never contradicted. Field names/types in it are illustrative only.
2. **This file** — architecture decisions, scope rulings, and resolved questions. Supersedes the original master brief.
3. **Build order / milestones** — sequencing, reorder freely.
4. **Agent handoff protocol** — how work moves between planner (Claude) → implementers (GLM 5.2 / Kimi 2.6) → QA (Antigravity 2.0).
5. **LLM orchestration research report** — reference menu for context/effort/orchestration patterns, not a mandate. Most of it (multi-agent fan-out, ReAct loops, MoA ensembles, Reflexion) is **explicitly not being built** — see §14 below.
6. **Cognitive Memory Middleware doc** — idea-bank only. Solves a different problem (implicit/semantic retrieval memory) than MCS has (explicit, deterministic `@mention` + lineage walk). Its vector DB / knowledge graph / forgetting-curve/SHY-decay machinery is **rejected outright** for this build, permanently, not just for v2.

---

## 3. Scope Ruling — Provider & Deployment

- **Exactly one live LLM provider for now: Gemini**, via the user's Google AI Studio Pro account and API key.
- The abstract `LLMProvider` interface stays provider-agnostic (per requirements §12's long-term mandate), but **only the Gemini adapter is implemented now**. OpenAI/Anthropic/OpenRouter/custom adapters are deferred to Phase 2, built only when explicitly requested.
- **Deployment target:** starts as localhost-only on the user's laptop, but BYOK must be designed to survive a near-future move to multi-device access (phone, PC, laptop, all hitting a backend over the home network or similar). This ruled out any "backend reads key from a local `.env` file" convenience shortcut — see §5.
- Not production-grade. No auth, no multi-tenant isolation, no hardened threat model. The one non-negotiable security rule that survives regardless: **the API key is never written to a log file, at any log level.**

---

## 4. Locked Technical Stack

| Concern | Choice | Notes |
|---|---|---|
| Language/runtime | Python 3.12+ | |
| API framework | FastAPI + Uvicorn | Async, typed, free OpenAPI docs |
| Domain models | Pydantic v2 | |
| Database | SQLite via SQLAlchemy 2.0 (async) + `aiosqlite` | Single local file, durable across sessions — directly satisfies "resume where I left off on this device" |
| Migrations | **Alembic — kept, not dropped** | Originally considered skippable for a "throwaway" personal project; reversed once the user confirmed they want durable project data they'll actually rely on. Blowing away the DB on every schema tweak is a real cost once real project history lives in it. |
| Token estimation | `tiktoken` as **fallback only** | Primary method is Gemini's own token accounting — see §8. |
| LLM calls | Hand-rolled `httpx` adapter, not the `google-genai` SDK | Keeps the wire contract transparent and inspectable for GLM/Kimi (consistent with the original brief's reasoning: an SDK black-box is harder for an implementing agent to reason about and harder for the user to audit/customize than a visible REST contract). |
| Vector DB / knowledge graph / decay | **None. Rejected.** | Not a memory-retrieval system; MCS's memory is explicit and deterministic (exact `@mention` + lineage walk). |
| Agent frameworks (LangGraph/DSPy/etc.) | **None.** | Not needed; MCS v2 has no autonomous loop in its chat path. |

---

## 5. BYOK & Key Handling (Final)

Requirements §13's original design is confirmed correct and **not weakened** for "personal use" — the multi-device future is the deciding factor:

- The API key lives **client-side only** (browser memory for the session; optional explicit "remember this key on this device" opt-in to localStorage, one copy per device — a phone and a laptop each store their own copy).
- The backend **never persists the key to disk, never logs it, never reads it from a server-side `.env`/config file.** A server-side stored key would only work if browser and backend are permanently the same machine — that assumption breaks the moment the user opens this from their phone against a laptop-hosted backend.
- **Wire contract:** key travels in a custom request header (not a query param, not the JSON body) on every LLM-calling endpoint. Query params leak into access logs and proxy traces by default; header form avoids that class of leak. Exact header name to be finalized at Milestone 0 TaskSpec time (e.g. `X-Gemini-Api-Key`).
- `provider`, `model`, and any non-secret settings travel in the request body as normal (per §13, these are not secrets).
- This is BYOK request plumbing — a dependency/middleware built once in Milestone 0 so it's structurally impossible to bypass later.

---

## 6. Gemini API Surface — Locked Decisions

- **Product:** Google AI Studio's Generative Language API (`generativelanguage.googleapis.com`), **not** Vertex AI (Vertex requires OAuth/service-account auth, which is the wrong shape for a BYOK raw-API-key flow).
- **Auth on the Gemini call itself:** `x-goog-api-key` header, not `?key=` query param — same leak-vector reasoning as §5.
- **API version:** `v1beta` — current Gemini feature surface (including relevant `generationConfig` options and thinking/effort controls) lives here; `v1` is the more conservative but feature-lagging surface.
- **Implementation approach:** hand-rolled REST calls (`generateContent`, `models.list`, `countTokens`) via `httpx`, not the `google-genai` SDK. This keeps the adapter's contract fully visible to GLM/Kimi and to the user, at the cost of writing slightly more adapter code ourselves. Confirmed as the right tradeoff for this project's stated "customizable, understand what's happening" goal.

---

## 7. Message-Shape Mapping (Provider Abstraction Boundary)

`LLMProvider.chat_completion()` (the abstract interface) accepts the **generic** shape:
```
chat_completion(system: str, messages: list[{role: "user"|"assistant", content: str}], **params) -> response
```

All Gemini-specific remapping happens **only inside `gemini_provider.py`**:
- `assistant` → `model` role rename.
- Flat `content: str` → `parts: [{text: ...}]` structure.
- `system` string pulled out of the message list entirely into Gemini's top-level `systemInstruction` field (Gemini's `contents` array has no system role at all).

This keeps the ABC provider-agnostic so a second provider (Phase 2) doesn't force a redesign of the interface — only a new adapter file.

---

## 8. Token Estimation Strategy (Final)

Two-part design, chosen for accuracy (single-provider system, so Gemini's own count is authoritative) while avoiding excessive network chatter:

### 8.1 Static context (the assembled lineage + system prompt + Referenced Knowledge, everything *except* the live draft)
- Treated as immutable while the user is typing — not recalculated per keystroke.
- After every successful send/receive on a branch, capture the exact count from that response's `usageMetadata.totalTokenCount` and cache it as `Branch.cached_static_token_count` (**new field**, added to requirements §3.2's Branch schema).
- This cached value is stale in exactly two situations, both rare and explicit — each triggers a one-time `countTokens` API call (not a `generateContent` call) to refresh it:
  1. **First-ever view of a branch with no sends yet** (cache is null) — e.g. a fresh fork, or Root before any Pair exists.
  2. **A Summary is applied, disconnected, or deleted** on that branch (`linked_summary_node_id` / `summary_cutoff_position` changes) — §10.2 requires the meter to visibly drop/rise the instant this happens, not on the next send.
- `tiktoken` is the fallback **only if the `countTokens` call itself errors** — not the default path, not a parallel check.

### 8.2 Live input (the current, not-yet-sent draft text + resolved `@mentions` in it)
- Pure client-side heuristic, zero backend calls: Google's stated standard of **1 token ≈ 4 characters** (English).
- Recalculated on every keystroke, cheaply, in the frontend.
- To estimate the token cost of `@mentions` currently typed in the draft (required by §5.2) without a backend round-trip per keystroke: **the frontend caches the full Node list for the current project in local state**, refetched whenever a Node is created/edited/deleted. At this project's stated scale (§18 of requirements: tens of branches, correspondingly small Node counts), this is a trivial memory footprint and lets `@mention` resolution + heuristic estimation happen entirely client-side.

### 8.3 The meter display
`Displayed total = Static Context (cached, exact) + Live Input (heuristic, live)`, prefixed with `~` per §5.3, color-banded per the existing 0–60/60–85/85–95/95%+ thresholds.

---

## 9. Persona / Instructions Customization (Final)

Two-tier system, resolving the user's "highly customizable persona/instructions/context" requirement — this is new scope beyond the original requirements doc, confirmed and locked:

- **Global tier:** a singleton `GlobalSettings` record with three free-text fields — `persona`, `instructions`, `negative_constraints`.
- **Per-Project tier:** the existing Project record (§3.1) gains the same three fields, nullable.
- **Override granularity: per-field** (explicitly chosen over whole-block override). Each of the three fields independently falls back to the global value if the project's own field is empty, and overrides it if set. This lets the user, e.g., keep a strict global negative-constraints list permanently while freely customizing persona per project.
- **System prompt assembly order:** effective persona → effective instructions → effective negative constraints → §4.6's Referenced Knowledge block (from `@mentions` and any injected Summary content).
- Editable via a Settings UI (textareas + save) — same "type it into a box, save it" interaction pattern the user described for Nodes.
- **New project seeding:** a new Project starts with all three fields blank (inheriting 100% from global by default), editable per-project afterward. Simpler default than copying global values in at creation time, and functionally identical from the user's point of view since per-field fallback already covers it.

This is a distinct subsystem from **Nodes (§9 of the requirements doc)**, which remain exactly as specified — reusable, `@mentionable`, project-scoped content blocks. Persona/Instructions is the "how the model behaves" settings layer; Nodes are the "reusable content I reference" layer.

---

## 10. Generation Parameters Per Turn (Final)

- **New field:** `PR Pair.generation_params` (JSON), added to requirements §3.3's PR Pair schema.
- Stores exactly what was used to produce that specific turn: `model`, `temperature`, `top_p`, `max_output_tokens`, `effort`/thinking-level.
- Selectable per-send in the UI (not just as a project-level default), so the user can dial these per prompt the way Claude.ai's effort selector works.
- Lets the user see/reproduce what settings actually produced a given historical response.

---

## 11. Effort / Reasoning Dial — Scope Clarification (Important, Previously Confused)

The user asked for "effort, like in Claude" and separately said "it should work as Claude do, rethink until all the pieces are there" — **these are two different mechanisms, and only the first is in scope for v2.**

- **In scope, building now:** a **single-call** parameter. Gemini natively exposes `thinking_level` / `thinking_budget` (varies by model generation) — one model call, more internal reasoning tokens spent before the answer, same request/response shape MCS already uses. This is a per-prompt-selectable parameter alongside temperature/top_p/max_output_tokens (§10 above), with levels the user can pick (e.g. low/medium/high/extra, mapped to whatever Gemini's specific model generation supports). Zero architectural impact — it's just another generation parameter.
- **Not in scope, explicitly deferred:** a multi-call self-critique/redraft loop or multi-step reasoning/tool loop (the orchestration research report's Sections 7/8 — Self-Refine, ReAct, Reflexion). This would mean multiple sequential LLM calls per user turn, a new state machine, and real cost multiplication (2–6× per turn per the research report's own estimates). The master brief already rules this out for v2's chat-serving path ("no autonomous agent loops inside the MCS chat path" — Phase 2 only, built if explicitly requested). Claude's own effort dial is in fact the single-call mechanism described above, **not** a hidden multi-pass loop — so building the effort parameter is the correct and complete interpretation of "work like Claude does" for v2. If genuine multi-pass reasoning is wanted later, it needs its own explicit request and its own cost/latency tradeoff writeup — it is not being quietly folded into Milestone 3.

---

## 12. Summarization / Compaction Strategy (Final)

- Technique: **a single, well-crafted one-shot summarization LLM call** over the branch's current effective lineage (§10.1 of requirements) — not recursive/hierarchical summarization, not structured-state-extraction (DECISIONS/FACTS/etc.), not any of the research report's Section 2 machinery. Those techniques exist for open-ended, unbounded cross-session memory — a different problem than MCS has, where a Summary Node is generated on an explicit user click over one branch's bounded lineage.
- Full lifecycle exactly as already specified in requirements §10: Generate (draft shown before applying) → Keep vs Replace → Edit → Disconnect vs Delete, with the Token Meter visibly reacting to Replace/Disconnect per §8.1 above.
- **Does not mutate ancestor branches.** A Summary is scoped to the one branch it was generated from; ancestors' own data and lineage are untouched — this was already a hard requirement in §4.3/§10 and needed no new design.

---

## 13. Multimodal / File Attachments (New Scope — Final Decisions)

Not present anywhere in the original requirements doc — a genuine addition, now fully specified:

- **Data model:** a new `Attachment` table — `id, pair_id, file_path, mime_type, original_filename, size_bytes, created_at`. Not a field on PR Pair directly, since one Pair may carry multiple files.
- **Storage:** files land on local disk under a project-scoped data directory.
- **Upload flow:** a **separate upload endpoint** (`POST /attachments` → returns an `attachment_id`) happens before the send-message request, which then references already-uploaded attachment ids. This (not one bundled multipart request) is what makes "retry with the same attached files after a failed send" trivial — the files are already durably uploaded before the LLM call fires at all.
- **Wire mechanism to Gemini:** always use Gemini's **File API** (upload once, reference by URI) — one code path for all file types, rather than switching between inline base64 and File API by size. File API is mandatory for audio/video anyway, so this avoids a two-path special case for marginal benefit.
- **Model capability display (the "info icon" showing what a model supports):** Gemini's `models.list` metadata is inconsistent across model generations for declaring supported modalities cleanly. Maintained instead as a **small hand-curated static table** (model-name pattern → supported input/output modalities: text/image/audio/video/etc.) in our own code, updated manually as new models ship. Traded a small ongoing maintenance cost for a reliably-correct capability display, rather than an info icon that's sometimes silently wrong.
- **Size limits:** no self-imposed cap — let Gemini's API reject oversized files and surface that error to the UI. Simpler, and at single-user volume the user will notice and adjust immediately.
- **File API expiry:** Gemini's uploaded files expire after 48 hours server-side. **Not engineered around** — documented as a known limitation (a retry after 48h requires re-upload) rather than building an auto-refresh/re-upload mechanism. Revisit only if this proves actually annoying in practice.
- We are **not** building our own file parser/extractor — whatever input handling a given Gemini model natively supports (image understanding, PDF text extraction, etc.) is used as-is through the File API; MCS does no pre-processing of file contents itself.

---

## 14. Explicitly Not Building (Confirmed Non-Goals, Beyond Requirements §17)

Carried from the requirements doc's own out-of-scope list, plus everything resolved during planning:

- No branch merging, no multi-user/auth, no token-by-token streaming, no import/export, no full Node version history, no mobile/responsive layout (all per requirements §17).
- No vector DB, no knowledge graph, no automatic memory decay/forgetting curves (Cognitive Memory doc's entire machinery — rejected as solving a different problem).
- No multi-agent fan-out/decomposition (research report §5), no multi-model ensemble/MoA (§6), no self-critique/redraft loop (§7), no ReAct/Reflexion in-execution reasoning loop (§8), no loop-governance/cost-router layer (§9) — all explicitly Phase-2-or-never for the MCS chat-serving path, since there is no autonomous loop in that path to govern.
- No LangGraph, no DSPy, no LiteLLM gateway — single-provider system has no normalization problem to solve yet.
- No auto-cap/self-imposed file size limits (let the provider's API be the enforcement point).
- No auto-refresh of expired Gemini File API references.
- No SDK dependency for the Gemini adapter (hand-rolled REST instead, for transparency).

---

## 15. Logging (Final)

- Python's standard `logging` module — console + rotating file. No observability stack (Prometheus/Grafana/etc.) — solving a problem this project doesn't have.
- **INFO level:** endpoint, status, latency, model used, token counts.
- **DEBUG level (opt-in flag):** full request/response payloads — acceptable to log full prompts/responses to local disk since there's no third party to protect this from.
- **Hard rule, no exceptions at any log level:** the API key is never written to a log line. Cheap to guarantee, guaranteed regardless of environment.
- No retry/backoff logic on Gemini API errors (rate limit, transient 5xx, malformed response) — **fail fast**, surface the error to the UI, let the user manually retry. Less code, single user, no need for automated resilience.

---

## 16. Failed Request / Retry UX (Final)

- A failed or safety-blocked LLM call **persists nothing** — no Pair is created, consistent with requirements §4.1 (an in-flight/incomplete turn is never part of any lineage).
- Backend returns a structured error object: failure reason, provider error code, human-readable message.
- Frontend keeps the drafted prompt (and any already-uploaded attachments, per §13's separate-upload design) in the input state on failure, and shows a **retry** action that resends the identical request rather than forcing re-entry.

---

## 17. Safety-Blocked / Empty Response Handling (Final)

- Treated as "no response" per requirements §4.1's existing rule — nothing is persisted, exactly like any other failed call (§16 above).
- The error surfaced to the UI carries the actual `finishReason` (`SAFETY` / `RECITATION` / `OTHER` / etc.) and, when Gemini provides them, the per-category safety ratings — so the user sees *why* it was blocked, not just a generic failure.
- **New customization surface added:** project-level configurable safety thresholds, exposing Gemini's `safetySettings` block (e.g. `BLOCK_NONE` / `BLOCK_ONLY_HIGH` / etc. per harm category) as a project setting. This is the direct, actionable lever for reducing false-positive blocks on the user's own content — a natural fit with the project's "customizable, affects response quality" design goal.
- Only ever consider `candidates[0]` from a Gemini response — multiple candidates are not a v2 feature.

---

## 18. Model Picker (Final)

- **Live-fetched** from Gemini's `models.list` endpoint using the user's own API key, filtered to models that support `generateContent`. This automatically reflects whatever the user's specific account/tier is actually entitled to — no separate "which tier" logic needed on our side.
- **Manual free-text entry remains available** as the universal fallback per requirements §12.3 — not removed just because live-fetch works; it's the safety valve for when the list call fails or a brand-new model isn't in the catalog response yet.
- Each model in the picker shows an **info icon** surfacing its supported input/output modalities (text/image/audio/video), sourced from the hand-curated static capability table described in §13 above (not from `models.list`'s unreliable metadata).

---

## 19. Data Model — Full Delta Summary (vs. requirements §3's original schema)

All of the following are **additive** to requirements §3; nothing in the original schema is removed or contradicted.

| Table | Change | Reason |
|---|---|---|
| `Branch` | + `cached_static_token_count` (nullable int) | §8.1 — token meter's static-context cache |
| `Project` | + `persona`, `instructions`, `negative_constraints` (nullable text) | §9 — per-project persona override |
| `Project` | + `safety_settings` (JSON, nullable) | §17 — per-project Gemini safety threshold config |
| `PR Pair` | + `generation_params` (JSON) | §10 — per-turn model/temperature/top_p/max_tokens/effort actually used |
| **New table:** `Attachment` | `id, pair_id, file_path, mime_type, original_filename, size_bytes, created_at` | §13 — multimodal file support |
| **New table:** `GlobalSettings` (singleton) | `persona`, `instructions`, `negative_constraints` | §9 — global persona tier |

---

## 20. Build Order Impact Summary

The original build order (Milestones 0–6, per the build-order doc) remains structurally correct and does not need reordering. The following milestones now carry additional, previously-unscoped work folded in above:

- **Milestone 0 (Foundations):** BYOK header contract (exact header name TBD at TaskSpec time — see §5), plus the new `GlobalSettings` table and the `Attachment` table both belong in the Milestone 0 baseline schema/migration, not bolted on later — attachments and persona settings are core schema now, not a phase-2 add-on.
- **Milestone 1 (Lineage & Tokens):** Token Meter implementation now follows the exact §8 design (cached static + live heuristic), not a naive per-keystroke `countTokens` call.
- **Milestone 3 (Multi-Provider Gateway):** scoped to **Gemini only** (§3, §6, §7 above). Also where the effort/generation-params dial (§10, §11) and the attachment upload/File API integration (§13) land.
- **Milestone 4 (Summary Node Lifecycle):** unchanged in mechanics, confirmed to use the single one-shot summarization call (§12), not the deferred recursive/structured-extraction techniques.
- No milestone needs a schema migration "surprise" later — everything identified above is now known before Milestone 0 starts.

---

## 21. Remaining Open Items Before a TaskSpec Can Be Written

As of this document, the following small items still need a final decision at TaskSpec-writing time (not architecturally significant, but not yet nailed down to an exact value):

1. **Exact BYOK header name** (e.g. `X-Gemini-Api-Key` vs. some other name) — cosmetic, pick one at Milestone 0 TaskSpec time.
2. **Effort-level → Gemini `thinking_budget`/`thinking_level` mapping table** — needs the exact current Gemini model lineup's supported values checked at implementation time, since this varies by model generation and Gemini's API surface here has moved fast.

Everything else in this document is considered locked and ready to be turned into TaskSpecs.

---

*This file is the complete planning record as of this conversation. A future planning session should start from this file alone — the original six source documents remain the ultimate authority for anything not explicitly overridden here, but should not need to be re-read in full for context.*
