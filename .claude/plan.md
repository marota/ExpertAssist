# Plan: Log User Interactions Per Session (Replay-Ready)

## Goal

Track every user interaction during a session as a timestamped, **replay-ready** event log. The log must contain enough data for an automated agent (e.g. browser automation) to deterministically reproduce the exact same session — same clicks, same selections, same analysis runs — without human input.

The log is saved as a dedicated `interaction_log.json` file alongside `session.json` when saving results.

---

## Design Principles for Replay

1. **Self-contained events**: Each event carries all input parameters needed to replay the action, not just a label. An agent reading the log should never need to infer missing data.
2. **Deterministic ordering**: Events are strictly ordered by timestamp. Async completions are logged as separate events with a `correlation_id` linking them to their trigger.
3. **Wait-for-completion semantics**: Events that trigger async work (API calls, streaming) log both a `*_started` and `*_completed` event. A replay agent must wait for the completion event's conditions (API response received) before proceeding to the next action.
4. **UI-level actions**: Log what the user did (clicked, selected, toggled), not internal React state changes. Each event maps to a specific UI gesture that a browser automation agent can reproduce.
5. **Sequence numbering**: Each event gets a monotonically increasing `seq` number for unambiguous ordering, even if timestamps collide.

---

## 1. Data Model

### `frontend/src/types.ts` — New types

```typescript
export type InteractionType =
  // === Configuration & Study Loading ===
  | 'config_loaded'                // User clicked "Load Study" → config sent to backend
  | 'settings_opened'              // User opened settings modal
  | 'settings_tab_changed'         // User switched tab within settings modal
  | 'settings_applied'             // User clicked Apply in settings (all params captured)
  | 'settings_cancelled'           // User cancelled/closed settings without applying
  | 'path_picked'                  // User used native file/dir picker
  // === Contingency Selection ===
  | 'contingency_selected'         // User selected a branch from dropdown
  | 'contingency_confirmed'        // User confirmed branch change (after dialog)
  // === Two-Step Analysis ===
  | 'analysis_step1_started'       // Step 1 launched (detect overloads)
  | 'analysis_step1_completed'     // Step 1 finished (overloads detected)
  | 'overload_toggled'             // User toggled an overload checkbox
  | 'analysis_step2_started'       // Step 2 launched (resolve overloads)
  | 'analysis_step2_completed'     // Step 2 finished (actions received)
  | 'prioritized_actions_displayed'// User clicked "Display Prioritized Actions"
  // === Action Interactions ===
  | 'action_selected'              // User clicked an action card
  | 'action_deselected'            // User clicked away / deselected action
  | 'action_favorited'             // User starred an action
  | 'action_unfavorited'           // User un-starred an action
  | 'action_rejected'              // User rejected an action
  | 'action_unrejected'            // User un-rejected an action
  | 'manual_action_simulated'      // User simulated action via manual search
  // === Combined Actions ===
  | 'combine_modal_opened'         // User opened Combine Actions modal
  | 'combine_modal_closed'         // User closed Combine Actions modal
  | 'combine_pair_toggled'         // User toggled an action in pair selection
  | 'combine_pair_estimated'       // Superposition estimation computed
  | 'combine_pair_simulated'       // Full simulation of combined pair
  // === Visualization ===
  | 'diagram_tab_changed'          // User switched tab (n / n-1 / action / overflow)
  | 'view_mode_changed'            // User switched Flows/Impacts mode
  | 'voltage_range_changed'        // User adjusted voltage filter slider
  | 'asset_clicked'                // User clicked a line/asset badge to zoom
  | 'zoom_in'                      // User clicked zoom-in button
  | 'zoom_out'                     // User clicked zoom-out button
  | 'zoom_reset'                   // User clicked zoom reset button
  | 'inspect_query_changed'        // User typed in search/inspect box
  // === SLD Overlay ===
  | 'sld_overlay_opened'           // User double-clicked VL to open SLD
  | 'sld_overlay_tab_changed'      // User switched SLD tab (n / n-1 / action)
  | 'sld_overlay_closed'           // User closed SLD overlay
  // === Session Management ===
  | 'session_saved'                // User saved session
  | 'session_reload_modal_opened'  // User opened reload modal
  | 'session_reloaded';            // User selected a session to reload

export interface InteractionLogEntry {
  seq: number;                     // Monotonic sequence number (0-based)
  timestamp: string;               // ISO 8601
  type: InteractionType;
  details: Record<string, unknown>;// Type-specific replay payload (see §2)
  correlation_id?: string;         // Links async start/complete pairs
  duration_ms?: number;            // For *_completed events: wall-clock duration
}
```

---

## 2. Replay Contract: Required Details Per Event Type

Each event's `details` field must contain **all parameters needed to replay** the user action. Below is the exhaustive contract.

### Configuration & Study Loading

| Event | Details | Replay Action |
|-------|---------|---------------|
| `config_loaded` | `{ network_path, action_file_path, layout_path, min_line_reconnections, min_close_coupling, min_open_coupling, min_line_disconnections, min_pst, n_prioritized_actions, lines_monitoring_path, monitoring_factor, pre_existing_overload_threshold, ignore_reconnections, pypowsybl_fast_mode }` | Click "Load Study" with these config values |
| `settings_opened` | `{ tab: 'paths'\|'recommender'\|'configurations' }` | Click gear icon |
| `settings_tab_changed` | `{ from_tab, to_tab }` | Click tab in settings modal |
| `settings_applied` | `{ network_path, action_file_path, layout_path, output_folder_path, min_line_reconnections, min_close_coupling, min_open_coupling, min_line_disconnections, min_pst, n_prioritized_actions, lines_monitoring_path, monitoring_factor, pre_existing_overload_threshold, ignore_reconnections, pypowsybl_fast_mode }` | Fill all fields → click Apply |
| `settings_cancelled` | `{}` | Click Cancel / close settings |
| `path_picked` | `{ field: 'network'\|'action'\|'layout'\|'output'\|'monitoring', picker_type: 'file'\|'dir', selected_path: string }` | Click file picker → select path |

### Contingency Selection

| Event | Details | Replay Action |
|-------|---------|---------------|
| `contingency_selected` | `{ element: string }` | Select value in branch dropdown |
| `contingency_confirmed` | `{ element: string, dialog_type: 'contingency'\|'loadStudy' }` | Click OK in confirmation dialog |

### Two-Step Analysis

| Event | Details | Replay Action |
|-------|---------|---------------|
| `analysis_step1_started` | `{ element: string }` | Click "Detect Overloads" |
| `analysis_step1_completed` | `{ element, overloads_found: string[], n_overloads: string[], can_proceed: bool, dc_fallback: bool, message: string }` | *(wait point — agent waits for API response)* |
| `overload_toggled` | `{ overload: string, selected: bool }` | Click checkbox for overload |
| `analysis_step2_started` | `{ element, selected_overloads: string[], all_overloads: string[], monitor_deselected: bool }` | Click "Resolve Selected Overloads" |
| `analysis_step2_completed` | `{ n_actions: number, action_ids: string[], dc_fallback: bool, message: string, pdf_url: string\|null }` | *(wait point)* |
| `prioritized_actions_displayed` | `{ n_actions: number }` | Click "Display Prioritized Actions" button |

### Action Interactions

| Event | Details | Replay Action |
|-------|---------|---------------|
| `action_selected` | `{ action_id: string }` | Click action card |
| `action_deselected` | `{ previous_action_id: string }` | Click elsewhere / select null |
| `action_favorited` | `{ action_id: string }` | Click star icon |
| `action_unfavorited` | `{ action_id: string }` | Click star icon (toggle off) |
| `action_rejected` | `{ action_id: string }` | Click reject icon |
| `action_unrejected` | `{ action_id: string }` | Click reject icon (toggle off) |
| `manual_action_simulated` | `{ action_id: string, description: string }` | Search action → click Simulate |

### Combined Actions

| Event | Details | Replay Action |
|-------|---------|---------------|
| `combine_modal_opened` | `{}` | Click "Combine Actions" button |
| `combine_modal_closed` | `{}` | Close modal |
| `combine_pair_toggled` | `{ action_id: string, selected: bool }` | Toggle checkbox in pair selection |
| `combine_pair_estimated` | `{ action1_id, action2_id, estimated_max_rho: number, estimated_max_rho_line: string }` | *(auto after pair selected — wait point)* |
| `combine_pair_simulated` | `{ combined_id: string, action1_id, action2_id, simulated_max_rho: number\|null }` | Click "Simulate" on pair row |

### Visualization

| Event | Details | Replay Action |
|-------|---------|---------------|
| `diagram_tab_changed` | `{ from_tab: TabId, to_tab: TabId }` | Click tab button |
| `view_mode_changed` | `{ mode: 'network'\|'delta' }` | Click Flows/Impacts toggle |
| `voltage_range_changed` | `{ min_kv: number, max_kv: number }` | Drag voltage slider |
| `asset_clicked` | `{ asset_name: string, action_id: string, target_tab: 'n'\|'n-1'\|'action' }` | Click rho-line badge |
| `zoom_in` | `{}` | Click + button |
| `zoom_out` | `{}` | Click - button |
| `zoom_reset` | `{}` | Click reset button |
| `inspect_query_changed` | `{ query: string }` | Type in search box |

### SLD Overlay

| Event | Details | Replay Action |
|-------|---------|---------------|
| `sld_overlay_opened` | `{ vl_name: string, action_id: string\|null, initial_tab: 'n'\|'n-1'\|'action' }` | Double-click VL node |
| `sld_overlay_tab_changed` | `{ from_tab: SldTab, to_tab: SldTab }` | Click tab in SLD overlay |
| `sld_overlay_closed` | `{}` | Click close on SLD overlay |

### Session Management

| Event | Details | Replay Action |
|-------|---------|---------------|
| `session_saved` | `{ session_name: string, output_folder: string }` | Click "Save Results" |
| `session_reload_modal_opened` | `{ output_folder: string, available_sessions: string[] }` | Click "Reload Session" |
| `session_reloaded` | `{ session_name: string }` | Click session in list |

---

## 3. Replay Agent Contract

An automated replay agent consuming `interaction_log.json` must follow these rules:

### 3.1 Event Processing Loop

```
for each event in interaction_log (ordered by seq):
  1. Wait for app to be idle (no pending API calls, no loading spinners)
  2. Execute the UI action described by event.type + event.details
  3. If event has a correlation_id and is a *_started event:
     - Execute the action
     - Wait for the matching *_completed event's conditions to be met
     - (The completed event is informational — the agent doesn't "replay" it,
        it waits for the app to produce that state naturally)
  4. Proceed to next event
```

### 3.2 Wait Points (Async Operations)

These events trigger async API calls. The replay agent must wait for the operation to complete before proceeding:

| Trigger Event | Wait Condition |
|---------------|----------------|
| `config_loaded` | Network loaded, branches list populated |
| `analysis_step1_started` | Loading spinner gone, overload list populated |
| `analysis_step2_started` | Streaming complete, action cards visible |
| `action_selected` | Action diagram loaded (or simulation fallback complete) |
| `manual_action_simulated` | Action card appears in feed |
| `combine_pair_estimated` | Estimation values appear in modal |
| `combine_pair_simulated` | Simulation values appear in modal |
| `session_reloaded` | Full session state restored |
| `settings_applied` | Network reloaded, branches refreshed |

### 3.3 Handling `*_completed` Events

Completed events are **informational checkpoints**, not actions to replay. They serve two purposes:
1. **Verification**: The agent can compare actual app state against the logged `details` to detect divergence (e.g., different number of overloads found → data changed)
2. **Timing**: The `duration_ms` field gives realistic timing for the original session

### 3.4 Correlation IDs

Async start/complete pairs share a `correlation_id` (UUID). This allows the agent to:
- Match starts with completions
- Handle nested async operations (e.g., analysis running while diagrams load)
- Detect interrupted operations (start without matching complete = user cancelled/errored)

---

## 4. Frontend Interaction Logger Utility

### New file: `frontend/src/utils/interactionLogger.ts`

```typescript
import { v4 as uuidv4 } from 'uuid'; // or a simple counter-based ID

class InteractionLogger {
  private log: InteractionLogEntry[] = [];
  private seq = 0;

  record(type: InteractionType, details: Record<string, unknown> = {}, correlationId?: string): string {
    const id = correlationId ?? uuidv4();
    this.log.push({
      seq: this.seq++,
      timestamp: new Date().toISOString(),
      type,
      details,
      correlation_id: id,
    });
    return id;  // Return correlation_id so caller can pass to completion event
  }

  recordCompletion(type: InteractionType, correlationId: string, details: Record<string, unknown>, startTimestamp: string): void {
    this.log.push({
      seq: this.seq++,
      timestamp: new Date().toISOString(),
      type,
      details,
      correlation_id: correlationId,
      duration_ms: Date.now() - new Date(startTimestamp).getTime(),
    });
  }

  getLog(): InteractionLogEntry[] {
    return [...this.log];
  }

  clear(): void {
    this.log = [];
    this.seq = 0;
  }
}

export const interactionLogger = new InteractionLogger();
```

- **Singleton** instance exported for use across the app.
- `record()` returns a `correlation_id` that callers pass to `recordCompletion()` for async pairs.
- `clear()` called when a new study is loaded (start of a new session scope).
- No React state — the log is only read at save time, avoiding unnecessary re-renders.
- No external dependency needed: use `crypto.randomUUID()` (available in all modern browsers) instead of uuid package.

---

## 5. Instrument App.tsx Handlers

Add `interactionLogger.record(...)` calls in each handler. For async handlers, capture the `correlation_id` at start and log completion.

### Example: Analysis Step 1

```typescript
const handleRunAnalysis = useCallback(async () => {
  const corrId = interactionLogger.record('analysis_step1_started', {
    element: selectedBranch,
  });
  const startTs = new Date().toISOString();

  try {
    const step1 = await api.runAnalysisStep1(selectedBranch);
    interactionLogger.recordCompletion('analysis_step1_completed', corrId, {
      element: selectedBranch,
      overloads_found: step1.lines_overloaded,
      n_overloads: step1.lines_overloaded.length,
      can_proceed: step1.can_proceed,
      dc_fallback: step1.dc_fallback ?? false,
      message: step1.message,
    }, startTs);
    // ... rest of handler
  } catch (e) { /* ... */ }
}, [selectedBranch]);
```

### Example: Simple Toggle

```typescript
const handleActionFavorite = useCallback((actionId: string) => {
  const wasFavorited = selectedActionIds.has(actionId);
  interactionLogger.record(
    wasFavorited ? 'action_unfavorited' : 'action_favorited',
    { action_id: actionId }
  );
  // ... rest of handler
}, [selectedActionIds]);
```

### Full Handler → Event Mapping

| Handler | Event(s) | Async? |
|---------|----------|--------|
| `handleLoadConfig` | `config_loaded` (start+complete) | Yes |
| `handleOpenSettings` | `settings_opened` | No |
| `setSettingsTab` | `settings_tab_changed` | No |
| `handleApplySettings` | `settings_applied` (start+complete) | Yes |
| `handleCloseSettings` | `settings_cancelled` | No |
| `pickSettingsPath` | `path_picked` | No |
| `setSelectedBranch` (user-driven) | `contingency_selected` | No |
| `handleConfirmDialog` | `contingency_confirmed` | No |
| `handleRunAnalysis` | `analysis_step1_started` → `analysis_step1_completed` | Yes |
| `handleToggleOverload` | `overload_toggled` | No |
| `handleDisplayPrioritizedActions` (triggers step2) | `analysis_step2_started` → `analysis_step2_completed` | Yes |
| `handleDisplayPrioritizedActions` (merge) | `prioritized_actions_displayed` | No |
| `handleActionSelect(id)` | `action_selected` / `action_deselected` | Yes (diagram) |
| `handleActionFavorite` | `action_favorited` / `action_unfavorited` | No |
| `handleActionReject` | `action_rejected` / `action_unrejected` | No |
| `handleManualActionAdded` | `manual_action_simulated` | No |
| Combined modal open | `combine_modal_opened` | No |
| Combined modal close | `combine_modal_closed` | No |
| Combined toggle | `combine_pair_toggled` | No |
| Combined estimate callback | `combine_pair_estimated` | Yes |
| Combined simulate | `combine_pair_simulated` | Yes |
| `setActiveTab` | `diagram_tab_changed` | No |
| `handleViewModeChange` | `view_mode_changed` | No |
| `setVoltageRange` | `voltage_range_changed` | No |
| `handleAssetClick` | `asset_clicked` | No |
| `handleManualZoomIn` | `zoom_in` | No |
| `handleManualZoomOut` | `zoom_out` | No |
| `handleManualReset` | `zoom_reset` | No |
| `setInspectQuery` | `inspect_query_changed` | No |
| `handleVlDoubleClick` | `sld_overlay_opened` | No |
| `handleOverlaySldTabChange` | `sld_overlay_tab_changed` | No |
| `handleOverlayClose` | `sld_overlay_closed` | No |
| `handleSaveResults` | `session_saved` | Yes |
| `handleOpenReloadModal` | `session_reload_modal_opened` | Yes |
| `handleRestoreSession` | `session_reloaded` | Yes |

---

## 6. Save Interaction Log with Session

### Modify `frontend/src/utils/sessionUtils.ts`

Add `interaction_log` field to `SessionInput`:

```typescript
export interface SessionInput {
  // ... existing fields ...
  interactionLog: InteractionLogEntry[];
}
```

### Modify `SessionResult` in `types.ts`

```typescript
export interface SessionResult {
  // ... existing fields ...
  interaction_log?: InteractionLogEntry[];
}
```

### Update `buildSessionResult()`

Include `input.interactionLog` in the returned object.

### Update `handleSaveResults` in `App.tsx`

Pass the current log when building the session:

```typescript
const session = buildSessionResult({
  // ... existing fields ...
  interactionLog: interactionLogger.getLog(),
});
```

---

## 7. Backend: Save Interaction Log as Separate File

### Modify `POST /api/save-session` in `expert_backend/main.py`

Add an optional `interaction_log` field to the `SaveSessionRequest`:

```python
class SaveSessionRequest(BaseModel):
    session_name: str
    json_content: str
    pdf_path: str | None = None
    output_folder_path: str
    interaction_log: str | None = None  # JSON string of interaction log entries
```

In the handler, write `interaction_log.json` alongside `session.json`:

```python
if req.interaction_log:
    log_path = os.path.join(session_folder, "interaction_log.json")
    with open(log_path, "w") as f:
        f.write(req.interaction_log)
```

### Update `frontend/src/api.ts`

Add `interaction_log` to the `saveSession` call.

### Update `handleSaveResults` in App.tsx

Pass the serialized interaction log as a separate field (not embedded in session.json, to keep session.json clean and backward-compatible):

```typescript
await api.saveSession({
  // ... existing params ...
  interaction_log: JSON.stringify(interactionLogger.getLog(), null, 2),
});
```

---

## 8. Output Structure

After saving, the session folder will contain:

```
<output_folder>/
  expertassist_session_LINE_XYZ_2026-03-18T10-30-00/
    session.json            ← existing: full state snapshot
    interaction_log.json    ← NEW: replay-ready event log
    overflow_abc123.pdf     ← existing: overflow graph copy
```

### `interaction_log.json` example (replay-ready)

```json
[
  {
    "seq": 0,
    "timestamp": "2026-03-18T10:20:01.123Z",
    "type": "config_loaded",
    "correlation_id": "a1b2c3d4",
    "details": {
      "network_path": "/data/network.xiidm",
      "action_file_path": "/data/actions.json",
      "layout_path": "/data/grid_layout.json",
      "min_line_reconnections": 2.0,
      "min_close_coupling": 3.0,
      "min_open_coupling": 2.0,
      "min_line_disconnections": 3.0,
      "min_pst": 1.0,
      "n_prioritized_actions": 10,
      "lines_monitoring_path": "",
      "monitoring_factor": 0.95,
      "pre_existing_overload_threshold": 0.02,
      "ignore_reconnections": false,
      "pypowsybl_fast_mode": true
    }
  },
  {
    "seq": 1,
    "timestamp": "2026-03-18T10:20:15.456Z",
    "type": "contingency_selected",
    "correlation_id": "e5f6a7b8",
    "details": { "element": "LINE_XYZ" }
  },
  {
    "seq": 2,
    "timestamp": "2026-03-18T10:20:30.789Z",
    "type": "analysis_step1_started",
    "correlation_id": "c9d0e1f2",
    "details": { "element": "LINE_XYZ" }
  },
  {
    "seq": 3,
    "timestamp": "2026-03-18T10:20:45.012Z",
    "type": "analysis_step1_completed",
    "correlation_id": "c9d0e1f2",
    "details": {
      "element": "LINE_XYZ",
      "overloads_found": ["LINE_A", "LINE_B", "LINE_C"],
      "can_proceed": true,
      "dc_fallback": false,
      "message": "3 overloaded lines detected"
    },
    "duration_ms": 14223
  },
  {
    "seq": 4,
    "timestamp": "2026-03-18T10:21:00.345Z",
    "type": "overload_toggled",
    "correlation_id": "d3e4f5a6",
    "details": { "overload": "LINE_C", "selected": false }
  },
  {
    "seq": 5,
    "timestamp": "2026-03-18T10:21:05.678Z",
    "type": "analysis_step2_started",
    "correlation_id": "b7c8d9e0",
    "details": {
      "element": "LINE_XYZ",
      "selected_overloads": ["LINE_A", "LINE_B"],
      "all_overloads": ["LINE_A", "LINE_B", "LINE_C"],
      "monitor_deselected": false
    }
  },
  {
    "seq": 6,
    "timestamp": "2026-03-18T10:21:30.901Z",
    "type": "analysis_step2_completed",
    "correlation_id": "b7c8d9e0",
    "details": {
      "n_actions": 5,
      "action_ids": ["disco_42", "reco_17", "topo_03", "pst_01", "disco_88"],
      "dc_fallback": false,
      "message": "Found 5 prioritized actions",
      "pdf_url": "/results/pdf/overflow_abc123.pdf"
    },
    "duration_ms": 25123
  },
  {
    "seq": 7,
    "timestamp": "2026-03-18T10:21:35.000Z",
    "type": "prioritized_actions_displayed",
    "correlation_id": "f1a2b3c4",
    "details": { "n_actions": 5 }
  },
  {
    "seq": 8,
    "timestamp": "2026-03-18T10:22:00.234Z",
    "type": "action_selected",
    "correlation_id": "a5b6c7d8",
    "details": { "action_id": "disco_42" }
  },
  {
    "seq": 9,
    "timestamp": "2026-03-18T10:22:10.567Z",
    "type": "action_favorited",
    "correlation_id": "e9f0a1b2",
    "details": { "action_id": "disco_42" }
  },
  {
    "seq": 10,
    "timestamp": "2026-03-18T10:22:20.890Z",
    "type": "diagram_tab_changed",
    "correlation_id": "c3d4e5f6",
    "details": { "from_tab": "n-1", "to_tab": "action" }
  },
  {
    "seq": 11,
    "timestamp": "2026-03-18T10:23:00.123Z",
    "type": "action_rejected",
    "correlation_id": "a7b8c9d0",
    "details": { "action_id": "reco_17" }
  },
  {
    "seq": 12,
    "timestamp": "2026-03-18T10:25:00.456Z",
    "type": "session_saved",
    "correlation_id": "e1f2a3b4",
    "details": {
      "session_name": "expertassist_session_LINE_XYZ_2026-03-18T10-25-00",
      "output_folder": "/data/output"
    }
  }
]
```

---

## 9. Tests

### `frontend/src/utils/interactionLogger.test.ts` (unit tests)

- `record()` appends entries with correct timestamp, type, and incrementing seq
- `record()` returns a correlation_id
- `recordCompletion()` links to the same correlation_id and includes duration_ms
- `getLog()` returns a copy (not a reference)
- `clear()` empties the log and resets seq counter
- Multiple records maintain insertion order

### `frontend/src/utils/sessionUtils.test.ts` (extend existing)

- `buildSessionResult` includes `interaction_log` when provided
- `interaction_log` is empty array when no interactions recorded

---

## 10. Update Documentation

### `CLAUDE.md`

- Add `interactionLogger.ts` to the architecture tree
- Document the interaction logging feature
- Add `interaction_log.json` to the session output description

### `docs/save-results.md`

- Add `interaction_log.json` to the "What is saved" section
- Add a "Replay" section explaining the log format and replay contract
- Document the event types table

---

## Files Modified

| File | Change |
|------|--------|
| `frontend/src/types.ts` | Add `InteractionType`, `InteractionLogEntry`; add `interaction_log?` to `SessionResult` |
| `frontend/src/utils/interactionLogger.ts` | **NEW** — singleton logger class with correlation support |
| `frontend/src/utils/interactionLogger.test.ts` | **NEW** — unit tests for logger |
| `frontend/src/utils/sessionUtils.ts` | Add `interactionLog` to `SessionInput`; include in output |
| `frontend/src/utils/sessionUtils.test.ts` | Add test for interaction_log in session |
| `frontend/src/App.tsx` | Import logger; add `record()`/`recordCompletion()` calls in ~30 handlers |
| `frontend/src/api.ts` | Add `interaction_log` param to `saveSession` |
| `frontend/src/components/CombinedActionsModal.tsx` | Add logging for combine modal open/close, pair toggle, estimate, simulate |
| `expert_backend/main.py` | Add `interaction_log` field to `SaveSessionRequest`; write file |
| `CLAUDE.md` | Document new feature |
| `docs/save-results.md` | Document `interaction_log.json` and replay contract |

---

## Implementation Order

1. Types (`types.ts`) — define the data model
2. Logger utility (`interactionLogger.ts`) — the core module with correlation support
3. Logger tests (`interactionLogger.test.ts`)
4. Session utils update (`sessionUtils.ts`) — wire log into save
5. Session utils tests update
6. API client update (`api.ts`) — pass log to backend
7. Backend update (`main.py`) — accept and write log file
8. App.tsx instrumentation — add `record()` calls to all handlers
9. CombinedActionsModal instrumentation — add logging for combine interactions
10. CLAUDE.md + docs update
11. Run tests, lint, build
12. Commit and push
