# Renewable Curtailment Actions

## Context

This document describes the integration of **renewable curtailment** actions into ExpertAssist, following changes introduced in [Expert_op4grid_recommender PR #71](https://github.com/marota/Expert_op4grid_recommender/pull/71/).

Curtailment is the symmetric counterpart to **load shedding**:

| | Load Shedding | Renewable Curtailment |
|---|---|---|
| **Target** | Loads (consumption) | Renewable generators (WIND / SOLAR) |
| **Side of overloaded line** | Downstream (aval) | Upstream (amont) |
| **Grid2Op mechanism** | `set_bus: {loads_id: {load: -1}}` | `set_bus: {generators_id: {gen: -1}}` |
| **MW metric** | `P_shed_MW` — load power lost | `P_curtailment_MW` — generation power lost |
| **Classifier type** | `load_shedding` | `open_gen` / `renewable_curtailment` |

---

## Library Changes (Expert_op4grid_recommender)

### New configuration parameters

| Parameter | Default | Description |
|---|---|---|
| `MIN_RENEWABLE_CURTAILMENT` | `0` | Minimum number of curtailment actions to include in prioritized results |
| `RENEWABLE_CURTAILMENT_MARGIN` | `0.05` | Safety margin (5%) added when computing required curtailment MW |
| `RENEWABLE_CURTAILMENT_MIN_MW` | `1.0` | Generators below this MW threshold are excluded as candidates |
| `RENEWABLE_ENERGY_SOURCES` | `["WIND", "SOLAR"]` | Energy source types considered renewable |

### New action score category

`action_scores` now includes a `renewable_curtailment` key with the same `{scores, params, non_convergence}` structure as other categories:

```python
"renewable_curtailment": {
    "scores": {"open_gen_GEN_WIND_1": 0.85, ...},
    "params": {
        "open_gen_GEN_WIND_1": {
            "substation": "SUB_A",
            "node_type": "amont",
            "generator_name": "GEN_WIND_1",
            "energy_source": "WIND",
            "influence_factor": 0.72,
            "P_curtailment_MW": 45.3,
            "P_overload_excess_MW": 32.1,
            "available_gen_MW": 50.0,
            "coverage_ratio": 1.0,
            "generators_curtailed": ["GEN_WIND_1"],
            "assets": {"lines": [...], "loads": [...], "generators": [...]}
        }
    },
    "non_convergence": {}
}
```

### New observation properties

- `gen_energy_source` — numpy array of energy source strings per generator
- `gen_renewable` — boolean numpy array indicating renewable status

### Classifier

`ActionClassifier.identify_grid2op_action_type()` now returns `"open_gen"` for actions that disconnect one or more generators (`gen_set_bus == -1`).

---

## ExpertAssist Integration

### 1. Backend — Configuration

**`main.py`** `ConfigRequest` model gains a new field:

```python
min_renewable_curtailment: float = 0.0
```

**`recommender_service.py`** `apply_settings()` maps it to:

```python
config.MIN_RENEWABLE_CURTAILMENT = settings.min_renewable_curtailment
```

The `/api/config` response `action_dict_stats` gains a `curtailment` count, detected via the classifier's `open_gen` type.

### 2. Backend — Action enrichment

A new `_compute_curtailment_details()` method mirrors the existing `_compute_load_shedding_details()`:

1. Reads `gens_bus` from the action topology
2. Filters generators with `bus == -1` (disconnected)
3. Computes curtailed MW: `gen_p(N-1) - gen_p(post-action)` for each generator
4. Resolves each generator's voltage level via `network_service`
5. Looks up `energy_source` from the library's observation data

Returns a list attached to the enriched action as `curtailment_details`:

```python
[
    {
        "generator_name": "GEN_WIND_1",
        "voltage_level_id": "VL_HV_1",
        "energy_source": "WIND",
        "curtailed_mw": 45.3
    }
]
```

### 3. Backend — MW at start

`_get_action_mw_start()` gains a `renewable_curtailment` / `open_gen` branch:

- Extracts generator name from `content.set_bus.generators_id`
- Returns `gen_p` of that generator in the N-1 observation

### 4. Frontend — Types

New interface:

```typescript
interface CurtailmentDetail {
    generator_name: string;
    voltage_level_id: string | null;
    energy_source: string;       // "WIND" | "SOLAR"
    curtailed_mw: number;
}
```

Added to `ActionDetail`, `SavedActionEntry`:

```typescript
curtailment_details?: CurtailmentDetail[];
```

`ConfigRequest` and `SettingsBackup` gain `min_renewable_curtailment` / `minRenewableCurtailment`.

### 5. Frontend — Settings UI

A new **Min Renewable Curtailment** numeric input appears in the Recommender settings section, next to the existing Min Load Shedding input. Default: `0.0`.

The value is:
- Sent in `POST /api/config` payload
- Persisted in session save/load
- Shown in the recommender settings summary in the ActionFeed header

### 6. Frontend — Action type filter

A new `curtail` filter toggle is added in both:

- **ActionFeed** search dropdown — checkbox: `[x] Curtailment`
- **CombinedActionsModal** explore tab — pill button: `CURTAIL`

Detection logic: action type contains `renewable_curtailment` or `open_gen`.

### 7. Frontend — Rendering

Curtailment details render in an info box styled similarly to load shedding but with a distinct color (green-tinted to suggest generation):

```
Curtailment of **45.3 MW** on generator **GEN_WIND_1** (WIND) at voltage level **VL_HV_1**
```

The voltage level is a clickable badge (zoom to NAD / double-click for SLD), consistent with load shedding detail interaction.

Target equipment badges for curtailment actions show VL badges derived from `curtailment_details`, following the same pattern as load shedding.

### 8. Frontend — Session persistence

`curtailment_details` is saved/restored alongside `load_shedding_details` in `SavedActionEntry`. The `min_renewable_curtailment` config value is included in `SessionResult.configuration`.

---

## Files Modified

| File | Change |
|---|---|
| `expert_backend/main.py` | `ConfigRequest` field, action dict stats |
| `expert_backend/services/recommender_service.py` | Config mapping, `_compute_curtailment_details()`, MW-at-start |
| `frontend/src/types.ts` | `CurtailmentDetail` interface, field additions |
| `frontend/src/api.ts` | Config payload type |
| `frontend/src/hooks/useSettings.ts` | State, payload, backup, restore |
| `frontend/src/hooks/useSession.ts` | Save/restore config field |
| `frontend/src/App.tsx` | Settings UI input |
| `frontend/src/components/ActionFeed.tsx` | Filter toggle, classification, detail rendering |
| `frontend/src/components/CombinedActionsModal.tsx` | Filter pill button |
| `frontend/src/utils/sessionUtils.ts` | Session serialization |
| Test files | Updated fixtures (`sessionUtils.test.ts`, `ActionFeed.test.tsx`, `useSession.test.ts`) |

## Backward Compatibility

All new fields are **optional** (`?` in TypeScript, `= 0.0` defaults in Python). Existing sessions saved without curtailment data load without issue. Older versions of the recommender library that don't produce `renewable_curtailment` scores simply result in an empty category — no curtailment cards appear and the filter has no effect.
