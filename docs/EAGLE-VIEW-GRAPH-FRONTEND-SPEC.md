# Eagle View — 2D Conversation Graph: Frontend Implementation Spec

**Audience:** Frontend Team  
**Author:** Backend Team  
**Status:** Ready for implementation  
**Backend Version this spec describes:** MCS v2 (see `BACKEND-ULTIMATE.md` and `API-CONTRACT.md` for the live API reference)

---

## 0. What This Page Is

The **Eagle View** is a dedicated page (or full-screen overlay) where the user sees the **entire conversation tree of a single project rendered as an interactive 2D graph**. Every branch, every prompt/response pair, and every node (manual and summary) in the project appears as a visual element. The user can:

- See the whole conversation topology at a glance — which threads fork from which, where summaries compress history, how branches relate.
- Click any element to navigate directly to it in the chat view.
- Drag nodes to arrange the layout as they prefer (positions are persisted by the backend).
- Zoom and pan freely across the canvas.

This is called "Eagle View" throughout the codebase and all specs. The term "3D Eagle View" in the original requirements doc (`MCS-BACKEND-CONSOLIDATED-SPEC.md §1`) was a planning-era label — the **backend currently returns 2D coordinates only** (`x`, `y` fields; `z` is present in the schema but unused). Build this as a **2D graph**. 3D is a future concern.

---

## 1. Backend Data Model — What You Are Rendering

Before touching any component, understand what the backend gives you. There are **three categories of entities** in a project, and they all appear in the graph:

### 1.1 Branches
A **Branch** is a conversation thread. Every project starts with exactly one Root Branch (no parent). All other branches are forks of an existing branch, forked from a specific Prompt/Response Pair.

Key fields relevant to the graph:
```
Branch {
  id: int
  project_id: int
  parent_branch_id: int | null     // null = Root Branch
  parent_pr_pair_id: int | null    // the exact Pair this was forked from
  type: "standard" | "temporary"
  label: string | null             // user-set name, may be null
  linked_summary_node_id: int | null  // if a Summary compresses this branch
  summary_cutoff_position: int | null // pairs before this index are "replaced" by summary
  cached_static_token_count: int | null
}
```

### 1.2 PR Pairs (Prompt/Response Pairs)
A **PR Pair** is one completed turn: a user prompt + the AI response. Pairs only exist once fully completed — there are no "pending" rows in the DB. Each pair belongs to exactly one branch.

Key fields relevant to the graph:
```
PRPair {
  id: int
  branch_id: int
  prompt_text: string   // BACKEND SENDS ONLY FIRST 100 CHARS in graph response
  response_text: string // NOT included in the graph response (too large)
  generation_params: object | null
  created_at: datetime
}
```

> **Important:** The graph API truncates `prompt_text` to 100 chars (see `app/api/graph.py` line 82). Do not rely on it for the full prompt — it's a preview label only. To show the full pair, navigate the user to the chat view or call `GET /pairs/{pair_id}`.

### 1.3 Nodes (Manual & Summary)
A **Node** is a reusable content block, either user-created (`manual`) or AI-generated (`summary`). Nodes are project-scoped, not branch-scoped. A summary node can be "linked" to a branch (compressing older pairs).

Key fields relevant to the graph:
```
Node {
  id: int
  project_id: int
  name: string
  content: string  // BACKEND SENDS ONLY FIRST 100 CHARS in graph response
  type: "manual" | "summary"
  version_counter: int
}
```

---

## 2. The Backend Graph API — Exact Contract

### 2.1 Primary Endpoint: Fetch the Whole Graph

```
GET /graph/project/{project_id}
```

**No auth header needed** (this endpoint does not call the LLM).

**Response schema:**
```typescript
interface GraphResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
  layout_positions: GraphLayoutPosition[];
}

interface GraphNode {
  id: number;
  type: "branch" | "pair" | "node";
  label: string | null;       // set for branches (user label), null for others
  name: string | null;        // set for nodes (Node.name), null for branches/pairs
  prompt_text: string | null; // set for pairs (truncated to 100 chars)
  content: string | null;     // set for nodes (truncated to 100 chars)
  node_type: string | null;   // "manual" | "summary" — only set when type === "node"
}

interface GraphEdge {
  source_id: number;
  source_type: "branch" | "pair" | "node";
  target_id: number;
  target_type: "branch" | "pair" | "node";
  edge_type: "fork" | "sequence" | "summary_cutoff" | "contains";
}

interface GraphLayoutPosition {
  id: number;
  project_id: number;
  branch_id: number | null;
  node_id: number | null;
  x: number;
  y: number;
  z: number | null;   // always null for now — ignore
  created_at: string;
}
```

### 2.2 Edge Type Semantics — Critical for Rendering

| `edge_type`     | `source_type` → `target_type` | Meaning |
|-----------------|-------------------------------|---------|
| `"sequence"`    | `branch` → `pair`            | This pair belongs to this branch, chronologically |
| `"fork"`        | `branch` → `branch`          | The target branch was forked from the source branch |
| `"summary_cutoff"` | `node` → `branch`        | This summary node compresses the history of this branch up to a cutoff position |
| `"contains"`    | (reserved, not emitted yet)   | Future: node contains another node via @mention |

> **Note:** The `"fork"` edge source is the **parent branch**, not the parent pair. To know _which pair_ caused the fork, you need to find the target branch's `parent_pr_pair_id` from the branches data. This is available in the lineage/branches API — but for the graph, a fork edge is branch-to-branch, and that's intentional. Optionally, you can render a visual indicator on the pair node from which the fork originates.

### 2.3 Layout Positions — Persistence

When the user drags a node, **persist its position** back to the backend:

```
POST /graph/layout/project/{project_id}
```
```json
{
  "branch_id": 5,    // OR
  "node_id": 10,     // one of these, not both
  "x": 350.0,
  "y": 200.0
}
```

**Important:** This endpoint **upserts** — it deletes any existing position for that `branch_id` or `node_id` first, then creates a new one. You don't need to track layout IDs for updates.

To delete a specific layout position (e.g., when resetting):
```
DELETE /graph/layout/{layout_id}
```

> **Note on PR Pair positions:** The current backend layout table only stores positions for **branches** and **nodes** — not for individual pairs. Pair positions should be **computed deterministically by the frontend** based on their parent branch's position and their chronological order within that branch (see §5 for the layout algorithm). Do not try to persist pair positions.

### 2.4 Fetching Full Content for a Node/Pair

The graph API only sends 100-char previews. When the user clicks a pair or node to inspect it:

- **Full pair:** `GET /pairs/{pair_id}` → returns full `prompt_text` and `response_text`
- **Full node:** `GET /nodes/{node_id}` → returns full `content`
- **Navigate to pair in chat:** route to the branch that owns the pair, scrolled to that pair

---

## 3. Conceptual Graph Structure — How to Think About It

```
ROOT BRANCH
  ├── Pair 1 (prompt/response)
  ├── Pair 2 (prompt/response)
  │     └── [FORK] → BRANCH A
  │                   ├── Pair A-1
  │                   ├── Pair A-2
  │                   │     └── [FORK] → BRANCH A-1
  │                   │                   └── Pair A-1-1
  │                   └── ...
  ├── Pair 3 (prompt/response)
  │     └── [FORK] → BRANCH B
  │                   ├── [SUMMARY NODE linked] → compresses Pair B-1 through B-3
  │                   └── Pair B-4 (after cutoff)
  └── ...

NODES (project-scoped, not branch-scoped):
  ├── Node "DesignDoc" (manual)
  └── Node "Summary-B" (summary, linked to Branch B)
```

Key insight: **Branches and Pairs have a strict parent-child relationship**. A branch is a container; pairs are its sequential children. Forks create new branch containers that start from a specific pair on the parent.

---

## 4. Components to Build

### 4.1 Component Hierarchy

```
<EagleViewPage>
  ├── <EagleViewToolbar>           // zoom, reset layout, back button
  ├── <GraphCanvas>                // the main drawing surface (svg or canvas)
  │     ├── <BranchLane>[]         // visual grouping lane per branch (optional, aesthetic)
  │     ├── <BranchNode>[]         // rendered branch container nodes
  │     ├── <PairNode>[]           // rendered pair nodes
  │     ├── <ContentNode>[]        // rendered manual/summary nodes
  │     ├── <EdgeRenderer>         // renders all edges/arrows
  │     └── <MiniMap>             // small overview of the full graph
  ├── <NodeDetailPanel>            // slide-in panel: full content of clicked pair/node
  └── <GraphLoadingSkeleton>       // shown while fetching
```

### 4.2 Component: `<EagleViewPage>`

**Responsibilities:**
- Owns the data fetching lifecycle (calls `GET /graph/project/{project_id}`)
- Holds the master `graphData` state: `{ nodes, edges, layoutPositions }`
- Holds `selectedNode: GraphNodeId | null` state
- Holds `transform: { x, y, scale }` state for pan/zoom
- Routes the user back to the chat when they click "Go to Chat"
- Triggers layout position saves (debounced, after drag ends)

**Props:**
```typescript
interface EagleViewPageProps {
  projectId: number;
  onNavigateToChat: (branchId: number, pairId?: number) => void;
}
```

**Data Fetching:**
```typescript
// On mount: fetch graph
const fetchGraph = async () => {
  const data = await fetch(`/graph/project/${projectId}`).then(r => r.json());
  setGraphData(data);
  setLayoutPositions(indexBy(data.layout_positions, 'branch_id', 'node_id'));
};
```

### 4.3 Component: `<GraphCanvas>`

This is the interactive SVG (or Canvas) surface. It handles:
- **Pan:** mouse drag on empty canvas background
- **Zoom:** mouse wheel / pinch
- **Node drag:** mouse drag on a specific node element (throttled position updates, save on mouseup)
- **Node click:** selects a node, opens `<NodeDetailPanel>`
- **Transform management:** maintains a CSS/SVG transform matrix

**Technology recommendation:** Use a library such as **React Flow** (`@xyflow/react`) or **D3.js** for the canvas rendering. React Flow is strongly preferred because:
- It natively handles pan/zoom/drag with no custom event math
- It has a built-in `MiniMap` component
- Node and edge types are defined as React components, fitting the component model above
- It persists nothing itself — you control what gets sent to the backend

If React Flow is used, the graph data must be transformed into React Flow's format (see §6).

**Key SVG/Canvas behaviors:**
- Minimum zoom: 10% (so users can see the whole graph)
- Maximum zoom: 200%
- Double-click on empty canvas: reset zoom to fit-all-nodes
- Ctrl+Scroll or pinch: zoom centered on cursor position

### 4.4 Component: `<BranchNode>`

Represents a Branch entity. Visual design:
- Shape: **Rounded rectangle (pill/card shape)**, wider than tall
- Background: distinct color based on branch depth (Root = prominent, depth 1 = slightly muted, depth 2 = more muted, etc.)
- Display text: branch `label` if set, otherwise `"Branch #${id}"` or `"Root"` for the root branch
- Badge: branch `type` — show a small `TEMP` badge if `type === "temporary"`
- Badge: if `linked_summary_node_id` is set, show a small summary indicator (e.g., a compressed/fold icon)
- Hover state: highlight border, show tooltip with full label + creation date
- Click: select this branch → open `<NodeDetailPanel>` showing branch info + "Go to Chat" button
- Drag: allow position dragging → on drag end, call `POST /graph/layout/project/{project_id}` with `branch_id`

**Size:** approximately 160px wide × 48px tall (adjust to fit label)

### 4.5 Component: `<PairNode>`

Represents a PR Pair (one prompt/response turn).

- Shape: **Smaller rounded rectangle**, noticeably smaller than branch nodes
- Background: a neutral card color (e.g., dark slate), no color variation by depth
- Display text: truncated `prompt_text` (already ≤100 chars from API; truncate further if needed with ellipsis at ~50 chars for the node display)
- Icon: small prompt/chat bubble icon on left
- Hover state: show tooltip with full `prompt_text` (100 chars) + creation date
- Click: select → open `<NodeDetailPanel>` with the pair's full content (load via `GET /pairs/{pair_id}`) + "Go to Branch" button
- **Not draggable** — position is computed by the layout algorithm based on its branch position (see §5)
- If this pair has forks from it (i.e., other branches have `parent_pr_pair_id === this.id`), show a small fork indicator (e.g., a branching icon badge)

**Size:** approximately 120px wide × 36px tall

### 4.6 Component: `<ContentNode>`

Represents a Node entity (manual or summary).

- Shape: **Hexagon or diamond** — visually distinct from branches and pairs
- Background: 
  - `"manual"` type: a teal/blue-green tone
  - `"summary"` type: a gold/amber tone (visually signals "this compresses history")
- Display text: `node.name` (e.g., "DesignDoc" or "Summary-2")
- Icon: document icon for manual, compress/summary icon for summary type
- Hover: tooltip with `content` preview (100 chars) + type badge
- Click: select → open `<NodeDetailPanel>` with full node content (load via `GET /nodes/{node_id}`)
- Drag: allow position dragging → on drag end, call `POST /graph/layout/project/{project_id}` with `node_id`

**Size:** approximately 120px wide × 120px tall (hexagon bounding box)

### 4.7 Component: `<EdgeRenderer>`

Renders all edges as SVG paths or bezier curves overlaid on the canvas.

| `edge_type`       | Visual Style |
|-------------------|--------------|
| `"sequence"`      | Thin solid line with small arrowhead at pair end. Color: muted gray. Represents "this pair belongs to this branch." |
| `"fork"`          | Medium solid line with arrowhead. Color: accent (e.g., blue). Represents "a new branch was created here." |
| `"summary_cutoff"` | Dashed line. Color: gold/amber. Represents "this summary node compresses this branch's history." |

Edge rendering notes:
- Use **bezier curves** (cubic or quadratic), not straight lines — straight lines create visual noise when nodes overlap
- For `"sequence"` edges from a branch to many pairs: render them as a **vertical spine** (the branch lays out its pairs vertically below/beside it), so the sequence edges become very short connector lines, not long arcs
- `"fork"` edges connect the parent branch node to the child branch node — route these as graceful arcs around other nodes
- Arrowheads: use SVG `<marker>` elements

### 4.8 Component: `<NodeDetailPanel>`

A slide-in side panel (or modal drawer) that appears when any node is selected.

**Content based on selected node type:**

**If Branch selected:**
```
[Branch Label or "Root Branch"]
Type: standard | temporary
Created: [date]
Token cache: [cached_static_token_count] tokens | N/A
Summary: [linked summary name] | None

[Button: "Open in Chat"]   → onNavigateToChat(branchId)
[Button: "Close"]
```

**If PR Pair selected:**
```
[Loading state while fetching full pair via GET /pairs/{pair_id}]

[User Prompt]
────────────────────────────
[full prompt_text]

[AI Response]
────────────────────────────
[full response_text]

Model: [generation_params.model]
Created: [date]

[Button: "Go to Branch"]   → onNavigateToChat(pair.branch_id, pair.id)
[Button: "Close"]
```

**If Node (manual/summary) selected:**
```
[node.name]
Type: Manual | Summary   [badge]
Version: [version_counter]
Created: [date]

[Content]
────────────────────────────
[full content via GET /nodes/{node_id}]

[Button: "Close"]
```

### 4.9 Component: `<EagleViewToolbar>`

Fixed toolbar at the top of the page:
- **Back button** — returns to the project's chat view
- **Fit View button** — resets pan/zoom to fit all nodes in viewport (`fit-to-view` behavior, common in React Flow)
- **Zoom controls** — `+` / `-` buttons (accessibility)
- **Project name** — display-only label
- **Node count badge** — "X branches, Y pairs, Z nodes" (count from `graphData.nodes`)

### 4.10 Component: `<MiniMap>`

A small (200×150px) overview map in the bottom-right corner:
- Shows all nodes as colored dots (branch = branch color, pair = gray dot, node = teal/gold dot)
- Highlights the current viewport rectangle
- Clicking on the minimap pans the main canvas to that region
- React Flow provides this as a built-in `<MiniMap>` component if you use React Flow

---

## 5. Layout Algorithm — Computing Node Positions

When the user opens Eagle View for the first time (or when no saved positions exist for an entity), positions must be computed automatically. This is the **default auto-layout**.

### 5.1 Core Layout Principle: Hierarchical Tree Layout

The branch tree forms a **directed acyclic graph (DAG)** rooted at the Root Branch. Use a **hierarchical top-down tree layout** for branches:

1. The **Root Branch** is placed at the canvas center-top (e.g., `x: canvasWidth/2, y: 100`)
2. Each child branch is placed below and offset horizontally from its parent
3. Branch depth determines the Y coordinate: `y = depth * BRANCH_VERTICAL_SPACING` (e.g., 250px per level)
4. Horizontal position is computed to avoid overlap: use a standard tree layout algorithm (e.g., Reingold-Tilford, or the simpler "assign horizontal indices to leaves, then center parents over their children")

### 5.2 Pair Layout Within a Branch

Pairs inside a branch are laid out **vertically as a column** beside (or below) the branch node:

```
[Branch Node] ──┐
                │ (sequence edge)
            [Pair 1]
                │
            [Pair 2]   ← from this pair, a fork edge goes to Child Branch
                │
            [Pair 3]
```

Algorithm:
- Branch node is the anchor
- Each pair is placed at: `x = branch.x + PAIR_OFFSET_X`, `y = branch.y + (index * PAIR_VERTICAL_SPACING)`
  - Recommended: `PAIR_OFFSET_X = 180px` (to the right of branch), `PAIR_VERTICAL_SPACING = 55px`
- Pairs are **not user-repositionable** (they have no layout record in the backend) — their position is always derived from the branch position

> If the branch has a `summary_cutoff_position`, visually dim (reduce opacity) the pairs before the cutoff index and render the linked summary node overlapping/adjacent to indicate compression.

### 5.3 Content Node Layout (Manual and Summary Nodes)

Content nodes (Nodes entity) are placed separately from the branch tree:
- **Summary nodes:** Place close to the branch they're linked to (if `linked_summary_node_id` is set on a branch, the summary node should be nearby — use `branch.x - 200, branch.y` or similar)
- **Manual nodes:** Place in a cluster to the far right or left of the canvas, since they're not structurally connected to a specific branch
- If no saved layout position exists, auto-place using the above heuristics

### 5.4 Layout Algorithm Execution Order

```
1. Build branch tree (from edges where edge_type === "fork")
2. Run tree layout algorithm on branches only → assign branch x/y
3. Override with saved layout_positions where available (user-dragged positions win)
4. For each branch: compute pair x/y from branch x/y + index
5. For each node: use saved position if available, else compute from linked branch or cluster fallback
6. Return { branchPositions, pairPositions, nodePositions } as a flat map id→{x,y}
```

### 5.5 Fit-to-Viewport

After initial layout, auto-fit: compute the bounding box of all nodes, then set the canvas transform so everything is visible with some padding (e.g., 50px margin). React Flow has `fitView()` for this.

---

## 6. Transforming API Data to React Flow Format (if using React Flow)

If you choose React Flow, the transformation from the backend's `GraphResponse` to React Flow's format looks like this:

```typescript
import { type Node as RFNode, type Edge as RFEdge } from '@xyflow/react';

function transformToReactFlow(
  graphData: GraphResponse,
  computedPositions: Map<string, {x: number, y: number}>
): { nodes: RFNode[], edges: RFEdge[] } {
  const nodes: RFNode[] = graphData.nodes.map(gn => ({
    id: `${gn.type}-${gn.id}`,      // unique: "branch-1", "pair-42", "node-10"
    type: gn.type,                   // maps to custom node types registered with React Flow
    position: computedPositions.get(`${gn.type}-${gn.id}`) ?? { x: 0, y: 0 },
    data: gn,                        // pass full GraphNode as data
    draggable: gn.type !== 'pair',   // pairs are not user-draggable
  }));

  const edges: RFEdge[] = graphData.edges.map((ge, i) => ({
    id: `edge-${i}`,
    source: `${ge.source_type}-${ge.source_id}`,
    target: `${ge.target_type}-${ge.target_id}`,
    type: ge.edge_type,              // or map to React Flow built-in types
    data: { edge_type: ge.edge_type },
    animated: ge.edge_type === 'fork',  // visual emphasis on forks
  }));

  return { nodes, edges };
}
```

Register custom node types:
```typescript
const nodeTypes = {
  branch: BranchNode,
  pair: PairNode,
  node: ContentNode,
};

const edgeTypes = {
  sequence: SequenceEdge,
  fork: ForkEdge,
  summary_cutoff: SummaryCutoffEdge,
};
```

---

## 7. State Management for the Graph Page

The graph page has enough state complexity to warrant its own isolated state slice. Recommended structure:

```typescript
interface EagleViewState {
  // Server data
  graphData: GraphResponse | null;
  isLoading: boolean;
  error: string | null;

  // Computed layout (derived from graphData + layout_positions)
  computedPositions: Map<string, {x: number, y: number}>;

  // UI state
  selectedNodeId: string | null;   // e.g. "pair-42"
  detailPanelOpen: boolean;
  detailContent: PairDetail | NodeDetail | BranchDetail | null;
  isDetailLoading: boolean;

  // Canvas transform
  viewport: { x: number, y: number, zoom: number };

  // Pending saves (positions being debounced)
  pendingPositionSaves: Map<string, {x: number, y: number}>;
}
```

Keep this state **local to the EagleView page** — it doesn't need to be in global state. If you use Zustand, create a scoped store; if you use React's `useReducer`, that's fine too.

---

## 8. Interaction Flows — Step-by-Step

### 8.1 Opening Eagle View

```
1. User clicks "Eagle View" button in project header
2. Route to /projects/{projectId}/graph (or open full-screen overlay)
3. EagleViewPage mounts → show <GraphLoadingSkeleton>
4. Call GET /graph/project/{projectId}
5. On success: run layout algorithm (§5), transform to React Flow format (§6)
6. Render the graph, auto-fit viewport
7. Hide skeleton, show graph
```

### 8.2 Clicking a Pair Node

```
1. User clicks a <PairNode>
2. setSelectedNodeId("pair-{id}")
3. Open <NodeDetailPanel> in loading state
4. Call GET /pairs/{pair_id}
5. On success: populate panel with full prompt + response
6. User reads content; panel shows "Go to Branch" button
7. User clicks "Go to Branch" → onNavigateToChat(pair.branch_id, pair.id)
8. Close Eagle View, navigate to chat view, scroll to that pair
```

### 8.3 Clicking a Branch Node

```
1. User clicks a <BranchNode>
2. setSelectedNodeId("branch-{id}")
3. Open <NodeDetailPanel> with branch info (no async call needed — data is in graphData)
4. User clicks "Open in Chat" → onNavigateToChat(branchId)
```

### 8.4 Clicking a Content Node

```
1. User clicks a <ContentNode>
2. setSelectedNodeId("node-{id}")
3. Open <NodeDetailPanel> in loading state
4. Call GET /nodes/{node_id}
5. On success: populate panel with full content
6. Close when done (no navigation action — nodes aren't branch-specific)
```

### 8.5 Dragging a Node (Branch or Content Node)

```
1. User starts dragging a <BranchNode> or <ContentNode>
2. React Flow updates position in real-time (smooth drag)
3. On drag end: capture final {x, y}
4. Add to pendingPositionSaves with a 500ms debounce
5. After debounce: call POST /graph/layout/project/{projectId}
   with { branch_id: X, x: ..., y: ... } or { node_id: X, x: ..., y: ... }
6. On success: update layoutPositions in local state
7. On error: show a brief toast ("Could not save position"), revert to last known position
```

### 8.6 Resetting Layout

```
1. User clicks "Reset Layout" in toolbar (optional feature)
2. Clear all saved positions? (optional: call DELETE for each layout_id)
3. Re-run auto-layout algorithm from scratch
4. Update computedPositions in state
```

---

## 9. Visual Design Guidance

### 9.1 Color System

| Entity | Node Color | Suggested Hex |
|--------|------------|---------------|
| Root Branch | Deep indigo / primary accent | `#6366f1` (indigo-500) |
| Standard Branch | Medium blue/slate | `#3b82f6` (blue-500), dimming with depth |
| Temporary Branch | Muted orange/amber | `#f59e0b` (amber-500) |
| PR Pair | Dark slate card | `#1e293b` (slate-800) with border |
| Manual Node | Teal/cyan | `#0d9488` (teal-600) |
| Summary Node | Gold/amber | `#d97706` (amber-600) |
| Canvas background | Very dark | `#0f172a` (slate-950) or `#111827` (gray-900) |
| Sequence edge | Light gray | `#64748b` (slate-500), 1px stroke |
| Fork edge | Blue accent | `#60a5fa` (blue-400), 2px stroke |
| Summary cutoff edge | Amber dashed | `#fbbf24` (amber-400), 1.5px dashed |

### 9.2 Typography

- Branch labels: 13px, medium weight, white
- Pair prompt preview: 11px, light weight, slate-300
- Node name: 12px, semibold, white
- Tooltip text: 12px, regular, white on dark background

### 9.3 Animations

- Graph entrance: fade-in + slight scale-up (300ms ease-out) on mount
- Node selection: glow ring animation on selected node (box-shadow pulse)
- Panel open: slide-in from right (250ms ease-out)
- Edge animation on fork edges: use React Flow's `animated: true` for a flowing dash animation

---

## 10. API Error Handling

| Scenario | Behavior |
|----------|----------|
| `GET /graph/project/{id}` → 404 | Show "Project not found" full-page error with back button |
| `GET /graph/project/{id}` → 500/network | Show retry button in the center of canvas |
| `GET /pairs/{id}` fails | Show error message inside detail panel, keep panel open |
| `GET /nodes/{id}` fails | Show error message inside detail panel |
| `POST /graph/layout` fails | Silent toast: "Position not saved." Don't revert visible position |
| `DELETE /graph/layout/{id}` fails | Silent toast only |

---

## 11. Performance Considerations

- **Do not re-fetch the graph on every navigation** — fetch once on mount, cache in component state. The graph data only changes when conversations branch (which the user is doing in the chat view, not in Eagle View). Add a "Refresh" button for the user to manually trigger a re-fetch.
- **Virtualize pair nodes** if a branch has many pairs. Projects at the stated scale (tens of branches) will have manageable node counts, but for future-proofing, React Flow handles virtualization automatically for nodes out of the viewport.
- **Debounce position saves** — 500ms debounce after drag ends. Never save on every drag tick.
- **Lazy-load detail content** — don't pre-fetch pair/node full content on mount. Only fetch when the panel opens.

---

## 12. Routing & Navigation Integration

### 12.1 Route for Eagle View

Recommended route: `/projects/:projectId/graph`  
Or as a full-screen overlay toggled from the project header.

### 12.2 Navigating Back to Chat

When the user clicks "Open in Chat" or "Go to Branch":
```typescript
// Navigate to branch, optionally scroll to a specific pair
onNavigateToChat(branchId: number, pairId?: number)
```

The chat view must support accepting a `pairId` in the URL params or state to know which pair to highlight/scroll to. This is a contract between the Eagle View page and the chat view that the frontend team must define. Suggested: add a `?scrollToPair={pairId}` query param on the chat route.

### 12.3 Deep-Linking

Optionally support: `/projects/:projectId/graph?selected=pair-42` — on mount, pre-select and open the detail panel for that node. This lets other parts of the app link directly to a specific node in the graph.

---

## 13. Summary of All API Calls Made by Eagle View

| Action | HTTP Call | Auth Header Needed? |
|--------|-----------|---------------------|
| Load graph | `GET /graph/project/{id}` | ❌ No |
| Load full pair detail | `GET /pairs/{pair_id}` | ❌ No |
| Load full node detail | `GET /nodes/{node_id}` | ❌ No |
| Save branch position | `POST /graph/layout/project/{id}` with `branch_id` | ❌ No |
| Save node position | `POST /graph/layout/project/{id}` with `node_id` | ❌ No |
| Delete layout position | `DELETE /graph/layout/{layout_id}` | ❌ No |

No LLM calls are made from Eagle View. The `X-Gemini-Api-Key` header is **not required** on any of these endpoints.

---

## 14. Known Backend Issues Relevant to This Page

From `BACKEND-ULTIMATE.md §7`:

1. **Eagle View API `NameError`:** The test suite currently shows 3 failures in `test_graph.py` with `NameError: name 'projects_get_db' is not defined`. This is a backend bug in the test dependency injection — the **production endpoint itself works**; the issue is isolated to the test harness. You can test the endpoint manually via `GET /graph/project/1` and it will return correctly.

2. **Cascade Deletion:** When a branch is deleted in the chat view, its child branches may not cascade-delete properly in the current backend build. If Eagle View fetches graph data after such a deletion, there may be orphaned branch nodes. The backend team is fixing this; in the meantime, a "Refresh" button on Eagle View will re-fetch and show current state.

---

## 15. Quick Reference: Backend Field Mapping

This table maps what the backend sends in `GET /graph/project/{id}` to what you display:

| Backend `GraphNode.type` | Display Component | Primary Label | Secondary Info |
|--------------------------|-------------------|---------------|----------------|
| `"branch"` | `<BranchNode>` | `label ?? "Branch #${id}"` | `type` badge, summary indicator |
| `"pair"` | `<PairNode>` | `prompt_text` (≤100 chars) | creation date (from full fetch) |
| `"node"` | `<ContentNode>` | `name` | `node_type` (manual/summary) |

---

*End of Eagle View Frontend Implementation Spec.*  
*Questions? Check `API-CONTRACT.md` for exact endpoint signatures and `BACKEND-ULTIMATE.md` for architecture context.*
