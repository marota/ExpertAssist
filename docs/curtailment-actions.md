# Renewable Curtailment & Load Shedding — Implementation Status

This document describes the implementation of renewable curtailment and load shedding actions in Co-Study4Grid, including the recent migration to the **power reduction format** (`set_load_p`/`set_gen_p`) introduced in [Expert_op4grid_recommender PR #74](https://github.com/marota/Expert_op4grid_recommender/pull/74).

## 1. Action Format Evolution

### Legacy Format (bus disconnection)

The original implementation disconnected loads/generators from the grid by setting their bus to -1:

```python
# Load shedding
{"set_bus": {"loads_id": {"LOAD_1": -1}}}
# Topology: loads_bus = {"LOAD_1": -1}

# Renewable curtailment
{"set_bus": {"generators_id": {"WIND_1": -1}}}
# Topology: gens_bus = {"WIND_1": -1}
```

This completely disconnects the element, losing voltage support and reactive power.

### New Format (power reduction)

PR #74 introduces active power setpoint changes that keep elements electrically connected:

```python
# Load shedding — reduce load to target MW
{"set_load_p": {"LOAD_1": 0.0}}
# Topology: loads_p = {"LOAD_1": 0.0}

# Renewable curtailment — reduce generation to target MW
{"set_gen_p": {"WIND_1": 0.0}}
# Topology: gens_p = {"WIND_1": 0.0}
```

The target MW can be any value between 0 and the current production/consumption, enabling **partial** load shedding and curtailment (configurable MW slider — planned feature).

### New Metadata Fields

The recommender library now provides explicit metadata on power reduction actions:
- `target_p_MW`: The target power setpoint value
- `reduction_MW`: The actual amount of power reduced
- `mw_required`: The required MW reduction amount

## 2. Library Interface (expert_op4grid_recommender)

### Configuration
- `config.MIN_LOAD_SHEDDING` (int): Minimum number of load shedding actions to recommend.
- `config.MIN_RENEWABLE_CURTAILMENT_ACTIONS` (int): Minimum number of curtailment actions to recommend.

### Action Classification
`ActionClassifier` classifies actions as:
- `"load_shedding"` / `"load_power_reduction"` — actions that reduce load consumption
- `"renewable_curtailment"` / `"gen_power_reduction"` / `"open_gen"` — actions that reduce renewable generation

### Recommendation Results
The analysis output includes:
- `action_scores["load_shedding"]` — scores and `mw_start` for load shedding actions
- `action_scores["renewable_curtailment"]` — scores and `mw_start` for curtailment actions

## 3. Backend Implementation

### Configuration (`main.py`)
- `ConfigRequest` includes `min_load_shedding: int` and `min_renewable_curtailment_actions: int`
- Propagated to `config.MIN_LOAD_SHEDDING` and `config.MIN_RENEWABLE_CURTAILMENT_ACTIONS`

### Network Service (`network_service.py`)
- `get_load_voltage_level(load_id)` — resolves load ID to its voltage level
- `get_generator_voltage_level(gen_id)` — resolves generator ID to its voltage level

### Recommender Service (`recommender_service.py`)

#### Action Enrichment (`_enrich_actions`)
Extracts topology fields from action objects, including both legacy and new fields:
```python
for field in ("lines_ex_bus", "lines_or_bus", "gens_bus", "loads_bus",
              "pst_tap", "substations", "switches", "loads_p", "gens_p"):
```

#### Load Shedding Details (`_compute_load_shedding_details`)
Detects affected loads from **both** formats:
1. Legacy: `loads_bus` entries with `bus == -1`
2. New: `loads_p` attribute on the action object, or `set_load_p` in action content

Returns `[{load_name, voltage_level_id, shedded_mw}]` computed by comparing N-1 and post-action observations.

#### Curtailment Details (`_compute_curtailment_details`)
Same dual-format detection for generators:
1. Legacy: `gens_bus` entries with `bus == -1`
2. New: `gens_p` attribute on the action object, or `set_gen_p` in action content

Returns `[{gen_name, voltage_level_id, curtailed_mw}]`. Only includes generators identified as renewable by `_is_renewable_gen()`.

#### MW Start Computation
`_mw_start_load_shedding()` and `_mw_start_curtailment()` check for both formats:
1. New format first: `content.set_load_p` / `content.set_gen_p`
2. Legacy fallback: `content.set_bus.loads_id` / `content.set_bus.generators_id` with `bus == -1`
3. Action ID pattern fallback: `load_shedding_<name>` / `curtail_<name>`

#### Dynamic Action Creation
When a user manually simulates `load_shedding_<name>` or `curtail_<name>`, the backend creates the action on-the-fly using the **new format**:
```python
# load_shedding_LOAD_1 → topology: {"loads_p": {"LOAD_1": 0.0}}
# curtail_WIND_1       → topology: {"gens_p": {"WIND_1": 0.0}}
```

#### Topology Reconstruction (`_build_action_entry_from_topology`)
Maps topology fields to action content:
- `loads_p` → `content.set_load_p`
- `gens_p` → `content.set_gen_p`
- Legacy `loads_bus` → `content.set_bus.loads_id` (unchanged)

## 4. Frontend Implementation

### Types (`types.ts`)
```typescript
interface ActionTopology {
    lines_ex_bus: Record<string, number>;
    lines_or_bus: Record<string, number>;
    gens_bus: Record<string, number>;
    loads_bus: Record<string, number>;
    pst_tap?: Record<string, unknown>;
    substations?: Record<string, unknown>;
    switches?: Record<string, unknown>;
    loads_p?: Record<string, number>;   // New power reduction
    gens_p?: Record<string, number>;    // New power reduction
}

interface LoadSheddingDetail {
    load_name: string;
    voltage_level_id: string | null;
    shedded_mw: number;
}

interface CurtailmentDetail {
    gen_name: string;
    voltage_level_id: string | null;
    curtailed_mw: number;
}
```

### Action Feed (`ActionFeed.tsx`)
- **Filtering**: `Load Shedding` and `Renewable Curtailment` checkbox filters in manual selection search
- **Score table**: Shows `MW Start` column (current load/generation MW before action)
- **Action cards**:
  - Load shedding details: amber background (`#fef3c7`), shows shedded MW and load name per load
  - Curtailment details: light blue background (`#e0f2fe`), shows curtailed MW and generator name
  - Clickable voltage level badges for navigation
- **Equipment badges**: Extracted from `loads_p`/`gens_p` in addition to `loads_bus`/`gens_bus`

### SVG Utilities (`svgUtils.ts`)
- Target detection accounts for `loads_p`/`gens_p` when determining affected equipment
- Line reconnection check excludes actions with `loads_p`/`gens_p` (not pure reconnections)

### Visualization Panel (`VisualizationPanel.tsx`)
- Target equipment IDs include elements from `loads_p`/`gens_p` for highlighting

### Session Persistence
- `sessionUtils.ts` serializes `action_topology` (including `loads_p`/`gens_p`) and `load_shedding_details`/`curtailment_details` in session snapshots
- Session restore reconstructs actions via `_build_action_entry_from_topology()` which handles both formats

## 5. Testing

### Backend (`expert_backend/tests/`)
- `test_power_reduction_format.py` — 23 tests covering all new format scenarios:
  - Detection of loads_p/gens_p in compute details functions
  - MW start extraction from set_load_p/set_gen_p
  - Topology-to-content mapping
  - Dynamic action creation with new format
  - Backwards compatibility with legacy format
- `test_renewable_curtailment.py` — curtailment detail computation and config updates
- `test_manual_action_enrichment.py` — enrichment with new topology format
- `test_dynamic_actions.py` — on-the-fly action creation
- `test_mw_start.py` — MW start computation for all action types
- `test_configurable_mw.py` — 8 tests for configurable MW reduction:
  - Partial load shedding with target_mw (setpoint = current - target, clamped >= 0)
  - Partial curtailment with target_mw
  - Full shedding/curtailment when target_mw is omitted
  - Clamping when target_mw exceeds current MW
  - Re-simulation of existing actions with updated target_mw
  - Content unchanged when target_mw is not provided on re-simulation

### Frontend (`frontend/src/`)
- `ActionFeed.test.tsx` — rendering of load shedding/curtailment details with both topology formats, Target MW input in score table, editable MW + re-simulate in action cards
- `svgUtils.test.ts` — target detection with loads_p/gens_p fields

## 6. Configurable MW Reduction

Users can choose how much MW to reduce when simulating load shedding or curtailment actions, enabling **partial** reductions instead of full disconnection.

### Semantics

- **Target MW** = the amount of MW to reduce (not the remaining setpoint)
- **Setpoint** = `current_mw - target_mw` (clamped to >= 0)
- When `target_mw` is omitted, full reduction is applied (setpoint = 0)

### API

`POST /api/simulate-manual-action` accepts an optional `target_mw` field:

```json
{
    "action_id": "load_shedding_LOAD_1",
    "disconnected_element": "LINE_X",
    "target_mw": 30.0
}
```

### Backend (`recommender_service.py`)

#### Dynamic Action Creation
When creating `load_shedding_<name>` or `curtail_<name>` actions on-the-fly:
1. Look up current MW from the N-1 observation (`obs_n1.load_p` / `obs_n1.gen_p`)
2. Compute `remaining = max(0, current_mw - target_mw)`
3. Use `remaining` as the setpoint in `loads_p` / `gens_p`

#### Re-simulation of Existing Actions
When `target_mw` is provided for an action already in `_dict_action`:
1. Update `set_load_p` or `set_gen_p` entries in the content with the new setpoint
2. The updated content is then used by `env.action_space()` for simulation

### Frontend (`ActionFeed.tsx`)

#### Score Table (Manual Selection)
- **Target MW column**: Shown for `load_shedding` and `renewable_curtailment` score table sections
- Input field: number input (0 to MW Start), pre-filled with placeholder = MW Start
- Clicking a row passes the entered `target_mw` to `simulateManualAction`

#### Action Card Detail Boxes
- **Reduction MW input**: Editable number field in load shedding (amber) and curtailment (blue) detail boxes
- **Re-simulate button**: Triggers `simulateManualAction` with the new `target_mw` value
- Default value: the total shedded/curtailed MW from the current simulation result
- The action card updates in-place with the new simulation results
