# Loading Study — parallelised XHR waterfall + text-format base diagram

## Context (v6 trace)

Chrome DevTools trace of a full "Load Study" gesture on the large grid
(PyPSA-EUR France 400 kV, ~25 MB SVG) showed the following XHR
waterfall:

```
0.0 s  ────── /api/config              14.1 s   (server pypowsybl load)
14.1 s ─┬──── /api/voltage-levels       0.3 s
        ├──── /api/nominal-voltages     0.3 s
        └──── /api/branches             0.8 s
14.9 s ────── /api/network-diagram      6.6 s   (2.5 MB gzip, 25 MB decoded)
21.5 s ────── client render            ~3.5 s
```

Two findings in the waterfall:

1. **`/api/network-diagram` waited for `/api/branches`** — the frontend
   passed `voltageLevels.length` as a hint to `processSvg` (node/text
   upscaling on large grids), so the diagram call only fired after the
   `Promise.all([branches, voltage-levels, nominal-voltages])` settled.
   That ~0.8 s gap is pure serialisation cost.
2. **`XHRLoad` = 620 ms** on the 25 MB response — attributable to
   `JSON.parse` of the giant SVG string embedded inside the JSON envelope.
   JSON parsers have to escape-scan every byte and allocate a second
   buffer for the string value, both of which scale linearly with
   payload size.

## Changes

### #1 — Parallelise the 4 post-config XHRs (`App.tsx` + `useSession.ts`)

```diff
- const [branchRes, vlRes, nomVRes] = await Promise.all([
-   api.getBranches(),
-   api.getVoltageLevels(),
-   api.getNominalVoltages(),
- ]);
- // ... state sets ...
- diagrams.fetchBaseDiagram(vlRes.voltage_levels.length);
+ const [branchRes, vlRes, nomVRes, diagramRaw] = await Promise.all([
+   api.getBranches(),
+   api.getVoltageLevels(),
+   api.getNominalVoltages(),
+   api.getNetworkDiagram(),
+ ]);
+ // ... state sets ...
+ diagrams.ingestBaseDiagram(diagramRaw, vlRes.voltage_levels.length);
```

Three call sites were updated:

- `App.tsx::applySettingsImmediate` (Apply Settings button)
- `App.tsx::handleLoadConfig` (Load Study button)
- `useSession.ts::handleRestoreSession` (session reload)

A new `ingestBaseDiagram(raw, vlCount)` method on `useDiagrams` does
just the `processSvg` + state-set work (no fetch), letting callers
drive the parallelism themselves. The legacy `fetchBaseDiagram(vlCount)`
helper is kept for backwards compat (tests, future single-call paths).

**Wire impact**: the diagram XHR now fires alongside
`branches`/`voltage-levels`/`nominal-voltages` at `t = config_end`,
so the critical path becomes `MAX(branches, nomV, vl, diagram) =
diagram`. Saves the ~0.8 s branches gap.

### #4 — `format=text` response for `/api/network-diagram`

Adds a `format` query parameter to the endpoint:

| `?format=json` (default) | `?format=text` (new) |
|---|---|
| `Content-Type: application/json` | `Content-Type: text/plain; charset=utf-8` |
| Body: `{"svg": "<svg>...</svg>", "metadata":..., ...}` | Body: `{"metadata":..., ...}\n<svg>...</svg>` |
| `JSON.parse(body)` scans the full 25 MB | `body.indexOf('\n')` + `JSON.parse(prefix)` — the SVG never passes through `JSON.parse` |

Gzip is still applied when the client signals `Accept-Encoding: gzip`
(same gate as `_maybe_gzip_json`), so wire bytes are unchanged.

The JSON default is preserved for backwards compatibility:
- `standalone_interface.html` (uses axios's JSON mode directly)
- third-party API consumers
- backend test `test_success` that still asserts on `response.json()`

The frontend `api.getNetworkDiagram` helper switches to
`?format=text` via `fetch` (axios would try to JSON-parse the body).

## Invariants (tested)

Backend (`test_api_endpoints.py::TestGetNetworkDiagram`):

- `test_success` — default `format=json` still returns `{"svg": ..., "metadata": ...}`.
- `test_text_format_returns_header_plus_svg` — `format=text` returns
  `Content-Type: text/plain`, the first line parses as JSON with all
  non-`svg` fields (`lines_overloaded`, `lines_overloaded_rho`, `metadata`),
  and the SVG is the rest of the body verbatim (NOT JSON-escaped).
- `test_text_format_gzip` — large text-format responses are
  `Content-Encoding: gzip` when the client sends `Accept-Encoding: gzip`.

Frontend (`api.test.ts::getNetworkDiagram`):

- Parses header + SVG correctly from the `text/plain` body.
- Surfaces non-2xx responses as thrown errors (preserves existing
  try/catch in App.tsx).

## Measured impact

Baseline (v6 trace, current main tip before this change):

| Segment | v6 wall-clock |
|---|---|
| `/api/config` | 14 103 ms |
| `/api/branches` (serial gate) | 775 ms |
| `/api/network-diagram` | 6 645 ms |
| XHRLoad (`JSON.parse`) | 618 ms |
| **Load Study total** | **~24.0 s** |

Expected after this change (to be confirmed on the next trace):

| Segment | Expected |
|---|---|
| `/api/config` | 14 103 ms (unchanged) |
| MAX(branches, nomV, vl, diagram) | ~6 645 ms |
| `XHRLoad` (header + raw SVG) | ~100-200 ms |
| **Load Study total** | **~20.9 s** (-12 %) |

The two wins combine naturally: parallel XHRs remove the branches gap
(0.8 s), text-format response removes most of the JSON-parse cost
(~400-500 ms). Server wall-clock is unchanged.

## What this does NOT change

- **Server compute time**: pypowsybl network load + NAD generation are
  untouched. The only way to shorten these is #2 (NAD generation during
  config) or #3 (disk cache of NAD on network hash+mtime) — see
  the analysis notes, out of scope for this commit.
- **Client render time** (~3.5 s Paint/Layout/Raster): untouched. The
  `ParseHTML` step that inserts the SVG into the DOM still runs — that
  is Blink parsing HTML, not the JSON parser.
- **standalone_interface.html** keeps using the legacy JSON endpoint
  because it is a self-contained fallback UI that does not share the
  fetch helper. Mirroring the parsing change would require replicating
  the header/body split logic there too; not worth the duplication.

## Files changed

| File | Change |
|---|---|
| `expert_backend/main.py` | Added `_maybe_gzip_svg_text` helper; `/api/network-diagram` now accepts `format=text` to return the header+SVG body. |
| `frontend/src/api.ts` | `getNetworkDiagram` uses `fetch` + `?format=text`, splits body on first `\n`, JSON-parses the header, treats the rest as SVG. |
| `frontend/src/hooks/useDiagrams.ts` | New `ingestBaseDiagram(raw, vlCount)` method that does `processSvg` + state-set without the fetch. Returned alongside `fetchBaseDiagram`. |
| `frontend/src/hooks/useSession.ts` | `RestoreContext` gains `ingestBaseDiagram`; session restore fires the diagram XHR in parallel with the other 3 and ingests the raw payload. |
| `frontend/src/App.tsx` | `applySettingsImmediate` and `handleLoadConfig` now `Promise.all` 4 XHRs and call `diagrams.ingestBaseDiagram` instead of `fetchBaseDiagram`. `ingestBaseDiagram` wired into `restoreContext`. |
| `frontend/src/api.test.ts` | `getNetworkDiagram` test rewritten to assert `fetch(..., '?format=text')` + header/body split. Added a non-ok-status test. |
| `frontend/src/hooks/useSession.test.ts` | Mock api now includes `getNetworkDiagram`; context mock includes `ingestBaseDiagram`. |
| `expert_backend/tests/test_api_endpoints.py` | Two new tests under `TestGetNetworkDiagram` covering `format=text` body shape and gzip. |
