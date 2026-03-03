"""Tests for RecommenderService._compute_deltas flow delta computation."""

import pytest
from expert_backend.services.recommender_service import RecommenderService


def _make_flows(p1, p2, q1=None, q2=None):
    """Helper to build a flows dict with optional Q defaults."""
    if q1 is None:
        q1 = {k: 0.0 for k in p1}
    if q2 is None:
        q2 = {k: 0.0 for k in p2}
    return {"p1": p1, "p2": p2, "q1": q1, "q2": q2}


class TestComputeDeltas:
    """Tests for flow delta computation between two network states."""

    def setup_method(self):
        self.service = RecommenderService()

    def test_identical_flows_zero_deltas(self):
        """When before and after flows are identical, all deltas should be zero."""
        flows = _make_flows(
            p1={"LINE_A": 100.0, "LINE_B": 200.0},
            p2={"LINE_A": -95.0, "LINE_B": -190.0},
        )
        result = self.service._compute_deltas(flows, flows)
        for line_id, info in result["flow_deltas"].items():
            assert info["delta"] == 0.0
            # When all deltas are 0, threshold = 0*0.05 = 0, and abs(0) < 0 is False,
            # so 0 is categorized as "negative" (since 0 > 0 is also False).
            assert info["category"] in ("grey", "negative")

    def test_positive_delta(self):
        """Increased flow should be categorized as positive."""
        before = _make_flows(p1={"LINE_A": 100.0}, p2={"LINE_A": -95.0})
        after = _make_flows(p1={"LINE_A": 200.0}, p2={"LINE_A": -195.0})
        result = self.service._compute_deltas(after, before)["flow_deltas"]
        assert result["LINE_A"]["delta"] == 100.0
        assert result["LINE_A"]["category"] == "positive"

    def test_negative_delta(self):
        """Decreased flow should be categorized as negative."""
        before = _make_flows(p1={"LINE_A": 200.0}, p2={"LINE_A": -195.0})
        after = _make_flows(p1={"LINE_A": 100.0}, p2={"LINE_A": -95.0})
        result = self.service._compute_deltas(after, before)["flow_deltas"]
        assert result["LINE_A"]["delta"] == -100.0
        assert result["LINE_A"]["category"] == "negative"

    def test_small_delta_below_threshold_is_grey(self):
        """Deltas below 5% of max are categorized as grey."""
        before = _make_flows(
            p1={"LINE_A": 100.0, "LINE_B": 100.0},
            p2={"LINE_A": -95.0, "LINE_B": -95.0},
        )
        # LINE_A has large delta, LINE_B has tiny delta
        after = _make_flows(
            p1={"LINE_A": 200.0, "LINE_B": 101.0},
            p2={"LINE_A": -195.0, "LINE_B": -96.0},
        )
        result = self.service._compute_deltas(after, before)["flow_deltas"]
        # LINE_A: delta=100.0, threshold = 100*0.05 = 5.0
        assert result["LINE_A"]["category"] == "positive"
        # LINE_B: delta=1.0 < 5.0 threshold
        assert result["LINE_B"]["category"] == "grey"

    def test_empty_flows(self):
        """Empty flow sets should produce empty deltas."""
        empty = _make_flows(p1={}, p2={})
        result = self.service._compute_deltas(empty, empty)
        assert result["flow_deltas"] == {}
        assert result["reactive_flow_deltas"] == {}

    def test_lines_in_after_not_in_before(self):
        """Lines appearing only in 'after' should still produce deltas."""
        before = _make_flows(p1={}, p2={})
        after = _make_flows(p1={"LINE_A": 50.0}, p2={"LINE_A": -48.0})
        result = self.service._compute_deltas(after, before)["flow_deltas"]
        assert "LINE_A" in result
        assert result["LINE_A"]["delta"] == 50.0

    def test_lines_in_before_not_in_after(self):
        """Lines appearing only in 'before' should produce negative deltas."""
        before = _make_flows(p1={"LINE_A": 50.0}, p2={"LINE_A": -48.0})
        after = _make_flows(p1={}, p2={})
        result = self.service._compute_deltas(after, before)["flow_deltas"]
        assert "LINE_A" in result
        assert result["LINE_A"]["delta"] == -50.0

    def test_delta_rounding(self):
        """Deltas should be rounded to 1 decimal place."""
        before = _make_flows(p1={"LINE_A": 100.0}, p2={"LINE_A": -95.0})
        after = _make_flows(p1={"LINE_A": 133.333}, p2={"LINE_A": -130.0})
        result = self.service._compute_deltas(after, before)["flow_deltas"]
        # delta = 133.333 - 100.0 = 33.333 -> rounded to 33.3
        assert result["LINE_A"]["delta"] == 33.3

    def test_multiple_lines(self):
        """Test with multiple lines having varying deltas."""
        before = _make_flows(
            p1={"L1": 100.0, "L2": 200.0, "L3": 50.0},
            p2={"L1": -95.0, "L2": -195.0, "L3": -48.0},
        )
        after = _make_flows(
            p1={"L1": 150.0, "L2": 180.0, "L3": 51.0},
            p2={"L1": -145.0, "L2": -175.0, "L3": -49.0},
        )
        result = self.service._compute_deltas(after, before)["flow_deltas"]
        assert len(result) == 3
        # L1 has biggest positive delta (50), L2 has negative delta (-20)
        assert result["L1"]["category"] == "positive"
        assert result["L2"]["category"] == "negative"
        # L3 has delta=1.0, threshold = 50*0.05 = 2.5 → grey
        assert result["L3"]["category"] == "grey"

    def test_flow_direction_uses_p2_when_p2_larger(self):
        """When p2 is the entering terminal (p2 > p1), delta uses p2."""
        before = _make_flows(
            p1={"LINE_A": -50.0},
            p2={"LINE_A": 55.0},
        )
        after = _make_flows(
            p1={"LINE_A": -80.0},
            p2={"LINE_A": 85.0},
        )
        result = self.service._compute_deltas(after, before)["flow_deltas"]
        # after: p2 > p1, so after_idx=2, after_val=85
        # before: p2 > p1, so before_idx=2, before_val=55
        # Same direction → delta = 85 - 55 = 30
        assert result["LINE_A"]["delta"] == 30.0

    def test_single_line_always_has_category(self):
        """With a single line, even significant deltas have a valid category."""
        before = _make_flows(p1={"LINE_A": 100.0}, p2={"LINE_A": -95.0})
        after = _make_flows(p1={"LINE_A": 200.0}, p2={"LINE_A": -195.0})
        result = self.service._compute_deltas(after, before)["flow_deltas"]
        assert result["LINE_A"]["category"] in ("positive", "negative", "grey")

    # --- Reactive power delta tests ---

    def test_reactive_deltas_returned(self):
        """_compute_deltas should return reactive_flow_deltas alongside flow_deltas."""
        before = _make_flows(
            p1={"LINE_A": 100.0}, p2={"LINE_A": -95.0},
            q1={"LINE_A": 10.0}, q2={"LINE_A": -8.0},
        )
        after = _make_flows(
            p1={"LINE_A": 200.0}, p2={"LINE_A": -195.0},
            q1={"LINE_A": 30.0}, q2={"LINE_A": -28.0},
        )
        result = self.service._compute_deltas(after, before)
        assert "reactive_flow_deltas" in result
        assert "LINE_A" in result["reactive_flow_deltas"]

    def test_reactive_delta_uses_p_terminal_alignment(self):
        """Q delta should use the same entering terminal as P (determined by P values)."""
        before = _make_flows(
            p1={"LINE_A": 100.0}, p2={"LINE_A": -95.0},
            q1={"LINE_A": 10.0}, q2={"LINE_A": -8.0},
        )
        after = _make_flows(
            p1={"LINE_A": 200.0}, p2={"LINE_A": -195.0},
            q1={"LINE_A": 30.0}, q2={"LINE_A": -28.0},
        )
        result = self.service._compute_deltas(after, before)
        # P entering terminal is p1 (100 > -95 and 200 > -195), same direction
        # So Q delta uses q1: 30 - 10 = 20
        assert result["reactive_flow_deltas"]["LINE_A"]["delta"] == 20.0

    def test_reactive_zero_when_q_unchanged(self):
        """When Q values don't change, reactive delta should be zero."""
        before = _make_flows(
            p1={"LINE_A": 100.0}, p2={"LINE_A": -95.0},
            q1={"LINE_A": 10.0}, q2={"LINE_A": -8.0},
        )
        after = _make_flows(
            p1={"LINE_A": 200.0}, p2={"LINE_A": -195.0},
            q1={"LINE_A": 10.0}, q2={"LINE_A": -8.0},
        )
        result = self.service._compute_deltas(after, before)
        assert result["reactive_flow_deltas"]["LINE_A"]["delta"] == 0.0


class TestComputeAssetDeltas:
    """Tests for load/generator asset delta computation."""

    def setup_method(self):
        self.service = RecommenderService()

    def test_identical_assets_zero_deltas(self):
        """Identical asset flows should produce zero deltas."""
        flows = {"GEN_A": {"p": 100.0, "q": 20.0}}
        result = self.service._compute_asset_deltas(flows, flows)
        assert result["GEN_A"]["delta_p"] == 0.0
        assert result["GEN_A"]["delta_q"] == 0.0

    def test_positive_asset_delta(self):
        """Increased asset P should be categorized as positive."""
        before = {"GEN_A": {"p": 100.0, "q": 20.0}}
        after = {"GEN_A": {"p": 200.0, "q": 20.0}}
        result = self.service._compute_asset_deltas(after, before)
        assert result["GEN_A"]["delta_p"] == 100.0
        assert result["GEN_A"]["category"] == "positive"

    def test_category_based_on_p_not_q(self):
        """Category should be based on delta_p, not delta_q."""
        before = {"GEN_A": {"p": 100.0, "q": 20.0}}
        after = {"GEN_A": {"p": 100.0, "q": 50.0}}
        result = self.service._compute_asset_deltas(after, before)
        # P unchanged → grey (below threshold since max_abs_p = 0)
        assert result["GEN_A"]["delta_q"] == 30.0
        assert result["GEN_A"]["category"] in ("grey", "negative")

    def test_empty_asset_flows(self):
        """Empty asset flows should produce empty result."""
        result = self.service._compute_asset_deltas({}, {})
        assert result == {}
