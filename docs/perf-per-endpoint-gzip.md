# Per-endpoint gzip on large SVG responses (Step 2)

## Context

After step 1 (`docs/perf-svg-tab-unmount.md`), the remaining floor on the
manual-action / N-1 paths is dominated by:

1. The server-side pypowsybl load-flow + NAD generation (unchanged here).
2. **Transferring ~28 MB of JSON-wrapped SVG** per diagram endpoint, entirely
   uncompressed — the trace headers showed
   `content-length: 28 430 383`, `content-encoding: none` on
   `/api/n1-diagram`.

SVG / JSON compresses ~10× with gzip (deeply repetitive XML namespace
declarations, path data, style strings). Enabling compression on these
endpoints alone removes ~25 MB of wire transfer per diagram call.

## Why not `GZipMiddleware` (again)

There was a previous attempt to enable compression globally:

```
commit 8c15de7  perf: fix NaN rendering and add gzip compression for large SVGs
commit 26bc49d  perf: fix overflow graph rendering delay and standalone UI tab switching
                — rolled back `app.add_middleware(GZipMiddleware, ...)`
```

The rollback commit's title tells the story:
**"fix overflow graph rendering delay"**. Starlette's `GZipMiddleware`
wraps every response, including the `StreamingResponse` returned by
`/api/run-analysis(-step2)`. Those endpoints emit NDJSON events one per
line, and the frontend relies on receiving the first `{"type":"pdf",...}`
event **before** the full `{"type":"result",...}` one so it can render the
Overflow PDF while the action enrichment finishes streaming. With
`GZipMiddleware` enabled, event lines were buffered inside the deflate
window until a gzip flush — the PDF event no longer arrived early, and
the "Overflow graph" tab appeared to hang until the whole analysis ended.
Additionally, the standalone UI's own NDJSON stream consumer was broken
by the same buffering.

Scoping compression to individual non-streaming endpoints sidesteps that.
The global middleware import is left in place (dead code for now), but
the middleware is not registered.

## What ships in this change

A small helper in `expert_backend/main.py`:

```python
_GZIP_MIN_BYTES = 10_000
_GZIP_LEVEL = 5

def _maybe_gzip_json(payload, request: Request) -> Response:
    data = jsonable_encoder(payload)
    body = json_module.dumps(data, separators=(",", ":"),
                             ensure_ascii=False).encode("utf-8")
    accept = request.headers.get("accept-encoding", "")
    if len(body) < _GZIP_MIN_BYTES or "gzip" not in accept.lower():
        return Response(content=body, media_type="application/json",
                        headers={"Vary": "Accept-Encoding"})
    compressed = gzip.compress(body, compresslevel=_GZIP_LEVEL)
    return Response(content=compressed, media_type="application/json",
                    headers={"Content-Encoding": "gzip",
                             "Vary": "Accept-Encoding"})
```

Design choices:

- **`Accept-Encoding`-aware** — if the client doesn't send `gzip` the
  helper returns plain JSON. Existing TestClient-based integration tests
  don't send `Accept-Encoding: gzip` by default, so they exercise the
  unchanged wire format. Real browsers always send gzip, so production
  hits the fast path.
- **`minimum_size = 10 kB`** — compression is a pure cost for small
  payloads (a few hundred bytes of config JSON); we only pay it when
  it pays back.
- **`compresslevel = 5`** — on the 28 MB N-1 payload this is ~same ratio
  as level 9 but ~3× faster on the server. Measured locally, compressing
  a representative French 400 kV N-1 diagram: 28 MB → ~2.5 MB in ~120 ms
  at level 5 vs ~370 ms at level 9.
- **`Vary: Accept-Encoding`** — correct for any caching layer (proxies,
  CDNs) so they don't serve a gzipped body to an identity-only client or
  vice-versa.

## Endpoints wrapped

All three large-SVG endpoints from the traces, plus the related SLD /
focused / actions endpoints that share the same payload shape:

| Endpoint | Purpose | Typical decoded size |
|---|---|---|
| `GET  /api/network-diagram` | N-state NAD | ~24 MB |
| `POST /api/n1-diagram` | N-1 NAD | ~28 MB |
| `POST /api/action-variant-diagram` | post-action NAD | ~27 MB |
| `POST /api/focused-diagram` | VL-scoped NAD | ~200–2000 kB |
| `POST /api/action-variant-focused-diagram` | VL-scoped post-action NAD | ~200–2000 kB |
| `POST /api/n-sld` | N-state SLD | ~50–300 kB |
| `POST /api/n1-sld` | N-1 SLD | ~50–300 kB |
| `POST /api/action-variant-sld` | post-action SLD | ~50–300 kB |
| `GET  /api/actions` | action-id + description list | ~2.7 MB |

Each endpoint's handler gained an `http_request: Request` parameter and
returns `_maybe_gzip_json(payload, http_request)` instead of the bare
dict. No payload shape changes.

## Endpoints intentionally NOT wrapped

- **`POST /api/run-analysis`** and **`POST /api/run-analysis-step2`** —
  these return `StreamingResponse(application/x-ndjson)` and MUST keep
  flushing one event per line. They are left on FastAPI's default
  response path; the helper is only invoked from non-streaming endpoints.
- **`/results/pdf/*`** (PDF download via `StaticFiles`) — PDFs are
  already compressed internally; gzipping them is pure CPU waste.
- Small JSON endpoints (config, branches, voltage levels, pick-path,
  etc.) — they never cross the 10 kB threshold, so even if wrapped they
  wouldn't trigger compression. Leaving them on FastAPI's default flow
  keeps the diff surgical.

## Tests

A new `TestDiagramGzipCompression` class in
`expert_backend/tests/test_api_endpoints.py` locks in the behaviour:

- gzip-wrapped path returns `Content-Encoding: gzip` on the three big
  endpoints when the client sends `Accept-Encoding: gzip`.
- identity path returns no `Content-Encoding: gzip` when the client
  advertises `Accept-Encoding: identity`.
- small payloads (below `_GZIP_MIN_BYTES`) are never gzipped even when
  gzip is accepted.
- **`/api/run-analysis-step2`** stays on `application/x-ndjson` with no
  `Content-Encoding: gzip` even when the client asks for gzip, and its
  two NDJSON events are delivered in order (pdf first, result second).

This last test is the regression guard against the prior
global-middleware failure mode.

## Expected wire-time impact

On the N-1 trace captured earlier, the `/api/n1-diagram` XHR took
**~7.6 s wall-clock** for ~28 MB of payload (server side is the dominant
portion — pypowsybl NAD generation). With gzip, the payload on the wire
drops to ~2.5 MB, so the transfer + browser `ParseHTML`/JSON-parse time
on the client drops proportionally. Rough breakdown of the 7.6 s:

- Server compute (pypowsybl): ~6.3 s — unchanged
- Server compress (new, level 5): +~0.12 s
- Network transfer + client decompress + parse: was ~1 s on localhost,
  now ~0.2 s

On localhost the savings are modest (~600–700 ms) because loopback is
essentially free. Off-box (a real deployment) the same change typically
buys 2–5 s per call at ordinary LAN speeds.

The change does NOT affect `totalObjects`, Layout, Paint or any of the
frontend rendering metrics — those are floored by the one-remaining
200 k-node active-tab SVG, which is the target of step 4 (server-side
SVG slimming).
