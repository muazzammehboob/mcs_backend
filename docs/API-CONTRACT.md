# MCS Backend API Contract

This document provides a fully self-contained specification of the entire API exposed by the MCS backend. It is designed for frontend developers who do not have access to the backend Python code.

## Global Configuration & Requirements

### Authentication / BYOK (Bring Your Own Key)
Every endpoint that triggers an external LLM call or interacts with the Gemini API requires the caller to provide their raw API key via an HTTP Header:
- **Header Name**: `X-Gemini-Api-Key`
- **Value**: The raw string of the API key (e.g., `AIzaSy...`)

If this header is missing on an LLM-bound route, the server will immediately return `401 Unauthorized`. 
*Note: The key is never persisted or logged by the backend.*

### Streaming Behavior (`/chat/completion`)
The `/chat/completion` endpoint is **strictly non-streaming**. It returns a single standard JSON object upon completion. The frontend should indicate a loading state while awaiting the response. Streaming (SSE or chunked) is not implemented in this version of the backend.

### Enums & Exact String Values
When supplying or evaluating categorical fields, expect and use these exact string values:

- **Branch Type**: `"standard"` | `"temporary"`
- **Node Type**: `"manual"` | `"summary"`
- **Effort Levels**: `"low"` | `"medium"` | `"high"` | `"max"`
- **Graph Node Type**: `"branch"` | `"pair"` | `"node"`
- **Graph Edge Type**: `"fork"` | `"sequence"` | `"summary_cutoff"` | `"contains"`
- **Summary Actions**: `"replace"` | `"disconnect"` | `"delete"`

---

## Health & System

### `GET /health`
**Status Codes**: 
- `200 OK`

**Response Example**:
```json
{
  "status": "ok"
}
```

---

## Models Catalog

### `GET /models`
Live-fetches supported models directly from the Gemini API.

**Headers Required**: `X-Gemini-Api-Key`

**Status Codes**: 
- `200 OK`
- `401 Unauthorized`
- `502 Bad Gateway` (Provider error)

**Response Example**:
```json
{
  "models": [
    {
      "id": "gemini-2.5-flash",
      "name": "Gemini 2.5 Flash",
      "modalities": ["TEXT", "IMAGE", "AUDIO"]
    }
  ]
}
```

---

## Chat

### `POST /chat/completion`
Sends a chat completion request to Gemini.

**Headers Required**: `X-Gemini-Api-Key`

**Request Model**: `ChatRequest`
- `system` (string, optional, default `""`)
- `messages` (Array of objects, required)
  - `role` (string: `"user"` | `"assistant"`)
  - `content` (string)
- `model` (string, optional, default `"gemini-2.5-flash"`)
- `temperature` (float | null, optional)
- `top_p` (float | null, optional)
- `max_output_tokens` (int | null, optional)
- `effort` (string | null, optional) - *Must be low, medium, high, max*

**Response Model**: `ChatResponseSchema`
- `content` (string)
- `model` (string)
- `usage` (object | null)

**Status Codes**:
- `200 OK`: Success
- `400 Bad Request`: Safety block triggered. Response detail contains `safety_ratings` and `finish_reason`.
- `401 Unauthorized`
- `502 Bad Gateway`: Gemini API provider error.

**Example Request**:
```json
{
  "system": "You are a helpful assistant.",
  "messages": [
    {"role": "user", "content": "Hello"}
  ],
  "model": "gemini-2.5-pro",
  "effort": "high"
}
```

**Example Response**:
```json
{
  "content": "Hello! How can I help you?",
  "model": "gemini-2.5-pro",
  "usage": {
    "promptTokenCount": 10,
    "candidatesTokenCount": 15,
    "totalTokenCount": 25
  }
}
```

---

## Projects

### `POST /projects`
Creates a Project and auto-creates its Root Branch in one transaction.

**Request Model**: `ProjectCreate`
- `name` (string, required)
- `default_provider` (string, optional, default `"gemini"`)
- `default_model` (string, optional, default `"gemini-2.5-flash"`)
- `custom_base_url` (string | null, optional)
- `token_limit` (int | null, optional)
- `persona` (string | null, optional)
- `instructions` (string | null, optional)
- `negative_constraints` (string | null, optional)
- `safety_settings` (object | null, optional)

**Response Model**: `ProjectResponse`
- `id` (int)
- `name` (string)
- `created_at` (string/datetime)
- `default_provider` (string)
- `default_model` (string)
- `custom_base_url` (string | null)
- `token_limit` (int | null)
- `persona` (string | null)
- `instructions` (string | null)
- `negative_constraints` (string | null)
- `safety_settings` (object | null)

**Status Codes**:
- `201 Created`

**Example Request**:
```json
{
  "name": "My New Project",
  "default_model": "gemini-2.5-pro"
}
```

**Example Response**:
```json
{
  "id": 1,
  "name": "My New Project",
  "created_at": "2026-07-06T00:00:00Z",
  "default_provider": "gemini",
  "default_model": "gemini-2.5-pro",
  "custom_base_url": null,
  "token_limit": null,
  "persona": null,
  "instructions": null,
  "negative_constraints": null,
  "safety_settings": null
}
```

### `GET /projects/{project_id}`
Gets a single project by ID. Returns `ProjectResponse`. Status: `200 OK` or `404 Not Found`.

---

## Branches

### `POST /branches/{pr_pair_id}/fork`
Forks a new branch from a **completed** PRPair.

**Request Model**: `BranchForkRequest`
- `pr_pair_id` (int, required)
- `label` (string | null, optional)

**Response Model**: `BranchModel`
- `id` (int)
- `project_id` (int)
- `parent_branch_id` (int | null)
- `parent_pr_pair_id` (int | null)
- `type` (string - `"standard"` or `"temporary"`)
- `label` (string | null)
- `cached_static_token_count` (int | null)
- `linked_summary_node_id` (int | null)
- `summary_cutoff_position` (int | null)
- `created_at` (string/datetime)

**Status Codes**:
- `201 Created`
- `404 Not Found`
- `409 Conflict` (Cannot act on a pending/null response pair)

**Example Request**:
```json
{
  "pr_pair_id": 42,
  "label": "Alternative Implementation"
}
```

**Example Response**:
```json
{
  "id": 5,
  "project_id": 1,
  "parent_branch_id": 2,
  "parent_pr_pair_id": 42,
  "type": "standard",
  "label": "Alternative Implementation",
  "cached_static_token_count": null,
  "linked_summary_node_id": null,
  "summary_cutoff_position": null,
  "created_at": "2026-07-06T00:00:00Z"
}
```

### `GET /branches/{branch_id}/counts`
Return branch-count-per-pair for all pairs in a branch.

**Response Model**: `BranchCountsResponse`
- `counts` (dict[str, int]: maps `pr_pair_id` string to child branch count)

**Example Response**:
```json
{
  "counts": {
    "42": 2,
    "45": 1
  }
}
```

### `GET /branches/{branch_id}/move-to-parent-pair`
Returns the PRPair this branch was forked from.

**Response Model**: `MoveToParentPairResponse`
- `parent_pr_pair_id` (int | null)

**Example Response**:
```json
{
  "parent_pr_pair_id": 42
}
```

---

## PRPairs

### `GET /pairs/{pair_id}`
Get a single PRPair by ID.

**Response Model**: `PRPairResponse`
- `id` (int)
- `branch_id` (int)
- `prompt_text` (string)
- `response_text` (string)
- `generation_params` (object | null)
- `created_at` (string/datetime)

**Status Codes**: `200 OK`, `404 Not Found`

**Example Response**:
```json
{
  "id": 42,
  "branch_id": 2,
  "prompt_text": "Write a python script",
  "response_text": "print('hello')",
  "generation_params": {"model": "gemini-2.5-flash"},
  "created_at": "2026-07-06T00:00:00Z"
}
```

---

## Nodes (Manual & Summary)

### `POST /nodes/project/{project_id}`
Creates a new Node in a project. Enforces per-project name uniqueness and @mention cycle detection.

**Request Model**: `NodeCreate`
- `name` (string, required)
- `content` (string, required)
- `type` (string, optional, default `"manual"`)

**Response Model**: `NodeResponse`
- `id` (int)
- `project_id` (int)
- `name` (string)
- `content` (string)
- `type` (string)
- `version_counter` (int)
- `created_at` (string/datetime)

**Status Codes**: 
- `201 Created`
- `409 Conflict` (Name conflict)
- `400 Bad Request` (@mention cycle detected, returns `detail.cycle` array)

**Example Request**:
```json
{
  "name": "DesignDoc",
  "content": "The architecture is modular.",
  "type": "manual"
}
```

**Example Response**:
```json
{
  "id": 10,
  "project_id": 1,
  "name": "DesignDoc",
  "content": "The architecture is modular.",
  "type": "manual",
  "version_counter": 1,
  "created_at": "2026-07-06T00:00:00Z"
}
```

### `PUT /nodes/{node_id}`
Updates a Node. Rejects @mention cycles.

**Request Model**: `NodeUpdate`
- `name` (string | null, optional)
- `content` (string | null, optional)

**Response**: Returns `NodeResponse`.

### `GET /nodes/project/{project_id}`
Lists all nodes in a project. Returns Array of `NodeResponse`.

### `GET /nodes/{node_id}`
Gets a single node. Returns `NodeResponse`.

### `DELETE /nodes/{node_id}`
Deletes a node. Returns `204 No Content`.

---

## Attachments

### `POST /attachments/project/{project_id}`
Upload a file. Stored locally and optionally uploaded to Gemini File API.

**Headers Required**: `X-Gemini-Api-Key`

**Request Content-Type**: `multipart/form-data`
- `file` (Binary File data, required)

**Response Model**: `AttachmentUploadResponse`
- `attachment_id` (int)
- `file_path` (string)
- `mime_type` (string)
- `original_filename` (string)
- `size_bytes` (int)
- `gemini_file_uri` (string | null)

**Status Codes**:
- `201 Created`
- `400 Bad Request`
- `502 Bad Gateway` (Gemini API Error)

**Example Response**:
```json
{
  "attachment_id": 3,
  "file_path": "uploads/1/diagram.png",
  "mime_type": "image/png",
  "original_filename": "diagram.png",
  "size_bytes": 1048576,
  "gemini_file_uri": "https://generativelanguage.googleapis.com/v1beta/files/abc123def456"
}
```

---

## Summaries

### `POST /summaries/generate`
Generates a summary draft for a branch. Produces a draft Node (not yet linked).

**Headers Required**: `X-Gemini-Api-Key`

**Request Model**: `SummaryGenerateRequest`
- `branch_id` (int, required)
- `model` (string, optional, default `"gemini-2.5-flash"`)

**Response Model**: `SummaryDraftResponse`
- `draft_node_id` (int | null)
- `name` (string)
- `content` (string)
- `branch_id` (int)
- `pair_count` (int)

**Example Request**:
```json
{
  "branch_id": 2,
  "model": "gemini-2.5-flash"
}
```

**Example Response**:
```json
{
  "draft_node_id": 11,
  "name": "Summary-2",
  "content": "We discussed the UI layout and chose Flexbox over Grid.",
  "branch_id": 2,
  "pair_count": 5
}
```

### `POST /summaries/replace`
Applies a summary Node to a branch with a cutoff position.

**Headers Required**: `X-Gemini-Api-Key`

**Request Model**: `SummaryReplaceRequest`
- `summary_node_id` (int, required)
- `cutoff_position` (int, required)

**Response Model**: `SummaryActionResponse`
- `branch_id` (int)
- `action` (string - `"replace"`)
- `linked_summary_node_id` (int | null)
- `summary_cutoff_position` (int | null)
- `token_count` (int | null)

**Example Request**:
```json
{
  "summary_node_id": 11,
  "cutoff_position": 5
}
```

**Example Response**:
```json
{
  "branch_id": 2,
  "action": "replace",
  "linked_summary_node_id": 11,
  "summary_cutoff_position": 5,
  "token_count": 250
}
```

### `POST /summaries/{branch_id}/disconnect`
Disconnect the active summary from a branch (keeps the Node).

**Headers Required**: `X-Gemini-Api-Key`

**Response**: `SummaryActionResponse` (action: `"disconnect"`, linked_summary_node_id: null).

### `POST /summaries/{branch_id}/delete`
Delete the active summary from a branch entirely (deletes the Node).

**Response**: `SummaryActionResponse` (action: `"delete"`, linked_summary_node_id: null).

---

## Graph (Eagle View)

### `GET /graph/project/{project_id}`
Return the full graph for a project: nodes, edges, and layout positions.

**Response Model**: `GraphResponse`
- `nodes` (list of `GraphNode`)
  - `id` (int)
  - `type` (string: `"branch"` | `"pair"` | `"node"`)
  - `label` (string | null)
  - `name` (string | null)
  - `prompt_text` (string | null)
  - `content` (string | null)
  - `node_type` (string | null: `"manual"` | `"summary"`)
- `edges` (list of `GraphEdge`)
  - `source_id` (int)
  - `source_type` (string)
  - `target_id` (int)
  - `target_type` (string)
  - `edge_type` (string: `"fork"` | `"sequence"` | `"summary_cutoff"` | `"contains"`)
- `layout_positions` (list of `GraphLayoutResponse`)

**Example Response**:
```json
{
  "nodes": [
    {"id": 1, "type": "branch", "label": "Root", "name": null, "prompt_text": null, "content": null, "node_type": null},
    {"id": 42, "type": "pair", "label": null, "name": null, "prompt_text": "Write a script", "content": null, "node_type": null}
  ],
  "edges": [
    {"source_id": 1, "source_type": "branch", "target_id": 42, "target_type": "pair", "edge_type": "sequence"}
  ],
  "layout_positions": [
    {"id": 1, "project_id": 1, "branch_id": 1, "node_id": null, "x": 100.0, "y": 200.0, "z": null, "created_at": "2026-07-06T00:00:00Z"}
  ]
}
```

### `POST /graph/layout/project/{project_id}`
Creates or updates a cosmetic layout position.

**Request Model**: `GraphLayoutRequest`
- `branch_id` (int | null, optional)
- `node_id` (int | null, optional)
- `x` (float, required)
- `y` (float, required)
- `z` (float | null, optional)

**Response Model**: `GraphLayoutResponse`
- `id` (int)
- `project_id` (int)
- `branch_id` (int | null)
- `node_id` (int | null)
- `x` (float)
- `y` (float)
- `z` (float | null)
- `created_at` (string/datetime)

**Status Codes**: `201 Created`

**Example Request**:
```json
{
  "branch_id": 1,
  "x": 250.5,
  "y": 100.0
}
```

**Example Response**:
```json
{
  "id": 10,
  "project_id": 1,
  "branch_id": 1,
  "node_id": null,
  "x": 250.5,
  "y": 100.0,
  "z": null,
  "created_at": "2026-07-06T00:00:00Z"
}
```

### `DELETE /graph/layout/{layout_id}`
Deletes a layout position. Returns `204 No Content`.
