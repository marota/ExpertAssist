# Copyright (c) 2025-2026, RTE (https://www.rte-france.com)
# This Source Code Form is subject to the terms of the Mozilla Public License, version 2.0.
# If a copy of the Mozilla Public License, version 2.0 was not distributed with this file,
# you can obtain one at http://mozilla.org/MPL/2.0/.
# SPDX-License-Identifier: MPL-2.0
# This file is part of Co-Study4Grid a Power Grid Study tool Assistant Interface to help solve contigencies for a grid state under study.

"""Unit tests for the lossless SVG slimmer applied to large NADs."""

import re

import pytest

from expert_backend.services.svg_slim import slim_svg


class TestTrailingZeroStripping:
    """Trailing-zero stripping on decimal fractions — purely lossless."""

    @pytest.mark.parametrize("inp,expected", [
        # .0 / .00 forms — strip entirely including the dot
        ('<polyline points="321345.0,-1734260.0"/>',
         '<polyline points="321345,-1734260"/>'),
        ('<g transform="translate(321362.00,-1734282.000)"/>',
         '<g transform="translate(321362,-1734282)"/>'),
        # mixed: trailing zeros after non-zero kept
        ('<polyline points="120.50,140.120"/>',
         '<polyline points="120.5,140.12"/>'),
        # non-zero fractions preserved
        ('<circle cx="120.5" cy="140.1"/>',
         '<circle cx="120.5" cy="140.1"/>'),
        # integers — untouched (no decimal point to begin with)
        ('<circle cx="120" cy="140"/>',
         '<circle cx="120" cy="140"/>'),
        # leading zeros after the dot are preserved (e.g. .05 != .5)
        ('<circle cx="0.050"/>',
         '<circle cx="0.05"/>'),
        # inside a comma-separated list: each fraction handled independently
        ('<polyline points="1.0,2.5 3.50,4.0"/>',
         '<polyline points="1,2.5 3.5,4"/>'),
        # negative numbers
        ('<g transform="translate(-1995685.0,-768981.500)"/>',
         '<g transform="translate(-1995685,-768981.5)"/>'),
    ])
    def test_trim_known_cases(self, inp, expected):
        assert slim_svg(inp) == expected

    def test_css_and_unit_values_are_not_touched(self):
        # CSS values with px suffix have a non-numeric separator already,
        # so `.0` inside them has no terminating delimiter of the kind the
        # regex requires — they stay unchanged. Same for hex colors etc.
        inp = '<div style="top:-1995685px;left:768981px">text</div>'
        assert slim_svg(inp) == inp
        inp2 = '<rect fill="#FFFFFFAA" stroke="black"/>'
        assert slim_svg(inp2) == inp2


class TestTextAnchorStylesArePreserved:
    """Inline `style="text-anchor:end"` must NOT be folded into a CSS class.

    An earlier version of the slimmer folded the ~10 k pypowsybl inline
    `text-anchor:end` styles into a single `.nad-te` CSS class + rule.
    On the reference French 400 kV N-1 NAD this caused Blink to do full
    CSS-selector matching on every `<text>` node on every style recalc,
    regressing Paint by +60 % on N-1 and +91 % on the action variant
    (see docs/perf-svg-slimming.md "v3 -> v4"). The fold was reverted;
    these tests guard against it being reintroduced.
    """

    _STYLE_HEADER = (
        '<svg xmlns="http://www.w3.org/2000/svg">'
        '<style>.c16 {fill: #546e7a}</style>'
    )

    def test_standalone_inline_style_kept(self):
        inp = self._STYLE_HEADER + '<text style="text-anchor:end">x</text></svg>'
        out = slim_svg(inp)
        # Inline style preserved verbatim; no class synthesized;
        # no CSS rule injected into the style block.
        assert 'style="text-anchor:end"' in out
        assert 'nad-te' not in out
        assert out == inp

    def test_class_and_style_both_preserved(self):
        inp = (self._STYLE_HEADER
               + '<text class="c16" style="text-anchor:end">x</text></svg>')
        out = slim_svg(inp)
        assert 'class="c16"' in out
        assert 'style="text-anchor:end"' in out
        assert 'nad-te' not in out
        assert out == inp

    def test_no_duplicate_class_attribute_on_any_tag(self):
        """Even if a future change re-introduces a text-anchor fold,
        it must never produce two `class="..."` attributes on the same
        element — that makes the browser refuse to render the SVG. The
        current implementation cannot produce this output (it never
        touches class= or style=), so the check is vacuous today, but
        it remains as a live guard against regressions.
        """
        inp = (self._STYLE_HEADER
               + '<text class="c16" x="10" y="20" style="text-anchor:end">a</text>'
               + '<text style="text-anchor:end" fill="red" class="c40">b</text>'
               + '</svg>')
        out = slim_svg(inp)
        for tag in re.finditer(r'<\w[^>]*>', out):
            assert tag.group(0).count('class="') <= 1, tag.group(0)


class TestEdgeCases:
    def test_empty_string(self):
        assert slim_svg('') == ''

    def test_none_safe_for_typed_callers(self):
        # We don't handle None explicitly, but the function is only
        # called from diagram_mixin._generate_diagram where the input is
        # always a non-empty string produced by pypowsybl. Still, a
        # bare-string check protects against accidental breakage.
        assert slim_svg('plain text') == 'plain text'

    def test_idempotent(self):
        # Running the slimmer twice yields the same output: the
        # trailing-zero transform cannot produce a pattern that itself
        # matches again.
        inp = (
            '<svg xmlns="http://www.w3.org/2000/svg"><style>.c16 {fill: #546e7a}</style>'
            '<text class="c16" style="text-anchor:end">x</text>'
            '<polyline points="321345.0,-1734260.50"/></svg>'
        )
        once = slim_svg(inp)
        twice = slim_svg(once)
        assert once == twice


class TestCombinedRealisticSnippet:
    def test_representative_nad_fragment(self):
        """A snippet shaped like real pypowsybl NAD output.

        Verifies that the trailing-zero strip is applied to every
        numeric context (viewBox, transform, cx/cy/r, points) while
        inline styles and class attributes are left entirely untouched.
        """
        inp = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="-137870.0 -2916920.0 1643872.0 1304459.0">'
            '<style><![CDATA[.c16 {fill: #546e7a}]]></style>'
            '<g class="nad-vl-nodes" transform="translate(321362.10,-1734282.300)">'
            '<circle cx="0.0" cy="0.0" r="12.0"/>'
            '<text class="c16" style="text-anchor:end">VL_A</text>'
            '<text style="text-anchor:end">VL_B</text>'
            '</g>'
            '<polyline points="321345.9,-1734260.0 315064.50,-1725622.10"/>'
            '</svg>'
        )
        out = slim_svg(inp)

        # Numeric tokens slimmed across every kind of attribute that
        # carries coordinates.
        assert 'viewBox="-137870 -2916920 1643872 1304459"' in out
        assert 'translate(321362.1,-1734282.3)' in out
        assert 'cx="0" cy="0" r="12"' in out
        assert 'points="321345.9,-1734260 315064.5,-1725622.1"' in out

        # Inline text-anchor styles and class attributes are preserved
        # byte-for-byte; no CSS rule was injected into the style block.
        assert 'class="c16"' in out
        assert '<text class="c16" style="text-anchor:end">VL_A</text>' in out
        assert '<text style="text-anchor:end">VL_B</text>' in out
        assert 'nad-te' not in out

        # Size strictly shrinks on this snippet.
        assert len(out) < len(inp)
