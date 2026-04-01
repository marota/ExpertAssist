# Renewable Curtailment Actions — Revised Implementation Specification

This document outlines the changes required to integrate renewable curtailment actions into ExpertAssist. Renewable curtailment is the generation-side counterpart to load shedding, and its implementation follows the same architectural patterns.

## 1. Library Interface (expert_op4grid_recommender)

The implementation depends on functional parity in the `expert_op4grid_recommender` library (implementing PR #71 requirements).

### Configuration
`config.py` must include:
- `MIN_RENEWABLE_CURTAILMENT` (float): Minimum score threshold for renewable curtailment actions (default: 0.0).

### Action Classification
`ActionClassifier.identify_grid2op_action_type()` must return `"open_gen"` for actions that disconnect one or more generators (where `gen_set_bus == -1` and no other elements except switches/nodes are modified).

### Recommendation Results
The analysis output now includes a `renewable_curtailment` key in `action_scores`, containing:
- `scores`: Map of `action_id` to its score.
- `mw_start`: Map of `action_id` to the MW value of the curtailed generator(s) at the start of the action (N-state or N-1 state).
- `params`: Relevant scoring parameters (e.g., energy source type).

## 2. ExpertAssist Backend

### Configuration Models
Update `expert_backend/main.py`:
- Add `min_renewable_curtailment: float = 0.0` to `ConfigRequest`.
- Update `get_config()` to return the new parameter.
- Update `action_dict_stats` to include a count of `"open_gen"` actions.

### Network Service
Update `expert_backend/services/network_service.py`:
- Implement `get_generator_voltage_level(gen_id: str)` to resolve generator IDs to their voltage levels via pypowsybl.

### Recommender Service
Update `expert_backend/services/recommender_service.py`:
- **Config Mapping**: Propagate `min_renewable_curtailment` from `Settings` to the library's `config.MIN_RENEWABLE_CURTAILMENT`.
- **Curtailment Enrichment**:
    ```python
    def _compute_curtailment_details(self, action_topology):
        # 1. Identify disconnected generators from gens_bus
        # 2. Compute curtailed MW (pre-action production vs post-action production)
        # 3. Resolve voltage_level_id & energy_source
        # 4. Return list of CurtailmentDetail objects
    ```
- **MW lookup**: Implement `_get_action_mw_start` for `renewable_curtailment` / `open_gen` to fetch pre-action production values from the observation.

## 3. ExpertAssist Frontend

### Types
Update `frontend/src/types.ts`:
- Add `CurtailmentDetail` interface:
  ```typescript
  export interface CurtailmentDetail {
      generator_name: string;
      voltage_level_id: string | null;
      energy_source: string;
      curtailed_mw: number;
  }
  ```
- Add `curtailment_details?: CurtailmentDetail[]` to `ActionDetail` and `SavedActionEntry`.
- Add `min_renewable_curtailment: number` to `ConfigRequest` and `SettingsBackup`.

### Settings UI
Update `SettingsModal.tsx`:
- Add a "Renewable Curtailment" numeric input in the Recommender tab, following "Min Load Shedding".

### Action Feed & Filtering
Update `ActionFeed.tsx`:
- Add a `curtail` checkbox to the manual selection search dropdown.
- Add logic to identify "curtailment" actions in `filteredActions` and `scoredActionsList` (types containing `"curtail"` or `"open_gen"`).
- Render `curtailment_details` in the action card, styled with a distinct color (greenish) to differ from load shedding.

### Combined Actions
Update `CombinedActionsModal.tsx`:
- Add a `CURTAIL` filter button to the exploration tab.
- Ensure combined actions involving curtailment propagate their details correctly.

## 4. Session Persistence
Ensure `session_service.py` and frontend session saving logic include `min_renewable_curtailment` and `curtailment_details`.
