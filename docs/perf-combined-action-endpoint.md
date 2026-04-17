# Combined manual-action endpoint (streamed NDJSON)

## Context

When the user clicks an action card that is NOT in the recommender's
prioritised-action list (typical scenarios: a manually-picked action, an
action from a reloaded session, a combined action built from the
`++ Combine` UI), the frontend fallback path previously fired two
**sequential** HTTP calls:

```
POST /api/simulate-manual-action   — grid2op simulate, ~3-4 s
POST /api/action-variant-diagram   — pypowsybl NAD regeneration, ~5-7 s on large grids
```

Two side-effects of this layout:

1. **One extra round-trip per click** — the UI waits for the simulation
   response to land before firing the diagram request.
2. **The sidebar action card (rho-before / rho-after / max-rho chip)
   cannot update until both calls complete.** Even though the
   simulation is a prerequisite for the diagram and NOT the diagram
   itself, the user sees the card stay "stale" for the full ~8 s.

## What shipped

A new streaming endpoint:

```
POST /api/simulate-and-variant-diagram
Content-Type: application/x-ndjson

{ "type": "metrics", <all simulate_manual_action fields> }\n
{ "type": "diagram", <all get_action_variant_diagram fields> }\n
```

On error at either step a single `{"type":"error","message":...}` event
is emitted and the stream closes.

The endpoint is a thin wrapper around the two existing service methods
— no new business logic. `simulate_manual_action` stores the resulting
observation in `RecommenderService._last_result`, which
`get_action_variant_diagram` then reads to pick the post-action variant.
The two methods are called **sequentially on the server**, so this
change does NOT save pypowsybl compute; the win is:

- **One fewer HTTP round-trip** per manual-action click (~100-500 ms
  off-box, ~10-50 ms on localhost).
- **Earlier sidebar update**: the `metrics` event is flushed to the
  wire the instant grid2op returns, so the action card's rho numbers
  appear ~5 s before the SVG does on large grids.

## Invariants (tested)

- `POST /api/simulate-and-variant-diagram` serves `application/x-ndjson`.
- It is NEVER wrapped by `_maybe_gzip_json` or a global `GZipMiddleware`
  — same reason `/api/run-analysis-step2` isn't: buffering NDJSON in
  gzip defeats the early-event delivery that is the point of the
  endpoint. A dedicated test (`test_ignores_accept_encoding_gzip`)
  confirms the response does not carry `Content-Encoding: gzip` even
  when the client sends `Accept-Encoding: gzip`.
- Events arrive in order (`metrics` first, `diagram` second). If the
  diagram step fails after the metrics step succeeds, the metrics event
  is still flushed so the UI can at least update the sidebar.
- All optional simulation parameters are forwarded: `action_content`,
  `lines_overloaded`, `target_mw`, `target_tap`, plus the `mode` field
  for the diagram step.

## Frontend integration

`api.ts` gets a new `simulateAndVariantDiagramStream` helper that
mirrors the existing `runAnalysisStep2Stream` pattern (fetch with
NDJSON response, caller reads with `TextDecoder` + `split('\n')`).

`useDiagrams.handleActionSelect` keeps the two-tier strategy:

1. **Fast path** — try `getActionVariantDiagram(actionId)` first. If
   the action is in `_last_result["prioritized_actions"]` (i.e. the
   recommender already computed it), this returns the diagram in a
   single call with no simulate work.
2. **Fallback** — on 4xx from the fast path, fire the new streaming
   endpoint. The metrics event updates `result.actions[actionId]`
   (rho fields, description, convergence flags, islanding info) as
   soon as simulation completes; the diagram event updates the active
   tab's SVG when the NAD is ready.

The old `api.simulateManualAction` is **kept** — other call sites may
use it (e.g. interactive re-simulation with different `target_mw` /
`target_tap` values) and removing it is out of scope.

## Files changed

| File | Change |
|---|---|
| `expert_backend/main.py` | New `SimulateAndVariantDiagramRequest` model + `POST /api/simulate-and-variant-diagram` endpoint (StreamingResponse). |
| `frontend/src/api.ts` | New `simulateAndVariantDiagramStream` helper. |
| `frontend/src/hooks/useDiagrams.ts` | Fallback branch in `handleActionSelect` replaced with NDJSON stream reader. Fast path unchanged. |
| `frontend/src/hooks/useDiagrams.test.ts` | Mock api now includes `simulateAndVariantDiagramStream`. |
| `expert_backend/tests/test_api_endpoints.py` | New `TestSimulateAndVariantDiagramStream` (5 tests). |

## Measured impact

Not yet captured as a trace — the v3 action-path numbers are the
baseline:

| XHR | v3 wall-clock |
|---|---|
| `/api/simulate-manual-action` | 3 412 ms |
| `/api/action-variant-diagram` | 4 933 ms |
| **Combined sequential** | **~8.3 s** |

Expected after this change:

- Same total compute time (both service methods still run).
- One XHR instead of two. Body: NDJSON stream.
- Sidebar card metrics visible ~5 s earlier.
- Wall-clock saving on the first `diagram` byte: limited to the
  round-trip gap (10-50 ms localhost, 100-500 ms real deployment).

The end-to-end wall-clock for the full operation is essentially
unchanged — the point of the change is **perceived latency**: the user
sees meaningful UI feedback at ~3.4 s instead of ~8.3 s on the fallback
path.

## What this does NOT change

- **Fast path** (action is in the prioritised list): still a single
  `getActionVariantDiagram` call. No behavioural change.
- **Server-side pypowsybl and grid2op work**: unchanged.
- **Network wire bytes**: same as the sum of the two old calls (SVG is
  still the bulk). Per-endpoint gzip on `/api/action-variant-diagram`
  compresses the SVG body today; the new streaming endpoint's diagram
  event is NOT gzipped on-wire because gzip-ing an NDJSON stream would
  defeat the early-event delivery that is the point of the change.
  That's the accepted tradeoff for this codepath.
