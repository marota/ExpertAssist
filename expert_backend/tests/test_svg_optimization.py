# Copyright (c) 2025-2026, RTE (https://www.rte-france.com)
# This Source Code Form is subject to the terms of the Mozilla Public License, version 2.0.
# SPDX-License-Identifier: MPL-2.0

import pytest
from expert_backend.services.recommender_service import RecommenderService

class TestSvgOptimization:
    def test_flatten_svg_single_child(self):
        service = RecommenderService()
        # A group with a single child should be flattened
        svg_input = """
        <svg xmlns="http://www.w3.org/2000/svg">
            <g transform="translate(10,20)" class="parent">
                <circle cx="0" cy="0" r="5" fill="red" class="child" />
            </g>
        </svg>
        """
        optimized = service._optimize_svg(svg_input)
        
        # The <g> should be gone, and its attributes merged into <circle>
        assert "<g" not in optimized
        assert '<circle cx="0" cy="0" r="5" fill="red"' in optimized
        assert 'class="parent child"' in optimized
        assert 'transform="translate(10,20)"' in optimized

    def test_flatten_svg_nested_single_child(self):
        service = RecommenderService()
        svg_input = """
        <svg xmlns="http://www.w3.org/2000/svg">
            <g transform="translate(10,20)">
                <g transform="scale(2)">
                    <rect x="0" y="0" width="10" height="10" />
                </g>
            </g>
        </svg>
        """
        optimized = service._optimize_svg(svg_input)
        
        assert "<g" not in optimized
        # Transforms should be concatenated
        assert 'transform="translate(10,20) scale(2)"' in optimized or 'transform="scale(2) translate(10,20)"' in optimized

    def test_class_minification(self):
        service = RecommenderService()
        svg_input = """
        <svg xmlns="http://www.w3.org/2000/svg">
            <style>
                .nad-vl300to500 { stroke: blue; }
                .nad-busnode { fill: black; }
                .nad-overloaded { stroke: red; }
            </style>
            <g class="nad-vl300to500">
                <circle class="nad-busnode" />
                <path class="nad-overloaded" />
            </g>
        </svg>
        """
        optimized = service._optimize_svg(svg_input)
        
        # Repetitive classes should be shortened
        assert "nad-vl300to500" not in optimized
        assert "nad-busnode" not in optimized
        
        # Protected class should REMAIN
        assert "nad-overloaded" in optimized
        
        # Check that style block was updated with numeric codes (c0, c1, etc.)
        assert ".c0" in optimized or ".c1" in optimized

    def test_nan_stripping(self):
        service = RecommenderService()
        # Elements with NaN in attributes should be removed
        svg_input = """
        <svg xmlns="http://www.w3.org/2000/svg">
            <circle cx="NaN" cy="10" r="5" />
            <path d="M 0 0 L NaN 10" />
            <rect x="10" y="10" width="10" height="10" />
        </svg>
        """
        optimized = service._optimize_svg(svg_input)
        
        assert "<circle" not in optimized
        assert "<path" not in optimized
        assert "<rect" in optimized

    def test_precision_reduction(self):
        service = RecommenderService()
        svg_input = """
        <svg xmlns="http://www.w3.org/2000/svg">
            <circle cx="123.45678" cy="987.65432" r="5" />
            <g transform="translate(10.1234, 20.5678)">
                <path d="M 1.1111 2.2222" />
            </g>
        </svg>
        """
        optimized = service._optimize_svg(svg_input)
        
        # Should be rounded to 1 decimal place
        assert 'cx="123.5"' in optimized
        assert 'cy="987.7"' in optimized
        assert 'translate(10.1, 20.6)' in optimized
        assert 'd="M 1.1 2.2"' in optimized

class TestMetadataOptimization:
    def test_prune_metadata(self):
        service = RecommenderService()
        meta = {
            "nodes": [
                {"equipmentId": "N1", "x": 100.123, "y": 200.456},
                {"equipmentId": "N2", "x": 300, "y": 400}
            ],
            "edges": [
                {
                    "equipmentId": "E1",
                    "edgeInfo1": {"svgId": "i1", "x": 10, "y": 20, "vlNode": "81"},
                    "edgeInfo2": {"svgId": "i2", "x": 30, "y": 40, "vlNode": "82"}
                }
            ]
        }
        
        pruned = service._prune_metadata(meta)
        
        # Node coordinates should be rounded
        assert pruned["nodes"][0]["x"] == 100.1
        assert pruned["nodes"][0]["y"] == 200.5
        
        # EdgeInfo should be pruned
        info1 = pruned["edges"][0]["edgeInfo1"]
        assert "svgId" in info1
        assert "x" not in info1
        assert "y" not in info1
        assert "vlNode" not in info1

    def test_id_preservation_during_flattening(self):
        """Test that id attribute is moved from flattened group to child."""
        svg = """
        <svg xmlns="http://www.w3.org/2000/svg">
            <g id="parent-id" transform="translate(10,20)">
                <circle cx="0" cy="0" r="5" class="node-class"/>
            </g>
        </svg>
        """
        service = RecommenderService()
        optimized = service._optimize_svg(svg)
        
        # The <g> should be gone, and <circle> should have the id and transform
        assert '<g' not in optimized
        assert 'id="parent-id"' in optimized
        assert 'transform="translate(10,20)"' in optimized
        assert 'class="node-class"' in optimized

    def test_id_collision_precedence(self):
        """Test that child id is preserved if both parent and child have one."""
        svg = """
        <svg xmlns="http://www.w3.org/2000/svg">
            <g id="parent-id">
                <circle id="child-id" cx="0" cy="0" r="5"/>
            </g>
        </svg>
        """
        service = RecommenderService()
        optimized = service._optimize_svg(svg)
        # Should NOT overwrite child-id
        assert 'id="child-id"' in optimized
        assert 'id="parent-id"' not in optimized
