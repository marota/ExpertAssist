# Lossless server-side SVG slimming (Step 4)

## Context

After steps 1–3, the remaining floor on every user-visible path is the
active-tab SVG itself. On the PyPSA-EUR France 400 kV grid:

- Raw SVG size per NAD: ~9.7–27 MB
- Decoded SVG element count: ~155 000
- Client-side work still bounded by parsing this one-remaining SVG string
  and walking its DOM (Paint ~5 s on the action path, ~2.6 s on N-1)

Step 2 (per-endpoint gzip) attacked wire bytes; step 4 attacks **raw
decoded bytes** — what the browser actually has to `JSON.parse` +
`DOMParser` on the main thread, regardless of transport compression.

## What "slimming" means here

Two pure string rewrites applied to the SVG **after** NaN stripping and
**before** the JSON response is built. Each is a local substitution that
preserves the visual output byte-for-byte at the rendered pixel level:

### 1. Fold `style="text-anchor:end"` into a class

Repeating inline attribute on ~10 000 `<text>` elements in a large NAD
(2.5 % of raw bytes on the reference 9.7 MB sample). Folded into a
single `.nad-te{text-anchor:end}` rule injected into the existing
`<style>` block, and the inline attribute rewritten as
`class="<existing-classes> nad-te"` to preserve the original class list.

The fold is **skipped entirely** if the SVG has no `</style>` tag (no
place to inject the rule) — converting the inline styles to a class
without the class definition would change rendering, so we'd rather
leave the SVG unchanged.

### 2. Strip trailing zeros from decimal fractions

`321345.0` → `321345`, `120.50` → `120.5`, `0.050` → `0.05`. The
transform targets only numeric tokens terminated by `,` / whitespace /
`)` / `"` — the delimiters used inside `points=`, `d=`, `transform=`,
`cx=`, `cy=`, `x=`, `y=`, etc. CSS values (`-1995685px`), hex colors
(`#FFFFFFAA`) and attribute names are never touched.

This is strictly lossless: trailing zeros on a decimal fraction carry no
numeric information. `321345.0` and `321345` parse to the same float.

## What is NOT done (and why)

- **Round to integer / truncate decimals**: would be visually lossless
  at the sub-pixel level (the reference grid viewBox is 1.6 M × 1.3 M
  units; 1 unit ≈ 0.0005 px on an 800 px viewport) but introduces any
  deviation from the source coordinate. Kept off for now.
- **Remove `<title>`/`<desc>`/`<metadata>`**: pypowsybl NAD output on
  the reference grid contains zero of these. No-op.
- **Element pruning (low-voltage filter, voltage-bound)**: already
  rejected upstream in `docs/nad_optimization.md` — 11 % gain for risk
  of hiding critical weak components.
- **Whitespace minification**: pypowsybl output already has no
  inter-tag whitespace.

## Files

| File | Role |
|---|---|
| `expert_backend/services/svg_slim.py` | `slim_svg(svg: str) -> str` — the two transforms, compiled regexes |
| `expert_backend/services/diagram_mixin.py` | Calls `slim_svg` at the end of `_generate_diagram`, logs `before -> after` byte count and duration |
| `expert_backend/tests/test_svg_slim.py` | 19 unit tests: trailing-zero cases, text-anchor fold in each attribute-order, CSS injection idempotence, edge cases, idempotence of double-slim, combined realistic NAD snippet |

## Measured impact

Benchmarked against the representative **9.7 MB N-1 NAD** (extracted
from commit `26bc49d`, PyPSA-EUR France 400 kV, contingency
`ARGIAL71CANTE`):

| | raw | slimmed | Δ |
|---|---|---|---|
| Bytes (decoded) | 9 718 700 | **9 441 264** | **-2.85 % (-277 KB)** |
| Bytes (gzip level 5) | 1 511 679 | **1 482 847** | -1.91 % (-29 KB) |
| XML element count | 155 120 | 155 120 | 0 (attribute-only) |
| XML parses cleanly | ✓ | ✓ | — |
| Slim time | n/a | **241 ms** | +<5 % of pypowsybl's 5-7 s |

On the bigger **27.7 MB** N-1 NADs seen on v1-v3 traces, the proportional
savings scale: ~0.8 MB off the decoded JSON body per call, which is
what the browser actually parses on the main thread.

### Why the gzip delta is smaller than the raw delta

Gzip already encodes the 10 000 repeating `style="text-anchor:end"`
strings efficiently — they're high-entropy redundancy by definition.
Trailing `.0` tokens are similarly compressible. The 277 KB raw
reduction compresses down to 29 KB on the wire because the repetition
has already been factored out by deflate.

What DOES move is the **browser-side work**:

- `JSON.parse` cost scales with decoded string length → -277 KB to parse
- SVG `DOMParser` cost similarly linear in input size
- Peak memory pressure during decode drops by the same delta
- 10 000 fewer `style="..."` attribute nodes for Blink to attach

These are unaffected by gzip. That's what step 4 buys that step 2 can't.

## Observability

`diagram_mixin._generate_diagram` logs a line like:

```
[RECO] SVG slimmed: 9718700 -> 9441264 bytes (-2.9%, 0.24s)
```

after every NAD generation. If a future pypowsybl version changes the
inline-style patterns or coordinate format, the log makes regressions
visible immediately.

## Interaction with earlier steps

| Step | Layer | Interaction |
|---|---|---|
| 1 (`display:none` inactive tabs) | Browser | Independent. Slim doesn't affect `totalObjects` counts. |
| 2 (per-endpoint gzip) | Wire | Complementary. Slim shrinks the input; gzip then compresses it further. No stacking conflict. |
| 3 (not yet shipped — streaming action variant) | Backend | Independent. |
| 4 (this change) | Decoded bytes | Compounds with step 2 on the decoded side. |

## What's still on the table

The hard floor for "big SVG" performance is now the element count
itself (155 k elements). Further wins need one of:

- **Element-level pruning** — already investigated and rejected
  (`docs/nad_optimization.md` strategies 1 & 3).
- **Canvas / WebGL renderer** — fundamentally different architecture.
  No pypowsybl support today.
- **Viewport-aware DOM culling** (`docs/network_rendering_profiling_recommendations.md`
  Layer 2) — client-side `display:none` on off-viewport elements.
  ~5× Paint reduction when zoomed in, zero when zoomed out.

Step 4 is the last cheap/safe lever on the server side; any future
wins are architectural.
