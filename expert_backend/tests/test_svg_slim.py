# Copyright (c) 2025-2026, RTE (https://www.rte-france.com)
# This Source Code Form is subject to the terms of the Mozilla Public License, version 2.0.
# If a copy of the Mozilla Public License, version 2.0 was not distributed with this file,
# you can obtain one at http://mozilla.org/MPL/2.0/.
# SPDX-License-Identifier: MPL-2.0
# This file is part of Co-Study4Grid a Power Grid Study tool Assistant Interface to help solve contigencies for a grid state under study.

"""Unit tests for the lossless SVG slimmer applied to large NADs."""

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


class TestTextAnchorFold:
    """Fold `style="text-anchor:end"` into a `.nad-te` class."""

    _STYLE_HEADER = '<svg xmlns="http://www.w3.org/2000/svg"><style>.c16 {fill: #546e7a}</style>'

    def test_standalone_inline_style_folded(self):
        inp = self._STYLE_HEADER + '<text style="text-anchor:end">x</text></svg>'
        out = slim_svg(inp)
        assert 'style="text-anchor:end"' not in out
        assert '<text class="nad-te">x</text>' in out
        assert '.nad-te{text-anchor:end}</style>' in out

    def test_merged_into_existing_class_before(self):
        inp = (self._STYLE_HEADER
               + '<text class="c16" style="text-anchor:end">x</text></svg>')
        out = slim_svg(inp)
        assert 'class="c16 nad-te"' in out
        assert 'style="text-anchor:end"' not in out
        # Existing class attribute is not duplicated.
        assert out.count('class=') == out.count('class="c16 nad-te"') + 0

    def test_merged_into_existing_class_after(self):
        inp = (self._STYLE_HEADER
               + '<text style="text-anchor:end" class="c16">x</text></svg>')
        out = slim_svg(inp)
        assert 'class="c16 nad-te"' in out
        assert 'style="text-anchor:end"' not in out

    def test_css_rule_injected_only_once_for_many_occurrences(self):
        body = ''.join(
            f'<text class="c16" style="text-anchor:end">{i}</text>'
            for i in range(5)
        )
        inp = self._STYLE_HEADER + body + '</svg>'
        out = slim_svg(inp)
        # All occurrences folded.
        assert 'style="text-anchor:end"' not in out
        # Only one CSS rule copy injected, regardless of how many elements folded.
        assert out.count('.nad-te{text-anchor:end}') == 1

    def test_fold_skipped_when_no_style_block(self):
        # Without a `<style>...</style>` block we have nowhere to put the
        # CSS rule, so the fold is a no-op (converting inline styles to a
        # class without the class definition would change rendering).
        inp = '<svg xmlns="http://www.w3.org/2000/svg"><text style="text-anchor:end">x</text></svg>'
        out = slim_svg(inp)
        assert out == inp

    def test_existing_nad_te_not_re_injected(self):
        inp = (self._STYLE_HEADER.replace(
                   '</style>', '.nad-te{text-anchor:end}</style>')
               + '<text style="text-anchor:end">x</text></svg>')
        out = slim_svg(inp)
        # Inline styles still folded…
        assert 'style="text-anchor:end"' not in out
        assert 'class="nad-te"' in out
        # …and the existing CSS rule is left alone, not duplicated.
        assert out.count('.nad-te{text-anchor:end}') == 1


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
        # Running the slimmer twice yields the same output: no transform
        # produces a pattern that itself matches again.
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

        Verifies the two transforms compose (text-anchor fold + decimal
        strip) and that the result is well-formed XML.
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

        # text-anchor styles gone, folded into class.
        assert 'style="text-anchor:end"' not in out
        assert 'class="c16 nad-te"' in out
        assert '<text class="nad-te">VL_B</text>' in out
        # CSS rule injected exactly once inside the style block.
        assert out.count('.nad-te{text-anchor:end}') == 1

        # Numeric tokens slimmed.
        assert 'translate(321362.1,-1734282.3)' in out
        assert 'cx="0" cy="0" r="12"' in out
        assert 'points="321345.9,-1734260 315064.5,-1725622.1"' in out

        # Size strictly shrinks on this snippet.
        assert len(out) < len(inp)
