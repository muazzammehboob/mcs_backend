# AGENT LOG: Backend Updates

## Eagle View & Graph API (Wave 3)
- **What was built:** Audited and validated the `/graph/project/{id}` endpoint and edge semantics (`sequence`, `fork`, `summary_cutoff`). Fixed an edge-case N+1 query issue in `app/api/graph.py`.
- **Why:** Required to cleanly serve the frontend's Eagle View without causing SQL warnings on empty IN clauses. 
- **Scope Cuts:** No changes to backend schema for manual layout positions (drag-to-reposition) were heavily optimized since the feature was deferred to v1 backlog.
- **Deviations:** The frontend adapter natively conforms to the backend's explicit edge types, ensuring the backend logic remains pure to the data model without needing UI-specific layout overrides.
