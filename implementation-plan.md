# MCS Backend — Implementation Plan (v1)

**Companion file:** `MCS-BACKEND-CONSOLIDATED-SPEC.md` — hand both files together to the
implementing agent. This file is the *build sequence*; the consolidated spec is the
*behavior/architecture authority*. Where they conflict, the consolidated spec wins —
open an issue in the master brief, don't silently resolve it in code.

**How to use this file:** Each Milestone below is self-contained. Copy the milestone's
"Context Packet" + its TaskSpec(s) + the consolidated spec into a **fresh** agent session.
The agent should not need any other conversation history, and should not need to have
"seen" the previous milestone's session to do correct work — every fact it needs to know
about prior milestones is restated in that milestone's Context Packet. Do not run two
milestones in the same agent session back to back; start clean each time so scope
doesn't blur.

**Two agents, same package:** Every TaskSpec here is agent-agnostic. Run it unmodified
against both GLM 5.2 (chat.z.ai) and Kimi 2.6 in parallel, compare the two returned
implementations against `acceptance_criteria`, pick the stronger one (or best-of-both
at the file level). Use `glm-agent-prompt.md` as the system/opening message for either
agent — it's not GLM-specific despite the filename.

---

## 0. Global Engineering Standards (apply to every milestone, don't restate per-task)

These are load-bearing, not decoration. An agent violating these should be treated as
a failed acceptance check even if the feature "works."

1. **No God files.** One responsibility per module. `app/domain/*.py` files contain
   zero FastAPI imports, zero SQLAlchemy session imports — pure functions/classes
   operating on plain Python objects or Pydantic models passed in. This is not a
   style preference: it's what makes `LineageAssembler` unit-testable without a
   database, which is the whole point of Milestone 1's acceptance criterion.
2. **Type hints everywhere**, `mypy --strict`-clean (or explicitly note a suppression
   with a one-line reason — no silent `# type: ignore` walls).
3. **No bare `except:`.** Catch specific exceptions. Provider/network errors get their
   own exception classes (`app/providers/exceptions.py`) — `GeminiAPIError`,
   `GeminiSafetyBlockError`, etc. — never a generic `Exception` swallow.
4. **No print() debugging left in.** Use the `logging` module per consolidated spec §15.
   The API key must never reach a log line at any level — this is checked explicitly
   in every review, not assumed.
5. **Every endpoint has a Pydantic request model and a Pydantic response model.**
   No raw `dict` in, raw `dict` out, even for tiny endpoints.
6. **Every domain service is unit-tested without spinning up FastAPI or a real DB
   file** (use an in-memory SQLite or plain fixtures — see each milestone's test
   requirements). Integration tests (`tests/api/`) are separate and cover the
   HTTP layer only.
7. **Migrations are never hand-edited after being committed.** A schema change after
   the fact is a new Alembic revision, never an edit to an old one.
8. **No speculative abstraction.** Don't build a plugin system, a generic event bus,
   or a config-driven rules engine "in case we need it later." If the consolidated
   spec says one provider, write one adapter and one clean interface — resist the
   urge to over-generalize before Phase 2 actually asks for it.
9. **Docstrings on every public function/class in `app/domain/` and `app/providers/`**
   stating the requirements section it implements, e.g. `"""Implements consolidated
   spec §4.3 (per-ancestor truncation at fork Pair)."""` — this is what makes a
   review against `acceptance_criteria` fast instead of archaeological.
10. **Commit-sized diffs.** Each TaskSpec should be returned as a self-contained diff/
    file-set matching exactly its `affected_modules` — not a drive-by refactor of
    unrelated files.

---

## Milestone Map (for your own tracking — not part of any single agent handoff)

| # | Milestone | Depends on schema/code from | Status |
|---|---|---|---|
| 0 | Foundations | — | ☐ |
| 1 | Lineage & Tokens | M0 schema | ☐ |
| 2 | Branching Mechanics & Nodes | M0 schema, M1 lineage (read-only dependency) | ☐ |
| 3 | Gemini Gateway | M0 BYOK plumbing | ☐ |
| 4 | Summary Node Lifecycle | M1 lineage, M3 Gemini adapter | ☐ |
| 5 | Temporary Branches | M1 lineage | ☐ |
| 6 | Eagle View & Cascading Deletes | M0 schema, M2 branch/node CRUD | ☐ |

Build in this order. Do not start M4 before M1 and M3 are both merged and reviewed —
it genuinely needs both. Everything else can be reordered if reality intrudes, per the
build-order doc's own philosophy.

---
---

# MILESTONE 0 — Foundations

## Context Packet (paste this + the TaskSpec into a fresh session — nothing else needed)

You are implementing the first milestone of a from-scratch Python backend. There is no
existing code. You're building:
- A FastAPI app with async SQLAlchemy 2.0 + SQLite (`aiosqlite`) + Alembic.
- Five tables at this stage: `Project`, `Branch`, `PRPair`, `Node`, `GraphLayoutPosition`,
  plus two more identified during planning: `Attachment` and `GlobalSettings` (singleton).
- BYOK plumbing: the API key travels in a request header named exactly
  **`X-Gemini-Api-Key`** on every LLM-calling endpoint, is validated to be present,
  passed through to the provider call, and is **never** persisted to disk, never
  logged at any level, never read from a server-side `.env`/config file as a fallback.
- Creating a `Project` auto-creates its Root `Branch` (branch with no parent, `type='standard'`).

You do **not** need to know anything about lineage assembly, token counting, Gemini's
wire format, or Summary Nodes to do this work correctly — none of that logic lives in
this milestone. Stub it out; other milestones own it.

## TaskSpec

```json
{
  "task_id": "M0-T1",
  "milestone_ref": "Milestone 0 — Foundations",
  "target_agent": "glm-5.2",
  "goal": "Scaffold the FastAPI project, SQLAlchemy models, Alembic baseline migration, and BYOK header plumbing.",
  "scope": "feature",
  "requirements_refs": [
    "consolidated-spec#1 (Mission)",
    "consolidated-spec#4 (Locked Technical Stack)",
    "consolidated-spec#5 (BYOK & Key Handling)",
    "consolidated-spec#19 (Data Model Delta Summary)"
  ],
  "affected_modules": [
    "pyproject.toml",
    "alembic.ini",
    "alembic/env.py",
    "alembic/versions/0001_initial.py",
    "app/main.py",
    "app/config.py",
    "app/db/session.py",
    "app/db/models.py",
    "app/schemas/project.py",
    "app/schemas/branch.py",
    "app/schemas/global_settings.py",
    "app/deps.py",
    "app/api/projects.py",
    "app/api/health.py",
    "tests/api/test_health.py",
    "tests/api/test_projects.py",
    "tests/domain/test_byok_header.py"
  ],
  "constraints": [
    "Header name is exactly 'X-Gemini-Api-Key' — do not invent a different name or make it configurable in this milestone",
    "app/deps.py must expose a single FastAPI dependency, e.g. get_gemini_api_key(), that every future LLM-calling endpoint will import — build it now even though no LLM endpoint exists yet, so it structurally cannot be bypassed later",
    "The dependency raises HTTP 401 with a clear message if the header is missing — do not silently allow None through",
    "No .env fallback read for the Gemini key anywhere in this codebase, not even for local dev convenience",
    "Project model fields (per requirements schema, additive per consolidated spec §19): id, name, created_at, persona (nullable text), instructions (nullable text), negative_constraints (nullable text), safety_settings (nullable JSON), default_provider, default_model, custom_base_url (nullable), token_limit (nullable int)",
    "Branch model fields: id, project_id (FK), parent_branch_id (nullable FK, self-referential), parent_pr_pair_id (nullable FK to PRPair, set once fork logic exists in M2 — nullable now), type (enum: 'standard'|'temporary', default 'standard'), label (nullable text), cached_static_token_count (nullable int), created_at",
    "PRPair, Node, GraphLayoutPosition, Attachment: create as SQLAlchemy models with the fields listed in consolidated-spec §19's delta table plus whatever base fields are obviously implied by their name (id, project_id/branch_id FKs, created_at) — do NOT invent behavior-specific fields (e.g. no summary linkage fields on PRPair yet, that's Milestone 4's job) beyond generation_params (JSON) which IS specified now",
    "GlobalSettings is a singleton table — enforce exactly one row exists (e.g. fixed primary key = 1, or a service-layer guard), fields: persona, instructions, negative_constraints (all nullable text)",
    "ON DELETE CASCADE at the DB level for Project -> Branch -> PRPair/Node/GraphLayoutPosition/Attachment per consolidated spec's cascade intent (full cascade matrix is Milestone 6's job to test exhaustively — but the FK constraints must exist now, or M6 has nothing to test)"
  ],
  "must_not": [
    "Do not implement LineageAssembler, TokenEstimator, mention resolution, or any Gemini adapter code — those are separate milestones",
    "Do not add a fork-from-pair endpoint — POST /projects creating the Root branch is the only branch-creation logic in this milestone",
    "Do not make the BYOK header name configurable via settings/env in this milestone",
    "Do not add authentication/user accounts — single-user, no auth, per non-goals"
  ],
  "acceptance_criteria": [
    "POST /projects with a valid body creates a Project row AND a Branch row with parent_branch_id=NULL, parent_pr_pair_id=NULL, type='standard' in the same transaction",
    "GET /health returns 200 with no DB dependency",
    "An endpoint protected by get_gemini_api_key() returns 401 when X-Gemini-Api-Key is absent, and passes the key through to the handler when present (write one throwaway test endpoint or reuse a real stub for this proof)",
    "grep-ing the entire repo for the literal API key value used in a test never matches any file under a logs/ directory or any emitted log line (assert this in a test that captures log output during a request)",
    "alembic upgrade head runs clean against a fresh SQLite file and creates all 7 tables",
    "mypy --strict passes on app/ with zero unsuppressed errors"
  ],
  "verification": "unit_tests",
  "effort_hint": "medium"
}
```

---
---

# MILESTONE 1 — Lineage & Tokens

## Context Packet (paste this + the TaskSpec into a fresh session)

Milestone 0 already exists and is merged. You have these facts about the schema —
you do not need to see M0's code, just trust these fields exist:

- `Branch(id, project_id, parent_branch_id, parent_pr_pair_id, type, label, cached_static_token_count, created_at)`
- `PRPair(id, branch_id, prompt_text, response_text, generation_params, created_at)` —
  **a PRPair only exists once it has both a prompt and a completed response.** A pending/
  in-flight turn is never written as a row at all (this is enforced upstream by Milestone 3's
  gateway, not by you — you can assume every PRPair row you ever see is complete).
- `Node(id, project_id, name, content, type, version_counter, created_at)` — `type` is
  `'manual'` or `'summary'`. Summary-specific linkage fields (`linked_summary_node_id`,
  `summary_cutoff_position` on `Branch`) **do not exist yet** — Milestone 4 adds them.
  For this milestone, write `LineageAssembler` to check for their presence defensively
  (e.g. `getattr(branch, "linked_summary_node_id", None)`) so M4 can wire it in later
  without you having to be re-invoked, OR simply add those two nullable fields to `Branch`
  yourself as part of this TaskSpec's migration if that's cleaner — your call, note which
  you did in your PR description.

Your job is the single most important module in this entire backend: given a Branch,
walk its ancestor chain and produce the exact ordered list of Pairs that should be sent
to the LLM as conversation history, handling forking/sibling-exclusion correctly, then
estimate tokens on top of that assembled payload.

**The one test that matters most:** a Branch tree like `Root(R1,R2) -> Backend(B1,B2,B3)`,
with a branch "Auth" forked from Backend at the point right after B2 (i.e. before B3
existed, or B3 is a sibling that came after the fork point) — lineage for "Auth" must
include `R1, R2, B1, B2` and **must not** include `B3` (B3 is a sibling on the Backend
branch's own continued timeline, not an ancestor of Auth). If you're not looking at the
actual `mcs-v2-requirements.md` §4.5 worked example text, treat the paragraph above as
the literal spec for this test — do not reinterpret it.

## TaskSpec

```json
{
  "task_id": "M1-T1",
  "milestone_ref": "Milestone 1 — Lineage & Tokens",
  "target_agent": "glm-5.2",
  "goal": "Implement LineageAssembler (ancestor-chain walk with correct fork/sibling handling) and TokenEstimator (static-cached + live-heuristic split) as pure domain services.",
  "scope": "feature",
  "requirements_refs": [
    "consolidated-spec#1 (v1 bugs are now permanent correctness requirements)",
    "consolidated-spec#8 (Token Estimation Strategy, full §8.1/8.2/8.3)",
    "context-packet-above (fork/sibling-exclusion worked example)"
  ],
  "affected_modules": [
    "app/domain/lineage.py",
    "app/domain/tokens.py",
    "app/schemas/lineage.py",
    "app/api/graph.py::token_meter_endpoint (add only the endpoint, not full Eagle View — that's M6)",
    "tests/domain/test_lineage.py",
    "tests/domain/test_tokens.py"
  ],
  "constraints": [
    "app/domain/lineage.py and app/domain/tokens.py contain zero FastAPI imports and zero SQLAlchemy Session imports — they operate on plain dataclasses/Pydantic models passed in by the caller (the API layer does the DB fetch, then calls these pure functions)",
    "A Pair with no response is never included in any lineage — encode this as a precondition/assertion, not a silent filter, since it should structurally never happen given M0's constraint",
    "LineageAssembler must walk parent_branch_id + parent_pr_pair_id to find the exact fork point and include only ancestor Pairs at-or-before that fork point on each ancestor branch — never later Pairs on an ancestor branch's own continued timeline",
    "TokenEstimator per consolidated spec §8: split output into static_context_tokens (from Branch.cached_static_token_count, exact/cached) and a documented hook for live_input_tokens (heuristic, computed client-side per §8.2 — your endpoint only needs to return the static/cached number plus expose a countTokens-refresh path per §8.1's two stale-cache trigger cases)",
    "Do not call the actual Gemini countTokens API in this milestone — stub the refresh function with a clear TODO/interface (Milestone 3 wires the real Gemini call in); test it with a fake token-counter function injected via dependency"
  ],
  "must_not": [
    "Do not implement Summary Node injection logic (linked_summary_node_id/summary_cutoff_position handling) beyond the defensive getattr/optional-field support described in the context packet — full Summary lifecycle is Milestone 4",
    "Do not implement Temporary Branch's stateless-lineage exception — that is Milestone 5, a separate TaskSpec; a normal ancestor walk is all this milestone should assume",
    "Do not touch app/domain/nodes.py or any @mention resolution logic — that is Milestone 2's TaskSpec, even though Referenced Knowledge rendering is conceptually adjacent",
    "Do not call the real tiktoken or Gemini countTokens API from inside app/domain/tokens.py directly — accept a token-counting callable as a parameter so it stays a pure, injectable function"
  ],
  "acceptance_criteria": [
    "The Root(R1,R2) -> Backend(B1,B2,B3) -> Auth(forked after B2) worked example passes as a literal unit test: Auth's assembled lineage == [R1,R2,B1,B2] and explicitly asserts B3 is absent",
    "A branch forked from Root before any Pair exists produces an empty ancestor contribution (parent_pr_pair_id=None handled without error)",
    "A 3-level-deep fork chain (Root -> A -> B -> C, each forked at a different mid-branch point) produces the correct concatenated, correctly-ordered list with no duplicate Pairs and no cross-sibling leakage at any level",
    "TokenEstimator returns cached Branch.cached_static_token_count directly with zero calls to the injected token-counter when the cache is non-null and no Summary state has changed since caching",
    "TokenEstimator triggers exactly one call to the injected token-counter callable when cache is null (fresh branch, no sends yet)",
    "mypy --strict passes on app/domain/lineage.py and app/domain/tokens.py with zero unsuppressed errors"
  ],
  "verification": "unit_tests",
  "effort_hint": "high"
}
```

---
---

# MILESTONE 2 — Branching Mechanics, Sidebar Support & Nodes

## Context Packet (paste this + the TaskSpec into a fresh session)

M0 (schema) and M1 (`LineageAssembler`, `TokenEstimator` — pure functions, importable
from `app.domain.lineage` / `app.domain.tokens`) already exist and are merged. You do
not need to modify either — you're building the CRUD/API layer that sits on top of and
around them, plus a fully separate concern (`@mention` Node resolution).

Known schema facts you can rely on: `Branch`, `PRPair`, `Node` tables exist exactly as
described in Milestone 1's context packet above.

## TaskSpec

```json
{
  "task_id": "M2-T1",
  "milestone_ref": "Milestone 2 — Branching Mechanics & Nodes",
  "target_agent": "glm-5.2",
  "goal": "Branch fork/label/delete endpoints with the completed-Pair-scoping rule, branch-count queries, and Node CRUD with @mention resolution + cycle detection.",
  "scope": "feature",
  "requirements_refs": [
    "consolidated-spec#1 (v1 bug: actions belong to the completed Pair, response side, never the prompt bubble, unavailable while a response is pending)"
  ],
  "affected_modules": [
    "app/api/branches.py",
    "app/api/pairs.py",
    "app/api/nodes.py",
    "app/domain/nodes.py",
    "app/schemas/branch.py",
    "app/schemas/pair.py",
    "app/schemas/node.py",
    "tests/domain/test_nodes.py",
    "tests/api/test_branches.py",
    "tests/api/test_nodes.py"
  ],
  "constraints": [
    "'Branch from here' and 'Delete' actions take a pr_pair_id, not a branch_id + prompt text — they are scoped to a completed Pair by construction, making the v1 bug (prompt-bubble scoping) structurally impossible rather than merely avoided by convention",
    "Fork-from-Pair endpoint accepts a pr_pair_id (which may be mid-branch, not just the tip) and creates a new Branch with parent_branch_id = that pair's branch, parent_pr_pair_id = that pair's id",
    "Branch-count-per-Pair is a single aggregate query (COUNT of Branches grouping by parent_pr_pair_id), not N+1 per-pair queries — expose it as one endpoint returning counts for all Pairs in a branch at once",
    "'Move to parent pair' is a lookup, not a mutation: given a branch, return the PRPair it was forked from (or null for Root)",
    "Node uniqueness is per-project, case-sensitive exact match on name, enforced at the DB level (unique constraint on (project_id, name)), not just application-level validation",
    "Circular-reference detection for @mentions happens at Node save time: if Node A's content @mentions Node B, and B (transitively) @mentions A, reject the save with a 400 and a clear error naming the cycle",
    "@mention resolution is recursive but must terminate — the cycle check above is what makes recursion safe, not a depth limit as a band-aid"
  ],
  "must_not": [
    "Do not implement Summary Node type-specific behavior (Keep/Replace/Disconnect/Delete state machine) — Node CRUD here treats type='summary' Nodes as opaque, no different from type='manual' for storage purposes; Milestone 4 owns the state machine",
    "Do not implement Temporary Branch stateless lineage — that's Milestone 5",
    "Do not implement the Eagle View graph endpoint or GraphLayoutPosition CRUD — that's Milestone 6",
    "Do not call LineageAssembler or TokenEstimator from these endpoints in a way that changes their behavior — if you need lineage data for a branch-tree display, call the existing pure function as-is"
  ],
  "acceptance_criteria": [
    "Attempting 'Branch from here' or 'Delete' on a PRPair whose response_text is null/pending returns 409, not 200 with broken state",
    "Forking mid-branch (not from the tip) correctly sets parent_pr_pair_id to the mid-branch Pair, and the new branch's later lineage assembly (via M1's LineageAssembler, called end-to-end in an integration test) excludes Pairs on the parent branch after that fork point",
    "Creating a Node named identically (case-sensitive) to an existing Node in the same project returns 409",
    "Creating Node A that @mentions Node B, then editing Node B to @mention Node A, is rejected with 400 and does not save",
    "Branch-count-per-Pair endpoint returns correct counts for a branch with 5 Pairs and a mix of 0-3 forks per Pair, using a query plan with no N+1 pattern (assert via query-count assertion in the test, e.g. using SQLAlchemy's statement counter)"
  ],
  "verification": "integration_tests",
  "effort_hint": "high"
}
```

---
---

# MILESTONE 3 — Gemini Gateway

## Context Packet (paste this + the TaskSpec into a fresh session)

M0's BYOK dependency (`get_gemini_api_key()` in `app/deps.py`, reading the
`X-Gemini-Api-Key` header) already exists — import and use it, do not rebuild it.
M1's `LineageAssembler`/`TokenEstimator` exist and produce the payload you'll send.

**Scope ruling (locked):** exactly one live provider, Gemini, via Google AI Studio's
`generativelanguage.googleapis.com` (v1beta), **not** Vertex AI. Auth is
`x-goog-api-key` header on the outbound Gemini call (not `?key=` query param — same
leak-vector reasoning as the inbound BYOK header). Hand-rolled `httpx` calls, **not**
the `google-genai` SDK — this keeps the wire contract auditable, per the project's
explicit "understand what's happening" design goal.

**Effort/thinking dial (resolved during planning — use this table, don't re-derive it):**
Gemini has two incompatible mechanisms depending on model generation, and sending both
in the same request is a 400 error:
- **Gemini 2.5-series models:** `thinking_config.thinking_budget` — an integer token
  cap. `0` disables thinking. `-1` means "dynamic, model decides." Reasoning cannot be
  fully disabled on 2.5 Pro specifically (sending 0 to Pro is rejected/ignored depending
  on sub-version — treat a rejection here as a normal provider error, not a bug in your code).
- **Gemini 3.x-series models (3, 3.1, 3.5, and later):** `thinking_config.thinking_level`
  — an enum string, either `"MINIMAL"|"LOW"|"MEDIUM"|"HIGH"` (Flash-family) or
  `"LOW"|"HIGH"` (Pro-family — check the specific model's supported set, don't assume
  Flash's full set applies to Pro). Thinking cannot be disabled at all on 3/3.1 Pro.
- Build a small static lookup (same pattern as the multimodal capability table in
  consolidated spec §13): `model_name_pattern -> {"param": "thinking_budget"|"thinking_level", "values": {...}}`.
  MCS's own user-facing effort levels are `low | medium | high | max`. Map each MCS
  level to the correct provider-native value **for whichever model is actually selected**
  — this mapping is a lookup, not a fixed constant, because the same MCS "high" means
  a token budget number on one model family and an enum string on another.
- If a selected model has no thinking support at all (non-thinking models still exist
  in the catalog), the adapter must simply omit `thinking_config` entirely rather than
  erroring — detect this from the same capability table.

## TaskSpec

```json
{
  "task_id": "M3-T1",
  "milestone_ref": "Milestone 3 — Gemini Gateway",
  "target_agent": "glm-5.2",
  "goal": "Implement the abstract LLMProvider interface and a concrete Gemini adapter (chat_completion, list_models, countTokens) using hand-rolled httpx calls, wired to the existing BYOK dependency.",
  "scope": "feature",
  "requirements_refs": [
    "consolidated-spec#3 (Scope Ruling — Gemini only)",
    "consolidated-spec#5 (BYOK wire contract)",
    "consolidated-spec#6 (Gemini API Surface — locked decisions)",
    "consolidated-spec#7 (Message-Shape Mapping)",
    "consolidated-spec#10 (Generation Parameters Per Turn)",
    "consolidated-spec#11 (Effort dial scope) + context-packet-above (exact thinking param mapping)",
    "consolidated-spec#16 (Failed Request / Retry UX)",
    "consolidated-spec#17 (Safety-Blocked / Empty Response Handling)",
    "consolidated-spec#18 (Model Picker)"
  ],
  "affected_modules": [
    "app/providers/base.py",
    "app/providers/gemini_provider.py",
    "app/providers/exceptions.py",
    "app/providers/thinking_map.py",
    "app/providers/capability_table.py",
    "app/api/chat.py",
    "app/api/models_catalog.py",
    "app/schemas/chat.py",
    "tests/domain/test_gemini_provider.py",
    "tests/domain/test_thinking_map.py"
  ],
  "constraints": [
    "LLMProvider ABC signature: chat_completion(system: str, messages: list[Message], **params) -> ChatResponse; list_models() -> list[ModelInfo]; count_tokens(system, messages) -> int",
    "All Gemini-specific remapping (assistant->model role rename, content->parts, system pulled into systemInstruction) happens only inside gemini_provider.py — the ABC and callers never see Gemini's wire shape",
    "Outbound auth to Gemini uses the x-goog-api-key header, never a ?key= query param",
    "API version v1beta, host generativelanguage.googleapis.com",
    "Use httpx.AsyncClient directly — no google-genai SDK dependency anywhere in this module",
    "thinking_map.py implements the exact lookup described in the context packet: given a model name and an MCS effort level (low/medium/high/max), return either a thinking_budget int or a thinking_level string, or omit thinking_config entirely for non-thinking models — this must be unit-testable with zero network calls",
    "A failed or safety-blocked call persists nothing — do not write a PRPair row on any error path; that's the caller's (API layer's) responsibility to enforce by only committing after a successful ChatResponse, but this adapter must make failure vs. success unambiguous via distinct exception types so the caller can't accidentally treat a safety block as success",
    "On safety block, raise GeminiSafetyBlockError carrying the actual finishReason and per-category safety ratings when present — do not flatten this into a generic error string",
    "count_tokens() calls Gemini's real countTokens endpoint — this is what Milestone 1's TokenEstimator stale-cache refresh hook calls in production; wire that connection in this milestone (import and pass this function where M1 left a stub/injectable slot)",
    "No retry/backoff logic — fail fast on any Gemini error, surface a structured error object (reason, provider error code, human-readable message) to the caller"
  ],
  "must_not": [
    "Do not implement OpenAI/Anthropic/OpenRouter/custom adapters — Gemini only, per the locked scope ruling",
    "Do not implement Attachment upload / File API integration in this task — that is a separate, explicitly-scoped follow-up TaskSpec (M3-T2) even though it's nominally part of Milestone 3",
    "Do not implement the Summary generation call — that's Milestone 4's one-shot summarization call, a different call site even though it reuses this same chat_completion() method",
    "Do not add retry/backoff logic even 'just for transient 5xx errors' — this is an explicit non-goal, fail fast per §15"
  ],
  "acceptance_criteria": [
    "A real (or realistically mocked, via respx/httpx mock transport) chat_completion() call against a 2.5-series model name uses thinking_budget in the request body, never thinking_level",
    "The same call against a 3.x-series model name uses thinking_level, never thinking_budget, and errors loudly in a unit test if both are ever set simultaneously (guard this in code, not just by convention)",
    "A model with no thinking support in the capability table produces a request body with no thinking_config key at all",
    "list_models() filters to models supporting generateContent only",
    "A simulated safety-blocked response (finishReason=SAFETY) raises GeminiSafetyBlockError with the safety ratings attached, and does not raise a generic exception that would be indistinguishable from a network failure",
    "The outbound request in every test assertion uses the x-goog-api-key header, and no test ever asserts on a ?key= query param construction",
    "mypy --strict passes on app/providers/ with zero unsuppressed errors"
  ],
  "verification": "unit_tests",
  "effort_hint": "high"
}
```

```json
{
  "task_id": "M3-T2",
  "milestone_ref": "Milestone 3 — Gemini Gateway (Attachments)",
  "target_agent": "glm-5.2",
  "goal": "Implement the Attachment upload endpoint and Gemini File API integration, as a separate concern from chat_completion.",
  "scope": "feature",
  "requirements_refs": [
    "consolidated-spec#13 (Multimodal / File Attachments)"
  ],
  "affected_modules": [
    "app/api/attachments.py",
    "app/domain/attachments.py",
    "app/providers/gemini_files.py",
    "app/schemas/attachment.py",
    "tests/api/test_attachments.py",
    "tests/domain/test_gemini_files.py"
  ],
  "constraints": [
    "POST /attachments is a separate endpoint from the send-message endpoint — it returns an attachment_id before any LLM call happens, so a failed send can be retried with the same already-uploaded files",
    "Always use Gemini's File API (upload once, reference by URI) for every file type, image included — do not special-case small images to inline base64",
    "Files are stored on local disk under a project-scoped data directory; the Attachment row stores file_path, mime_type, original_filename, size_bytes",
    "No self-imposed size cap — let Gemini's API reject oversized files and propagate that error as-is to the caller",
    "File API expiry (48h) is not engineered around — no auto-refresh/re-upload logic; document the limitation in a docstring, that's the entire mitigation"
  ],
  "must_not": [
    "Do not build any file content parsing/extraction (no PDF text extraction, no image analysis) — MCS passes files through untouched, Gemini does all interpretation",
    "Do not build an auto-refresh mechanism for expired File API references",
    "Do not add a configurable max-file-size setting"
  ],
  "acceptance_criteria": [
    "POST /attachments with a valid file returns an attachment_id and persists file_path/mime_type/original_filename/size_bytes",
    "The same attachment_id can be referenced in two separate (simulated) send attempts without re-uploading",
    "An oversized-file rejection from the (mocked) Gemini File API surfaces its actual error message to the caller rather than being caught and replaced with a generic message"
  ],
  "verification": "unit_tests",
  "effort_hint": "low"
}
```

---
---

# MILESTONE 4 — Summary Node Lifecycle

## Context Packet (paste this + the TaskSpec into a fresh session)

**Hard prerequisite: M1 and M3 must both already be merged before this milestone
starts** — this is the one milestone that genuinely can't be built against a stub,
because it calls the real `chat_completion()` from M3 and must integrate with the
real `LineageAssembler` from M1.

Known facts: `Branch` has (or M1 already added) `linked_summary_node_id` (nullable FK
to Node) and `summary_cutoff_position` (nullable, e.g. an integer index into the
Pair sequence or a FK to a specific PRPair — implementer's choice, document it clearly
in the PR). `Node.type` includes `'summary'`.

## TaskSpec

```json
{
  "task_id": "M4-T1",
  "milestone_ref": "Milestone 4 — Summary Node Lifecycle",
  "target_agent": "glm-5.2",
  "goal": "Implement SummaryService: Generate (one-shot summarization call over current effective lineage) -> Keep/Replace/Disconnect/Delete state machine.",
  "scope": "feature",
  "requirements_refs": [
    "consolidated-spec#12 (Summarization / Compaction Strategy)",
    "consolidated-spec#8.1 (Token Meter must visibly react to Replace/Disconnect immediately, not on next send)"
  ],
  "affected_modules": [
    "app/domain/summaries.py",
    "app/api/summaries.py",
    "app/schemas/summary.py",
    "tests/domain/test_summaries.py",
    "tests/api/test_summaries.py"
  ],
  "constraints": [
    "Generate: compute the branch's current effective lineage via the existing LineageAssembler (M1, import as-is, do not modify), send it through a single fixed summarization prompt via the existing gemini_provider.chat_completion() (M3, import as-is), produce a draft Node (type='summary') that is shown to the user before anything is applied — the draft is not saved as the branch's active summary until Keep/Replace is chosen",
    "Node naming: auto-generate a name and de-duplicate against existing Node names in the project (reuse M2's Node uniqueness constraint — if a collision occurs, append a counter suffix, do not fail the generate step)",
    "Replace sets Branch.linked_summary_node_id and Branch.summary_cutoff_position; LineageAssembler must respect this by short-circuiting the ancestor walk at the cutoff and injecting the summary content instead of the full pre-cutoff history — if this requires a change to app/domain/lineage.py, make the MINIMAL addition needed (an optional summary-injection branch in the existing function), do not rewrite the module",
    "Disconnect restores raw lineage assembly (clears linked_summary_node_id/summary_cutoff_position) but keeps the Node row intact (still @mentionable manually)",
    "Delete does Disconnect's restore + Node row deletion in one transaction",
    "Keep vs Delete/Disconnect must trigger an immediate Branch.cached_static_token_count recompute (calling M3's real count_tokens, not the stale cache) — the token meter must visibly change the instant this happens per consolidated spec §8.1, not wait for the next send",
    "A Summary Node's content is editable afterward exactly like a manual Node (reuse M2's Node update endpoint/logic, do not duplicate it)"
  ],
  "must_not": [
    "Do not build recursive/hierarchical summarization or structured-state-extraction (DECISIONS/FACTS/etc.) — a single one-shot call over the bounded lineage is the entire technique",
    "Do not mutate any ancestor branch's own data or lineage — Summary is scoped strictly to the one branch it was generated from",
    "Do not rewrite app/domain/lineage.py's core ancestor-walk algorithm — only add the summary-injection short-circuit as a minimal, clearly-marked addition",
    "Do not implement Temporary Branch restrictions here — Milestone 5 owns rejecting 'Summarize' on Temporary Branches"
  ],
  "acceptance_criteria": [
    "Generate produces a draft Node that is NOT yet linked to the branch (linked_summary_node_id unchanged) until Replace is explicitly called",
    "Replace on a branch with a 10-Pair lineage and cutoff at Pair 6 produces an assembled lineage (via LineageAssembler) of [summary content, Pairs 7-10] — verified as a literal integration test, not just a unit test of the state flags",
    "Disconnect on that same branch restores the full [Pairs 1-10] lineage with no summary injection, and the Token Meter's re-fetched value strictly increases compared to the Replace state",
    "Delete removes the Node row entirely; a subsequent GET for that node_id returns 404",
    "Editing a Summary Node's content uses the exact same endpoint/code path as editing a manual Node (assert this via code reference, not duplicated logic, in the PR description)"
  ],
  "verification": "integration_tests",
  "effort_hint": "high"
}
```

---
---

# MILESTONE 5 — Temporary Branches

## Context Packet (paste this + the TaskSpec into a fresh session)

M1's `LineageAssembler` exists and is merged. This milestone is a small, surgical
addition to it — not a new subsystem. `Branch.type` is `'standard'` or `'temporary'`
(field already exists from M0).

## TaskSpec

```json
{
  "task_id": "M5-T1",
  "milestone_ref": "Milestone 5 — Temporary Branches",
  "target_agent": "glm-5.2",
  "goal": "Add stateless-within-itself lineage assembly for Temporary Branches as a flag-driven exception in LineageAssembler, plus fork-to-standard and Summarize-rejection behavior.",
  "scope": "feature",
  "requirements_refs": [
    "consolidated-spec (Temporary Branches are a flag/branch type, not a new subsystem, per master brief §5 responsibility map)"
  ],
  "affected_modules": [
    "app/domain/lineage.py",
    "app/api/branches.py",
    "app/api/summaries.py",
    "tests/domain/test_lineage_temporary.py",
    "tests/api/test_temporary_branches.py"
  ],
  "constraints": [
    "When assembling lineage for a Pair being sent within a Temporary Branch, exclude that Temporary Branch's own prior Pairs from the payload — the ancestor chain above the fork point is unaffected and still included normally",
    "This is a minimal, clearly-marked conditional inside the existing LineageAssembler function (branch on Branch.type == 'temporary') — do not fork the function into two parallel implementations",
    "Forking from a Pair inside a Temporary Branch to create a new standard branch is allowed and behaves like any normal fork (the new branch is 'standard' type, gets the full ancestor chain including that Temporary Branch's own Pairs up to the fork point)",
    "The Summarize endpoint (M4) must reject requests where the target branch's type == 'temporary' with a 400 and a clear message — add this as a guard clause in app/api/summaries.py, do not touch app/domain/summaries.py's internals"
  ],
  "must_not": [
    "Do not create a separate TemporaryLineageAssembler class or module — this is a conditional inside the existing one",
    "Do not allow Temporary Branch's own Pairs to be included in ANY other branch's lineage either (they're a dead end, not a reusable ancestor) — verify this doesn't accidentally regress via a fork-from-Temporary-Pair test"
  ],
  "acceptance_criteria": [
    "Sending 3 sequential messages within a single Temporary Branch produces 3 independent lineage assemblies, each identical (same ancestor-chain content) except for the new prompt — none of the Temporary Branch's own prior 3 turns compound into later ones",
    "A fork from a mid-Temporary-Branch Pair to a new standard branch correctly includes the ancestor chain PLUS that Temporary Branch's Pairs up to the fork point (the new branch is not itself temporary, so normal accumulation rules apply to it going forward)",
    "POST to the Summarize endpoint against a Temporary Branch returns 400 and does not call SummaryService at all (assert via mock call-count of zero)"
  ],
  "verification": "integration_tests",
  "effort_hint": "medium"
}
```

---
---

# MILESTONE 6 — Eagle View Data & Cascading Deletes

## Context Packet (paste this + the TaskSpec into a fresh session)

M0 (schema, all FK constraints already in place), M2 (Branch/Node CRUD) exist and are
merged. This milestone is read-only graph serving plus destructive-action correctness
— it's easy to under-test this one, don't.

## TaskSpec

```json
{
  "task_id": "M6-T1",
  "milestone_ref": "Milestone 6 — Eagle View & Cascading Deletes",
  "target_agent": "glm-5.2",
  "goal": "Serve the read-only Eagle View graph (Pairs/Branches/Nodes + real edges including Summary Node edges), CRUD GraphLayoutPosition as pure cosmetic data, and verify the full cascade-delete matrix.",
  "scope": "feature",
  "requirements_refs": [
    "consolidated-spec (GraphLayoutPosition is purely cosmetic, zero effect on lineage/tokens, master brief §5/§8.4)"
  ],
  "affected_modules": [
    "app/api/graph.py",
    "app/schemas/graph.py",
    "tests/api/test_graph.py",
    "tests/api/test_cascade_deletes.py"
  ],
  "constraints": [
    "The graph endpoint returns all Pairs/Branches/Nodes for a project plus their real edges: parent Branch->Branch fork edges, Branch->PRPair sequence edges, and — for any Branch with an active linked_summary_node_id — a distinctly-typed edge from that Summary Node to its cutoff point in the graph",
    "GraphLayoutPosition CRUD (x/y/z or whatever coordinate fields the schema defines) must have zero read or write interaction with app/domain/lineage.py or app/domain/tokens.py — this table is display-only; a unit test should prove that deleting all GraphLayoutPosition rows for a project does not change any TokenEstimator or LineageAssembler output",
    "Cascade matrix to implement/verify at the DB constraint level: Project delete -> cascades to Branches -> Pairs/Nodes/GraphLayoutPositions/Attachments all removed; Branch delete -> cascades to its own Pairs AND to descendant Branches (forked from it) recursively; Node delete -> any future @mention of it must resolve to a 'not found' state at render time, but past AI responses that already rendered that mention's content are untouched (the historical PRPair.response_text is not retroactively edited)"
  ],
  "must_not": [
    "Do not add any layout-affects-behavior logic — if you find yourself writing code where GraphLayoutPosition changes a lineage or token result, stop, that's a spec violation",
    "Do not build pagination or virtualized-loading logic for the graph endpoint — spec explicitly says tens-to-~100 branches, keep it simple, return everything in one response"
  ],
  "acceptance_criteria": [
    "A project with 3 branches (one with an active Summary) returns a graph payload whose edge list includes exactly one Summary-type edge, correctly pointing at the cutoff Pair",
    "Deleting a Project deletes all of its Branches, Pairs, Nodes, GraphLayoutPositions, and Attachments in one transaction — verified by row-count assertions on all 5 child tables, not just checking the Project row is gone",
    "Deleting a mid-tree Branch that has 2 descendant forked Branches deletes all 3 branches (itself + both descendants) and their Pairs, recursively",
    "Deleting a Node that is @mentioned in an already-completed PRPair leaves that PRPair's stored response_text completely unchanged; a NEW Pair created afterward that tries to @mention the deleted Node's name resolves to a 'not found' state rather than an error or stale content",
    "A test explicitly proves GraphLayoutPosition deletion has zero effect on LineageAssembler/TokenEstimator output for the same branch"
  ],
  "verification": "integration_tests",
  "effort_hint": "medium"
}
```

---
---

# Appendix A — Decisions Log (fold into master brief once this plan is executed)

| Item | Resolution |
|---|---|
| BYOK header name | `X-Gemini-Api-Key` (both MCS's own inbound API and the outbound Gemini call use their own respective header names — MCS inbound is `X-Gemini-Api-Key`, outbound to Google is `x-goog-api-key` per Gemini's own contract) |
| Effort/thinking mapping | Model-family-aware lookup: 2.5-series -> `thinking_budget` (int, 0=off, -1=dynamic); 3.x-series -> `thinking_level` (enum, set varies Flash vs Pro, never both params together, cannot disable on 3/3.1 Pro). See Milestone 3's context packet for the full table. |
| Requirements.md gap | Original `mcs-v2-requirements.md` was not available during this planning pass. `MCS-BACKEND-CONSOLIDATED-SPEC.md` is being used as the authoritative behavior reference in its place for this build cycle. If the original doc surfaces later, diff it against the consolidated spec before trusting either blindly — the consolidated spec claims to supersede it but was written by a prior planning pass, not verified against it line-by-line in this session. |

# Appendix B — What This Plan Deliberately Does Not Cover (Phase 2, do not build without explicit request)

Effort/verbosity dial normalization via LiteLLM, planner-executor/TaskSpec generation
as a *runtime MCS feature* (vs. our own build process), multi-model consultation (MoA),
ReAct/Reflexion loops, loop governance/cost caps, semantic/vector search over Nodes,
OpenAI/Anthropic/OpenRouter/custom provider adapters, branch merging, multi-user/auth,
token streaming, import/export, full Node version history.
