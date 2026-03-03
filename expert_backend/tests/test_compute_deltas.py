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


class TestBranchDelta:
    """Tests for the low-level _branch_delta static method."""

    def test_same_direction_increase(self):
        """Flow enters at terminal 1 in both states, magnitude increases."""
        # before: 100 enters at t1, ~100 leaves at t2
        # after:  150 enters at t1, ~150 leaves at t2
        delta = RecommenderService._branch_delta(150, -148, 100, -98)
        assert delta == pytest.approx(50.0)

    def test_same_direction_decrease(self):
        """Flow enters at terminal 1 in both states, magnitude decreases."""
        delta = RecommenderService._branch_delta(50, -48, 100, -98)
        assert delta == pytest.approx(-50.0)

    def test_same_direction_entering_t2(self):
        """Flow enters at terminal 2 in both states."""
        # before: -50 at t1 (leaving), 55 at t2 (entering) → mag 55
        # after:  -80 at t1 (leaving), 85 at t2 (entering) → mag 85
        delta = RecommenderService._branch_delta(-80, 85, -50, 55)
        assert delta == pytest.approx(30.0)

    def test_direction_reversal(self):
        """Flow reverses direction between states."""
        # before: 100 at t1 (entering), -98 at t2 → mag 100
        # after:  -80 at t1 (leaving), 85 at t2 (entering) → mag 85
        # Reference = before (stronger, mag 100) at t1 positive.
        # In after: t1 = -80, sign flipped → after signed_mag = -80
        # delta = -80 - 100 = -180
        delta = RecommenderService._branch_delta(-80, 85, 100, -98)
        assert delta == pytest.approx(-180.0)

    def test_identical_zero_delta(self):
        """Identical flows → zero delta."""
        delta = RecommenderService._branch_delta(100, -98, 100, -98)
        assert delta == pytest.approx(0.0)

    def test_both_zero(self):
        """Both states zero flow."""
        delta = RecommenderService._branch_delta(0, 0, 0, 0)
        assert delta == pytest.approx(0.0)


class TestComputeDeltas:
    """Tests for flow delta computation between two network states."""

    def setup_method(self):
        self.service = RecommenderService()

    def test_identical_flows_zero_deltas(self):
        """When before and after flows are identical, all deltas should be zero."""
        flows = _make_flows(
            p1={"LINE_A": 100.0, "LINE_B": 200.0},
            p2={"LINE_A": -98.0, "LINE_B": -195.0},
        )
        result = self.service._compute_deltas(flows, flows)
        for line_id, info in result["flow_deltas"].items():
            assert info["delta"] == 0.0

    def test_positive_delta(self):
        """Increased flow should be categorized as positive."""
        before = _make_flows(p1={"LINE_A": 100.0}, p2={"LINE_A": -98.0})
        after = _make_flows(p1={"LINE_A": 200.0}, p2={"LINE_A": -198.0})
        result = self.service._compute_deltas(after, before)["flow_deltas"]
        assert result["LINE_A"]["delta"] == 100.0
        assert result["LINE_A"]["category"] == "positive"

    def test_negative_delta(self):
        """Decreased flow should be categorized as negative."""
        before = _make_flows(p1={"LINE_A": 200.0}, p2={"LINE_A": -198.0})
        after = _make_flows(p1={"LINE_A": 100.0}, p2={"LINE_A": -98.0})
        result = self.service._compute_deltas(after, before)["flow_deltas"]
        assert result["LINE_A"]["delta"] == -100.0
        assert result["LINE_A"]["category"] == "negative"

    def test_small_delta_below_threshold_is_grey(self):
        """Deltas below 5% of max are categorized as grey."""
        before = _make_flows(
            p1={"LINE_A": 100.0, "LINE_B": 100.0},
            p2={"LINE_A": -98.0, "LINE_B": -98.0},
        )
        after = _make_flows(
            p1={"LINE_A": 200.0, "LINE_B": 101.0},
            p2={"LINE_A": -198.0, "LINE_B": -99.0},
        )
        result = self.service._compute_deltas(after, before)["flow_deltas"]
        assert result["LINE_A"]["category"] == "positive"
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
        before = _make_flows(p1={"LINE_A": 100.0}, p2={"LINE_A": -98.0})
        after = _make_flows(p1={"LINE_A": 133.333}, p2={"LINE_A": -131.0})
        result = self.service._compute_deltas(after, before)["flow_deltas"]
        assert result["LINE_A"]["delta"] == 33.3

    def test_multiple_lines(self):
        """Test with multiple lines having varying deltas."""
        before = _make_flows(
            p1={"L1": 100.0, "L2": 200.0, "L3": 50.0},
            p2={"L1": -98.0, "L2": -198.0, "L3": -48.0},
        )
        after = _make_flows(
            p1={"L1": 150.0, "L2": 180.0, "L3": 51.0},
            p2={"L1": -148.0, "L2": -178.0, "L3": -49.0},
        )
        result = self.service._compute_deltas(after, before)["flow_deltas"]
        assert len(result) == 3
        assert result["L1"]["category"] == "positive"
        assert result["L2"]["category"] == "negative"
        assert result["L3"]["category"] == "grey"

    def test_single_line_always_has_category(self):
        """With a single line, even significant deltas have a valid category."""
        before = _make_flows(p1={"LINE_A": 100.0}, p2={"LINE_A": -98.0})
        after = _make_flows(p1={"LINE_A": 200.0}, p2={"LINE_A": -198.0})
        result = self.service._compute_deltas(after, before)["flow_deltas"]
        assert result["LINE_A"]["category"] in ("positive", "negative", "grey")

    # --- Reactive power delta tests ---

    def test_reactive_deltas_returned(self):
        """_compute_deltas should return reactive_flow_deltas alongside flow_deltas."""
        before = _make_flows(
            p1={"LINE_A": 100.0}, p2={"LINE_A": -98.0},
            q1={"LINE_A": 10.0}, q2={"LINE_A": -8.0},
        )
        after = _make_flows(
            p1={"LINE_A": 200.0}, p2={"LINE_A": -198.0},
            q1={"LINE_A": 30.0}, q2={"LINE_A": -28.0},
        )
        result = self.service._compute_deltas(after, before)
        assert "reactive_flow_deltas" in result
        assert "LINE_A" in result["reactive_flow_deltas"]

    def test_reactive_delta_magnitude_based(self):
        """Q delta uses absolute magnitude logic."""
        before = _make_flows(
            p1={"LINE_A": 100.0}, p2={"LINE_A": -98.0},
            q1={"LINE_A": 10.0}, q2={"LINE_A": -8.0},
        )
        after = _make_flows(
            p1={"LINE_A": 200.0}, p2={"LINE_A": -198.0},
            q1={"LINE_A": 30.0}, q2={"LINE_A": -28.0},
        )
        result = self.service._compute_deltas(after, before)
        # Q entering at t1 in both states (10 > |-8|, 30 > |-28|)
        # delta = 30 - 10 = 20
        assert result["reactive_flow_deltas"]["LINE_A"]["delta"] == 20.0

    def test_reactive_zero_when_q_unchanged(self):
        """When Q values don't change, reactive delta should be zero."""
        before = _make_flows(
            p1={"LINE_A": 100.0}, p2={"LINE_A": -98.0},
            q1={"LINE_A": 10.0}, q2={"LINE_A": -8.0},
        )
        after = _make_flows(
            p1={"LINE_A": 200.0}, p2={"LINE_A": -198.0},
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
        assert result["GEN_A"]["delta_q"] == 30.0
        assert result["GEN_A"]["category"] in ("grey", "negative")

    def test_empty_asset_flows(self):
        """Empty asset flows should produce empty result."""
        result = self.service._compute_asset_deltas({}, {})
        assert result == {}
