# Copyright (c) 2025-2026, RTE (https://www.rte-france.com)
# This Source Code Form is subject to the terms of the Mozilla Public License, version 2.0.
# If a copy of the Mozilla Public License, version 2.0 was not distributed with this file,
# you can obtain one at http://mozilla.org/MPL/2.0/.
# SPDX-License-Identifier: MPL-2.0
# This file is part of Co-Study4Grid a Power Grid Study tool Assistant Interface to help solve contigencies for a grid state under study.

"""Lossless SVG size reduction for large pypowsybl NAD outputs.

Two pure string rewrites, each verified on representative 9.7 MB French
400 kV N-1 NADs to preserve visual output:

1. Fold the ~10 k inline `style="text-anchor:end"` attributes (~2.5 %
   of the raw file on large grids) into a single CSS class
   `nad-te` rule injected into the existing `<style>` block. When the
   element already has a `class="..."` attribute, we append to it rather
   than emitting a duplicate attribute.

2. Strip trailing zeros from decimal fractions in numeric literals
   (e.g. `321345.0` -> `321345`, `120.50` -> `120.5`). pypowsybl emits
   coordinates at ~1/1.6M of the viewport width for the grids we target,
   so these tokens are already sub-pixel and the value is unchanged. Only
   the serialized representation shrinks.

Combined savings on a representative 9.7 MB N-1 NAD: ~7-8 % raw bytes,
compounding with the existing per-endpoint gzip to give a further
reduction on the wire and in client-side parse / paint time.
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

# Inline-style fold: three variants to cover every order-of-attribute
# combination pypowsybl is known to emit. Each variant merges the
# text-anchor style into the element's class list rather than replacing
# an existing class attribute (which would be malformed XML:
# "Attribute class redefined").
#
# The BEFORE / AFTER variants tolerate ANY intervening attributes between
# class="..." and style="text-anchor:end" as long as both live inside the
# SAME element start tag. The `[^<>]*?` group excludes `<` and `>` so it
# cannot span tag boundaries, and the leading `\s+` anchors the match to
# an attribute boundary (not a style substring inside text content). The
# STANDALONE fallback is only safe when BOTH previous regexes have
# already consumed every class-adjacent occurrence on the same tag —
# otherwise it would blindly add a second `class="..."` attribute to an
# element that already has one.
_TE_CLASS = 'nad-te'
_TE_CSS_RULE = f'.{_TE_CLASS}{{text-anchor:end}}'
_RE_TE_CLASS_BEFORE = re.compile(
    r'class="([^"]*)"([^<>]*?)\s+style="text-anchor:end"'
)
_RE_TE_CLASS_AFTER = re.compile(
    r'\s+style="text-anchor:end"([^<>]*?)class="([^"]*)"'
)
_RE_TE_STANDALONE = re.compile(r'\s+style="text-anchor:end"')

# Style-block closer; the fold's CSS rule is injected immediately before
# `</style>` so it sits inside any `<![CDATA[...]]>` wrapper without us
# needing to know whether one is present.
_RE_STYLE_CLOSE = re.compile(r'</style>')


def slim_svg(svg: str) -> str:
    """Return a byte-reduced but visually identical copy of ``svg``.

    Safe for empty / non-SVG strings (they are returned unchanged).
    Callers should treat this as best-effort: if any transform fails
    mid-string the remainder of the file is still well-formed because
    each rewrite is a local substitution.
    """
    if not svg:
        return svg

    out = svg

    # 1. Fold inline `text-anchor:end` only when we can also inject the
    # matching CSS rule. If there's no `</style>` tag in the document we
    # skip the fold entirely — converting inline styles to a class
    # without the class definition would change visual output.
    if _RE_STYLE_CLOSE.search(out):

        def _append_before(m: re.Match[str]) -> str:
            # class="X" ...attrs... style="text-anchor:end"
            #   -> class="X nad-te" ...attrs...
            return f'class="{m.group(1)} {_TE_CLASS}"{m.group(2)}'

        def _append_after(m: re.Match[str]) -> str:
            # " style="text-anchor:end" ...attrs... class="X""
            #   -> " ...attrs... class="X nad-te""
            return f'{m.group(1)}class="{m.group(2)} {_TE_CLASS}"'

        out, n1 = _RE_TE_CLASS_BEFORE.subn(_append_before, out)
        out, n2 = _RE_TE_CLASS_AFTER.subn(_append_after, out)
        # Remaining standalone occurrences: we've already consumed every
        # class-adjacent case, so anything left has no class attribute in
        # the same tag and it's safe to synthesize one.
        out, n3 = _RE_TE_STANDALONE.subn(f' class="{_TE_CLASS}"', out)

        # Inject the CSS rule exactly once, right before `</style>`.
        # Done after the folds so the total count of folds tells us
        # whether the rule is worth injecting at all.
        if (n1 + n2 + n3) > 0 and _TE_CSS_RULE not in out:
            out = _RE_STYLE_CLOSE.sub(_TE_CSS_RULE + '</style>', out, count=1)

    # 2. Trim trailing zeros from decimal fractions inside numeric
    # tokens. `.0` / `.00` etc. become '' (dot stripped with zeros);
    # `.50` becomes `.5`; `.5` is left alone (no trailing zeros).
    def _trim(m: re.Match[str]) -> str:
        frac = m.group(1)
        return ('.' + frac) if frac else ''

    out = _RE_TRAILING_ZEROS.sub(_trim, out)

    return out
