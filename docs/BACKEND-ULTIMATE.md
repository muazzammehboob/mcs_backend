# MCS v2 Backend Ultimate Truth

## 1. Overview
The MCS v2 (Multidimensional Conversation System) backend is a stateful, local-first API layer built with FastAPI, SQLAlchemy, and SQLite. It provides robust graph-like conversation management (branches, prompt-response pairs, summary nodes) and routes LLM requests to either Gemini or Claude providers using a strict "Bring Your Own Key" (BYOK) architecture.

## 2. Architecture Summary
- **`app/api/`**: Contains the FastAPI route definitions, handling HTTP requests, response serialization, and dependency injection (such as DB sessions and BYOK headers).
- **`app/db/`**: Defines the SQLAlchemy ORM models (`models.py`) mapping the application state to the SQLite database.
- **`app/domain/`**: The core business logic layer. It contains pure domain services (e.g., `lineage.py`, `nodes.py`, `summaries.py`, `tokens.py`) that operate independently of FastAPI or SQLAlchemy, managing algorithms for history reconstruction, cycle detection, and token caching.
- **`app/providers/`**: The multi-provider routing architecture. Inheriting from a base `LLMProvider`, it contains hand-rolled httpx clients for Gemini (`gemini_provider.py`) and Claude (`claude_provider.py`), translating generic system messages to proprietary external API formats.
- **`app/schemas/`**: Pydantic models defining the strict request and response contracts for all API endpoints.

## 3. Complete Endpoint Reference
### Branches (`/branches`)
- **`POST /{pr_pair_id}/fork`**: Forks a conversation from a completed PRPair. Returns 409 if attempted on a pending/null response.
- **`GET /{branch_id}/counts`**: Returns aggregate statistics for a branch.
- **`GET /{branch_id}/move-to-parent-pair`**: Resolves the parent pair for navigation.
- **`PUT /{branch_id}`**: Updates a branch (e.g., its label).
- **`DELETE /{branch_id}`**: Deletes a branch.
- **`POST /{branch_id}/messages`**: Submits a prompt to an LLM. Streams `text/event-stream` yielding token, usage, done, or error events. **Requires BYOK API Key Header.**

**Explicit Callout: `GET /branches/{branch_id}/lineage`**
- Assembles the linear history for a branch up to its fork point.
- **Historic 500 Error:** Previously, this endpoint threw an `AmbiguousForeignKeysError` because `branches` and `pr_pairs` have mutual foreign keys. This was definitively fixed in Phase 6 by specifying the `onclause` explicit join (`PRPairModel.branch_id == BranchModel.id`).
- **Current Error Behavior:** 
  - If the branch or project is missing, it returns `404 Not Found`. 
  - If the static token count needs to be generated via the LLM API but fails (e.g., network error, invalid key), it **silently catches the exception** and falls back to a character-based heuristic (`total_chars // 4`) without failing the request.

### Nodes (`/nodes`)
- **`POST /project/{project_id}`**: Creates a node. Returns 400 for `@mention` cycles, 409 for name conflicts.
- **`PUT /{node_id}`**: Updates a node.
- **`GET /project/{project_id}`**: Lists all nodes.
- **`GET /{node_id}`**: Retrieves a node.
- **`DELETE /{node_id}`**: Deletes a node.

### Pairs (`/pairs`)
- **`GET /{pair_id}`**: Retrieves a specific prompt-response pair.

### Projects (`/projects`)
- **`POST /`**: Creates a new project and bootstraps a root standard branch.
- **`GET /`**: Lists all projects.
- **`GET /{project_id}`**: Retrieves project details.
- **`GET /{project_id}/branches`**: Lists all branches in a project.
- **`PUT /{project_id}`**: Updates a project.
- **`DELETE /{project_id}`**: Deletes a project.

### Attachments (`/attachments`)
- **`POST /project/{project_id}`**: Uploads a file, stores metadata, and interacts with the provider.

### Summaries (`/summaries`)
- **`POST /generate`**: Generates a summary draft node (fails on temporary branches).
- **`POST /replace`**: Applies a summary node to a branch at a cutoff point.
- **`POST /{branch_id}/disconnect`**: Disconnects a summary from a branch.
- **`POST /{branch_id}/delete`**: Deletes a summary from a branch.

### Graph (`/graph`)
- **`GET /project/{project_id}`**: Returns the Eagle View graph structure (nodes, edges, layouts).
- **`POST /layout/project/{project_id}`**: Creates layout positions.
- **`DELETE /layout/{layout_id}`**: Removes layout coordinates.

### Global Settings (`/settings`) & Models (`/models`)
- **`GET /global` & `PUT /global`**: Manages singleton settings.
- **`GET /`**: Lists supported models.

### Health (`/health`)
- **`GET /health`**: Returns `{ "status": "ok" }`.

## 4. Data Model
The system uses 7 SQLAlchemy tables synced to `migrations/versions/0001_initial.py`:
- **`GlobalSettings`**: Singleton table for fallback persona/instructions.
- **`Project`**: Root table holding overrides.
- **`Branch`**: Represents a thread. Inherits from `parent_branch_id` and `parent_pr_pair_id` (fork point). Includes `type` ('standard' or 'temporary'), and summary links.
- **`PRPair`**: A completed Prompt/Response turn tied to a `branch_id`. Uncompleted turns are not stored.
- **`Node`**: Reusable text blocks. `type` is 'manual' or 'summary'. 
- **`Attachment`**: File attachments bound to a `pair_id`.
- **`GraphLayoutPosition`**: 3D coordinates for Eagle View visual layouts.

**Relationships**: Lineage is computed by traversing `parent_branch_id` and slicing pairs at `parent_pr_pair_id`. Sibling pairs added after the fork point are excluded. Temporary branches exclude their own pending pairs from lineage to avoid cyclic generation loops.

**Migration State**: The SQLAlchemy models in `app/db/models.py` **exactly match** `0001_initial.py`. The database is fully in sync. Migrations use deferred batch alter tables to handle circular dependencies (e.g., branch to pairs and nodes).

## 5. Persistence Architecture Decision
**Explicit Statement:** The backend is currently a **full stateful persistence layer** using SQLite and Alembic. It is **NOT** a "stateless proxy." 
Any documentation or previous agent inferences claiming the backend was built as a stateless proxy with persistence bolted on later are **factually incorrect**. The codebase natively handles full database CRUD operations, parent-child branch tracking, and cascade deletes, which were demanded by the original spec.

## 6. Provider/Routing Architecture
- **Routing:** Handled at the endpoint level. If `"claude"` is in the requested model string, it uses `ClaudeProvider`; otherwise, it defaults to `GeminiProvider`.
- **BYOK Flow:** Enforces an `X-Gemini-Api-Key` HTTP header. The key is never persisted. Both Gemini and Claude APIs dynamically use this exact same header for key transport.
- **Capability Table:** `capability_table.py` maps models (via regex-like strings) to supported modalities.
- **Thinking Map:** Maps effort dials ("low", "medium", "high", "max") to provider params. Gemini 2.5 uses integer `thinkingBudget`, while 3.x uses string `thinkingLevel` (e.g., "MEDIUM"). An explicit check prevents both from being sent simultaneously.
- **Exceptions & Streaming Fallback:** During `POST /branches/{branch_id}/messages` streaming, if the primary provider instantly fails (excluding safety blocks), the backend explicitly abandons the original model choice, switches to `"gemini-2.5-flash"`, and retries the stream transparently. Safety blocks raise `GeminiSafetyBlockError` and pass details back to the UI.

## 7. Known Issues / Unresolved Items
All documented blockers in `ISSUE-REGISTRY.md` and `design (4).md` are resolved in `FIX-LOG.md`. However, based on the **latest test suite execution** (73 tests, 4 failures), there are current code-level issues:
- **Cascade Deletion Failure:** `test_branch_delete_cascades_to_descendants` in `test_cascade_deletes.py` fails. When a middle branch is deleted, its descendants are not being automatically removed from the database as expected.
- **Eagle View API `NameError`:** `test_graph.py` has 3 failures crashing with `NameError: name 'projects_get_db' is not defined`. This is likely a FastAPI dependency override scoping/import issue.

## 8. What the Frontend Needs to Know
- **Auth Contract:** You MUST send the `X-Gemini-Api-Key` header with your LLM API key on any request that interacts with the LLM (like `POST /branches/{branch_id}/messages` and `POST /summaries/generate`). Without it, you get a 401. This header carries the key for *both* Claude and Gemini.
- **Streaming Contract:** The `/branches/{branch_id}/messages` endpoint returns `text/event-stream`. You must parse the stream yielding JSON events: `{"type": "token", "text": "..."}`, `{"type": "usage", "metrics": {...}}`, `{"type": "done"}`, or `{"type": "error", "message": "..."}`.
- **Forking Contract:** You can only fork from a *completed* `PRPair`. Pending turns are not stored in the DB, and trying to fork from an incomplete pair returns 409 Conflict.
- **Temporary Branch Contract:** Temporary branches are stateless for their own turns (they don't store prompt/response pairs inside themselves for lineage). You cannot generate a summary on a temporary branch (returns 400).
- **Lineage Payload:** When calling `GET /branches/{branch_id}/lineage`, expect an array of pairs, summary cutoff metadata, and a static token count. If the LLM fails to count tokens, the backend silently provides a character-based heuristic count rather than throwing a 500 error.
- **Summary Replacement:** To replace lineage with a summary, call `POST /summaries/replace` providing `summary_node_id`, `branch_id`, and `cutoff_position` (an integer index).
