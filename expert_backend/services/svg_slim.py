# Copyright (c) 2025-2026, RTE (https://www.rte-france.com)
# This Source Code Form is subject to the terms of the Mozilla Public License, version 2.0.
# If a copy of the Mozilla Public License, version 2.0 was not distributed with this file,
# you can obtain one at http://mozilla.org/MPL/2.0/.
# SPDX-License-Identifier: MPL-2.0
# This file is part of Co-Study4Grid a Power Grid Study tool Assistant Interface to help solve contigencies for a grid state under study.

"""Lossless SVG size reduction for large pypowsybl NAD outputs.

Currently a single pure string rewrite verified on representative 9.7 MB
French 400 kV N-1 NADs to preserve visual output:

- Strip trailing zeros from decimal fractions in numeric literals
  (e.g. `321345.0` -> `321345`, `120.50` -> `120.5`). pypowsybl emits
  coordinates at ~1/1.6M of the viewport width for the grids we target,
  so these tokens are already sub-pixel and the value is unchanged.
  Only the serialized representation shrinks.

## Rejected: folding `style="text-anchor:end"` into a CSS class

An earlier version of this file also folded the ~10 k inline
`style="text-anchor:end"` attributes on `<text>` nodes into a shared
`.nad-te` class injected into the existing `<style>` block. That saved
about 2 % additional raw bytes on the reference 9.7 MB NAD.

In practice the fold was a NET LOSS in browser-side work: replacing
10 000+ local inline styles with a single CSS-class rule forced Blink
to do full CSS-selector matching for each text element against every
rule in the NAD's `<style>` block on every style recalc. On the
reference French 400 kV grid this increased:

  - Paint total     +60 %  (N-1)   /  +91 %  (action variant)
  - Layerize total  +41 %  (N-1)   /  +46 %  (action variant)
  - Long tasks      +41 %  (N-1)   /  +40 %  (action variant)

The byte win (~176 KB raw, ~10 KB after gzip) is dwarfed by the
browser-side cost. See the "v3 -> v4" rows in `docs/perf-svg-slimming.md`
for the measured regression; the fold was removed in favour of keeping
the pypowsybl inline styles as-is.
"""

from __future__ import annotations

import re


# Match a numeric fraction (".<digits>") immediately followed by a
# delimiter that terminates a numeric token. We deliberately REQUIRE a
# preceding digit via a lookbehind so we never match inside attribute
# names, css property names, or negative-number contexts like `-.5`
# (which are treated as `0.5` numerically but don't appear in pypowsybl
# output anyway).
#
# The inner group captures the non-trailing-zero portion: empty string
# when the whole fraction is zeros (`.0`, `.00`), or the leading non-
# zero suffix (`.50` -> `.5`, `.120` -> `.12`). Trailing zeros after
# the captured portion are consumed by the `0+` quantifier.
_RE_TRAILING_ZEROS = re.compile(r'(?<=\d)\.(\d*?)0+(?=[,\s)"])')

def slim_svg(svg: str) -> str:
    """Return a byte-reduced but visually identical copy of ``svg``.

    Safe for empty / non-SVG strings (they are returned unchanged).
    Callers should treat this as best-effort: if the transform fails
    mid-string the remainder of the file is still well-formed because
    each rewrite is a local substitution.
    """
    if not svg:
        return svg

    # Trim trailing zeros from decimal fractions inside numeric tokens.
    # `.0` / `.00` etc. become '' (dot stripped with zeros);
    # `.50` becomes `.5`; `.5` is left alone (no trailing zeros).
    def _trim(m: re.Match[str]) -> str:
        frac = m.group(1)
        return ('.' + frac) if frac else ''

    return _RE_TRAILING_ZEROS.sub(_trim, svg)
