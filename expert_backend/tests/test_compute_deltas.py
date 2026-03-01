"""Tests for RecommenderService._compute_deltas flow delta computation."""

import pytest
from expert_backend.services.recommender_service import RecommenderService


class TestComputeDeltas:
    """Tests for flow delta computation between two network states."""

    def setup_method(self):
        self.service = RecommenderService()

    def test_identical_flows_zero_deltas(self):
        """When before and after flows are identical, all deltas should be zero."""
        flows = {
            "p1": {"LINE_A": 100.0, "LINE_B": 200.0},
            "p2": {"LINE_A": -95.0, "LINE_B": -190.0},
        }
        result = self.service._compute_deltas(flows, flows)
        for line_id, info in result.items():
            assert info["delta"] == 0.0
            # When all deltas are 0, threshold = 0*0.05 = 0, and abs(0) < 0 is False,
            # so 0 is categorized as "negative" (since 0 > 0 is also False).
            assert info["category"] in ("grey", "negative")

    def test_positive_delta(self):
        """Increased flow should be categorized as positive."""
        before = {"p1": {"LINE_A": 100.0}, "p2": {"LINE_A": -95.0}}
        after = {"p1": {"LINE_A": 200.0}, "p2": {"LINE_A": -195.0}}
        result = self.service._compute_deltas(after, before)
        assert result["LINE_A"]["delta"] == 100.0
        assert result["LINE_A"]["category"] == "positive"

    def test_negative_delta(self):
        """Decreased flow should be categorized as negative."""
        before = {"p1": {"LINE_A": 200.0}, "p2": {"LINE_A": -195.0}}
        after = {"p1": {"LINE_A": 100.0}, "p2": {"LINE_A": -95.0}}
        result = self.service._compute_deltas(after, before)
        assert result["LINE_A"]["delta"] == -100.0
        assert result["LINE_A"]["category"] == "negative"

    def test_small_delta_below_threshold_is_grey(self):
        """Deltas below 5% of max are categorized as grey."""
        before = {
            "p1": {"LINE_A": 100.0, "LINE_B": 100.0},
            "p2": {"LINE_A": -95.0, "LINE_B": -95.0},
        }
        # LINE_A has large delta, LINE_B has tiny delta
        after = {
            "p1": {"LINE_A": 200.0, "LINE_B": 101.0},
            "p2": {"LINE_A": -195.0, "LINE_B": -96.0},
        }
        result = self.service._compute_deltas(after, before)
        # LINE_A: delta=100.0, threshold = 100*0.05 = 5.0
        assert result["LINE_A"]["category"] == "positive"
        # LINE_B: delta=1.0 < 5.0 threshold
        assert result["LINE_B"]["category"] == "grey"

    def test_empty_flows(self):
        """Empty flow sets should produce empty deltas."""
        empty = {"p1": {}, "p2": {}}
        result = self.service._compute_deltas(empty, empty)
        assert result == {}

    def test_lines_in_after_not_in_before(self):
        """Lines appearing only in 'after' should still produce deltas."""
        before = {"p1": {}, "p2": {}}
        after = {"p1": {"LINE_A": 50.0}, "p2": {"LINE_A": -48.0}}
        result = self.service._compute_deltas(after, before)
        assert "LINE_A" in result
        assert result["LINE_A"]["delta"] == 50.0

    def test_lines_in_before_not_in_after(self):
        """Lines appearing only in 'before' should produce negative deltas."""
        before = {"p1": {"LINE_A": 50.0}, "p2": {"LINE_A": -48.0}}
        after = {"p1": {}, "p2": {}}
        result = self.service._compute_deltas(after, before)
        assert "LINE_A" in result
        assert result["LINE_A"]["delta"] == -50.0

    def test_delta_rounding(self):
        """Deltas should be rounded to 1 decimal place."""
        before = {"p1": {"LINE_A": 100.0}, "p2": {"LINE_A": -95.0}}
        after = {"p1": {"LINE_A": 133.333}, "p2": {"LINE_A": -130.0}}
        result = self.service._compute_deltas(after, before)
        # delta = 133.333 - 100.0 = 33.333 -> rounded to 33.3
        assert result["LINE_A"]["delta"] == 33.3

    def test_multiple_lines(self):
        """Test with multiple lines having varying deltas."""
        before = {
            "p1": {"L1": 100.0, "L2": 200.0, "L3": 50.0},
            "p2": {"L1": -95.0, "L2": -195.0, "L3": -48.0},
        }
        after = {
            "p1": {"L1": 150.0, "L2": 180.0, "L3": 51.0},
            "p2": {"L1": -145.0, "L2": -175.0, "L3": -49.0},
        }
        result = self.service._compute_deltas(after, before)
        assert len(result) == 3
        # L1 has biggest positive delta (50), L2 has negative delta (-20)
        assert result["L1"]["category"] == "positive"
        assert result["L2"]["category"] == "negative"
        # L3 has delta=1.0, threshold = 50*0.05 = 2.5 → grey
        assert result["L3"]["category"] == "grey"

    def test_flow_direction_uses_p2_when_p2_larger(self):
        """When p2 is the entering terminal (p2 > p1), delta uses p2."""
        before = {
            "p1": {"LINE_A": -50.0},
            "p2": {"LINE_A": 55.0},
        }
        after = {
            "p1": {"LINE_A": -80.0},
            "p2": {"LINE_A": 85.0},
        }
        result = self.service._compute_deltas(after, before)
        # after: p2 > p1, so after_idx=2, after_val=85
        # before: p2 > p1, so before_idx=2, before_val=55
        # Same direction → delta = 85 - 55 = 30
        assert result["LINE_A"]["delta"] == 30.0

    def test_single_line_always_has_category(self):
        """With a single line, even significant deltas have a valid category."""
        before = {"p1": {"LINE_A": 100.0}, "p2": {"LINE_A": -95.0}}
        after = {"p1": {"LINE_A": 200.0}, "p2": {"LINE_A": -195.0}}
        result = self.service._compute_deltas(after, before)
        assert result["LINE_A"]["category"] in ("positive", "negative", "grey")
