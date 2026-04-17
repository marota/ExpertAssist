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

One pure string rewrite applied to the SVG **after** NaN stripping and
**before** the JSON response is built, preserving the visual output
byte-for-byte at the rendered pixel level:

### Strip trailing zeros from decimal fractions

`321345.0` → `321345`, `120.50` → `120.5`, `0.050` → `0.05`. The
transform targets only numeric tokens terminated by `,` / whitespace /
`)` / `"` — the delimiters used inside `points=`, `d=`, `transform=`,
`cx=`, `cy=`, `x=`, `y=`, etc. CSS values (`-1995685px`), hex colors
(`#FFFFFFAA`) and attribute names are never touched.

This is strictly lossless: trailing zeros on a decimal fraction carry no
numeric information. `321345.0` and `321345` parse to the same float.

## What is NOT done (and why)

- **Fold `style="text-anchor:end"` into a CSS class** — tried and
  reverted; see the "v3 → v4 regression" section below for the measured
  failure. Pypowsybl emits ~10 000 of these inline styles on large NADs
  and folding them into a single class rule caused Blink to do full
  selector matching on every `<text>` element on every style recalc,
  regressing Paint by +60 to +91 % despite saving ~176 KB raw bytes.
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
| `expert_backend/services/svg_slim.py` | `slim_svg(svg: str) -> str` — the trailing-zero transform, one compiled regex |
| `expert_backend/services/diagram_mixin.py` | Calls `slim_svg` at the end of `_generate_diagram`, logs `before -> after` byte count and duration |
| `expert_backend/tests/test_svg_slim.py` | Unit tests: trailing-zero cases, guard that text-anchor styles are NOT folded, edge cases, idempotence, representative NAD snippet |

## Measured impact

Benchmarked against the representative **9.7 MB N-1 NAD** (extracted
from commit `26bc49d`, PyPSA-EUR France 400 kV, contingency
`ARGIAL71CANTE`):

| | raw | slimmed | Δ |
|---|---|---|---|
| Bytes (decoded) | 9 718 700 | **9 534 264** | **-1.90 % (-184 KB)** |
| Bytes (gzip level 5) | 1 511 679 | **1 484 150** | -1.82 % (-27 KB) |
| XML element count | 155 120 | 155 120 | 0 (attribute-only) |
| XML parses cleanly | ✓ | ✓ | — |
| Slim time | n/a | **205 ms** | +<5 % of pypowsybl's 5-7 s |

On the bigger **27 MB** N-1 NADs seen in v1-v3 traces, the proportional
savings scale: ~500 KB off the decoded JSON body per call, which is what
the browser actually parses on the main thread.

## v3 → v4 regression (and the fix)

The first version of this step also folded the ~10 000 inline
`style="text-anchor:end"` attributes on `<text>` elements into a single
`.nad-te{text-anchor:end}` CSS-class rule injected into the existing
`<style>` block. On the 9.7 MB reference sample this saved an extra
~93 KB raw, bringing the total slim delta to -2.85 %.

The v4 production traces measured the full effect on the browser:

| Scenario | Metric | v3 (step 1+2) | v4 (with fold) | Δ |
|---|---|---|---|---|
| N-1 | Long tasks total | 9 404 ms | **13 283 ms** | **+41 %** |
| N-1 | Paint total | 2 588 ms | **4 140 ms** | **+60 %** |
| N-1 | Layerize total | 2 626 ms | 3 709 ms | +41 % |
| Action | Long tasks total | 13 957 ms | **19 587 ms** | **+40 %** |
| Action | Paint total | 5 335 ms | **10 201 ms** | **+91 %** |
| Action | Layerize total | 3 893 ms | 5 692 ms | +46 % |

Decoded size was indeed down 461 KB as designed, but Paint roughly
**doubled** on the manual-action path.

### Root cause

Each inline `style="text-anchor:end"` carries the property locally on
its element — Blink reads it in O(1) during style resolution. Replacing
10 000+ inline styles with a single CSS-class rule forces Blink into
full selector matching mode: every text element in the NAD is tested
against every rule in the `<style>` block (pypowsybl emits ~25 rules)
on every style recalc. That cost scales as `elements × rules`, and on
the reference French 400 kV N-1 NAD it dominates the Paint budget.

The gzip win from the fold is additionally tiny: the 10 000 repeating
inline-style strings are already the kind of redundancy deflate
compresses ~100:1. On-wire savings from the fold were ~10 KB out of
2.8 MB gzipped — well below measurement noise.

### Decision

The fold was reverted in a follow-up commit. The slimmer now does only
trailing-zero stripping. Tests
`TestTextAnchorStylesArePreserved::test_standalone_inline_style_kept`,
`test_class_and_style_both_preserved` and
`test_no_duplicate_class_attribute_on_any_tag` guard against the fold
being reintroduced.

The slim time also dropped from **510 ms to 205 ms** (the fold's
three-regex sweep over the full SVG was the main cost).

## Why the gzip delta stays small

Gzip already encodes numeric tokens efficiently — trailing `.0` patterns
are compressible too. The 184 KB raw reduction compresses down to 27 KB
on the wire because deflate already factored out most of the redundancy.

What DOES move is the **browser-side work**:

- `JSON.parse` cost scales with decoded string length → -184 KB to parse
- SVG `DOMParser` cost similarly linear in input size
- Peak memory pressure during decode drops by the same delta

These are unaffected by gzip. That's what step 4 buys that step 2 can't.

## Observability

`diagram_mixin._generate_diagram` logs a line like:

```
[RECO] SVG slimmed: 9718700 -> 9534264 bytes (-1.9%, 0.21s)
```

after every NAD generation. If a future pypowsybl version changes the
coordinate format, the log surfaces regressions immediately.

## Interaction with earlier steps

| Step | Layer | Interaction |
|---|---|---|
| 1 (`display:none` inactive tabs) | Browser | Independent. Slim doesn't affect `totalObjects` counts. |
| 2 (per-endpoint gzip) | Wire | Complementary. Slim shrinks the input; gzip then compresses it further. No stacking conflict. |
| 3 (not yet shipped — streaming action variant) | Backend | Independent. |
| 4 (this change) | Decoded bytes | Compounds with step 2 on the decoded side, modestly. |

## What's still on the table

The hard floor for "big SVG" performance is now the element count
itself (155 k elements) and the inline-style attribute count
(pypowsybl's normal output). Further wins need one of:

- **Upstream pypowsybl change** — ship rules with classes from
  generation time rather than emitting inline styles. That would make
  a client-side fold cheap (the matching cost is still there but amortised
  over the same number of rules).
- **Element-level pruning** — already investigated and rejected
  (`docs/nad_optimization.md` strategies 1 & 3).
- **Canvas / WebGL renderer** — fundamentally different architecture.
  No pypowsybl support today.
- **Viewport-aware DOM culling** (`docs/network_rendering_profiling_recommendations.md`
  Layer 2) — client-side `display:none` on off-viewport elements.
  ~5× Paint reduction when zoomed in, zero when zoomed out.

Step 4 is the last cheap/safe lever on the server side; any further
wins are architectural.
