# Performance Profiling: Network Diagram & Visualization

This document details the performance bottlenecks identified in ExpertAssist when working with large electrical grids (e.g., the French grid with ~10k branches).

## Performance Characterization

Profiling was conducted using `config_large_grid.json` across three primary user scenarios.

### Scenario Timings

| Scenario | Component | Duration | Note |
|---|---|---|---|
| **1. Initial Load** | `pp.network.load` | ~2.4s | XIIDM parsing overhead |
| | Action Dict Load | ~2.3s | Loading/enriching the action space |
| | Base Diagram | ~2.5s | pypowsybl NAD generation for full grid |
| **2. Contingency Selection** | N-1 Analysis | ~12.5s | Core contingency load flow |
| | Flow Delta Calculation | ~3.5s | Python-side loop over 10k branches |
| | N-1 Diagram | ~2.5s | pypowsybl NAD generation |
| **3. Manual Action** | Action Simulation | ~15.9s | Re-simulating N-1 then applying action |
| | Action Diagram | ~2.4s | pypowsybl NAD generation |

## Identified Bottlenecks

### 1. Large SVG Payload (~13 MB)
The pypowsybl Network Area Diagram (NAD) for the full French grid produces an SVG string of approximately 13 MB. 
- **Impact**: High latency during transmission and significant DOM thrashing in the frontend during rendering and pan/zoom.
- **Current Mitigation**: `boostSvgForLargeGrid` attempts to scale elements but doesn't reduce total element count.

### 2. Python-Side Flow Deltas
The `_compute_deltas` method in `recommender_service.py` iterates over every branch in Python.
- **Impact**: Takes 2.0s to 3.5s per diagram update.
- **Optimization Potential**: Vectorizing this logic using NumPy would reduce this to <0.1s.

### 3. Simulation Latency
- **N-1 Contingency Analysis**: 12.5s is the baseline for a full grid simulation.
- **Manual Action Simulation**: 16s is unexpectedly high for a single action, suggesting inefficiencies in how the action is applied or how the environment state is managed.

## Profiling Tools

A standalone profiling script is available at `scripts/profile_diagram_perf.py`. It benchmarks:
1. Initial network loading and base diagram generation.
2. Contingency selection and N-1 diagram generation.
3. Manual action application and post-action diagram generation.

**Usage:**
```bash
# Run with project venv
./venv_expert_assist_py310/bin/python scripts/profile_diagram_perf.py config_large_grid.json
```
