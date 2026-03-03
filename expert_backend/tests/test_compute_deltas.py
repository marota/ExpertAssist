"""Tests for RecommenderService._direction_aware_delta and _compute_deltas."""

import pytest
from expert_backend.services.recommender_service import RecommenderService


def _make_flows(p1, p2, q1=None, q2=None, vl1=None, vl2=None):
    """Helper to build a flows dict with optional Q and VL defaults."""
    if q1 is None:
        q1 = {k: 0.0 for k in p1}
    if q2 is None:
        q2 = {k: 0.0 for k in p2}
    if vl1 is None:
        vl1 = {k: f"VL1_{k}" for k in p1}
    if vl2 is None:
        vl2 = {k: f"VL2_{k}" for k in p1}
    return {"p1": p1, "p2": p2, "q1": q1, "q2": q2, "vl1": vl1, "vl2": vl2}


class TestDirectionAwareDelta:
    """Tests for _direction_aware_delta static method.

    Convention: positive value = power enters at that terminal.
    The entering terminal has the larger absolute value.
    """

    def test_same_direction_increased(self):
        """After stronger, same direction → positive delta, no flip."""
        # before: 100 enters t1; after: 200 enters t1
        delta, flip = RecommenderService._direction_aware_delta(200, -198, 100, -98)
        assert delta == pytest.approx(100.0)
        assert flip is False

    def test_same_direction_decreased(self):
        """After weaker, same direction → negative delta, no flip."""
        # before: 200 enters t1; after: 100 enters t1
        delta, flip = RecommenderService._direction_aware_delta(100, -98, 200, -198)
        assert delta == pytest.approx(-100.0)
        assert flip is False

    def test_same_direction_entering_t2(self):
        """Both states enter at t2 → positive delta when after is stronger."""
        # before: 55 enters t2; after: 85 enters t2
        delta, flip = RecommenderService._direction_aware_delta(-80, 85, -50, 55)
        assert delta == pytest.approx(30.0)
        assert flip is False

    def test_direction_reversal_before_stronger(self):
        """Direction reverses, before is stronger → negative delta, flip=True."""
        # before: 100 enters t1 (mag=100); after: 85 enters t2 (mag=85)
        # ref = before (stronger, enters t1)
        # a_signed = -85 (opposite to ref dir), b_signed = +100
        # delta = -85 - 100 = -185
        delta, flip = RecommenderService._direction_aware_delta(-80, 85, 100, -98)
        assert delta == pytest.approx(-185.0)
        assert flip is True

    def test_direction_reversal_after_stronger(self):
        """Direction reverses, after is stronger → no flip."""
        # before: 50 enters t1; after: 80 enters t2 (reversed, stronger)
        # ref = after (stronger, enters t2)
        # a_signed = +85, b_signed = -50 (opposite to ref dir)
        # delta = 85 - (-50) = 135
        delta, flip = RecommenderService._direction_aware_delta(-80, 85, 50, -48)
        assert delta == pytest.approx(135.0)
        assert flip is False

    def test_equal_magnitude_no_flip(self):
        """Equal magnitude, same direction → zero delta, no flip."""
        delta, flip = RecommenderService._direction_aware_delta(100, -98, 100, -98)
        assert delta == pytest.approx(0.0)
        assert flip is False

    def test_both_zero(self):
        """Both states zero → zero delta, no flip."""
        delta, flip = RecommenderService._direction_aware_delta(0, 0, 0, 0)
        assert delta == pytest.approx(0.0)
        assert flip is False

    def test_one_state_zero(self):
        """One state is zero (line absent) → delta = magnitude of the other."""
        # after has flow, before is zero
        delta, flip = RecommenderService._direction_aware_delta(50, -48, 0, 0)
        assert delta == pytest.approx(50.0)
        assert flip is False

    def test_one_state_zero_reversed(self):
        """Before has flow, after is zero → negative delta."""
        delta, flip = RecommenderService._direction_aware_delta(0, 0, 50, -48)
        assert delta == pytest.approx(-50.0)
        assert flip is False


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
        for info in result["flow_deltas"].values():
            assert info["delta"] == 0.0
            assert info["flip_arrow"] is False

    def test_positive_delta_same_direction(self):
        """Increased flow (same direction) → positive delta, no arrow flip."""
        before = _make_flows(p1={"L": 100.0}, p2={"L": -98.0})
        after = _make_flows(p1={"L": 200.0}, p2={"L": -198.0})
        result = self.service._compute_deltas(after, before)["flow_deltas"]
        assert result["L"]["delta"] == 100.0
        assert result["L"]["category"] == "positive"
        assert result["L"]["flip_arrow"] is False

    def test_negative_delta_same_direction(self):
        """Decreased flow (same direction) → negative delta, no arrow flip."""
        before = _make_flows(p1={"L": 200.0}, p2={"L": -198.0})
        after = _make_flows(p1={"L": 100.0}, p2={"L": -98.0})
        result = self.service._compute_deltas(after, before)["flow_deltas"]
        assert result["L"]["delta"] == -100.0
        assert result["L"]["category"] == "negative"
        assert result["L"]["flip_arrow"] is False

    def test_direction_reversal(self):
        """Flow reverses direction: delta reflects the full swing."""
        # before: 100 enters t1; after: 80 enters t2 (reversed at t1 = -80)
        before = _make_flows(p1={"L": 100.0}, p2={"L": -98.0})
        after = _make_flows(p1={"L": -80.0}, p2={"L": 85.0})
        result = self.service._compute_deltas(after, before)["flow_deltas"]
        # Reference = before (stronger, t1). delta = -85 - 100 = -185
        # a_mag = 85, b_mag = 100; ref = before (enters t1)
        # a_signed = -85 (enters t2, opposite ref), b_signed = +100
        assert result["L"]["delta"] == -185.0
        assert result["L"]["flip_arrow"] is True

    def test_small_delta_below_threshold_is_grey(self):
        """Deltas below 5% of max are categorized as grey."""
        before = _make_flows(
            p1={"A": 100.0, "B": 100.0},
            p2={"A": -98.0, "B": -98.0},
        )
        after = _make_flows(
            p1={"A": 200.0, "B": 101.0},
            p2={"A": -198.0, "B": -99.0},
        )
        result = self.service._compute_deltas(after, before)["flow_deltas"]
        assert result["A"]["category"] == "positive"
        assert result["B"]["category"] == "grey"

    def test_empty_flows(self):
        """Empty flow sets should produce empty deltas."""
        empty = _make_flows(p1={}, p2={})
        result = self.service._compute_deltas(empty, empty)
        assert result["flow_deltas"] == {}
        assert result["reactive_flow_deltas"] == {}

    def test_lines_in_after_not_in_before(self):
        before = _make_flows(p1={}, p2={})
        after = _make_flows(p1={"L": 50.0}, p2={"L": -48.0})
        result = self.service._compute_deltas(after, before)["flow_deltas"]
        assert result["L"]["delta"] == 50.0

    def test_lines_in_before_not_in_after(self):
        before = _make_flows(p1={"L": 50.0}, p2={"L": -48.0})
        after = _make_flows(p1={}, p2={})
        result = self.service._compute_deltas(after, before)["flow_deltas"]
        assert result["L"]["delta"] == -50.0

    def test_delta_rounding(self):
        before = _make_flows(p1={"L": 100.0}, p2={"L": -98.0})
        after = _make_flows(p1={"L": 133.333}, p2={"L": -131.0})
        result = self.service._compute_deltas(after, before)["flow_deltas"]
        assert result["L"]["delta"] == 33.3

    def test_output_has_flip_arrow(self):
        """Output should include flip_arrow boolean."""
        before = _make_flows(p1={"L": 100.0}, p2={"L": -98.0})
        after = _make_flows(p1={"L": 200.0}, p2={"L": -198.0})
        result = self.service._compute_deltas(after, before)["flow_deltas"]
        assert "flip_arrow" in result["L"]
        assert isinstance(result["L"]["flip_arrow"], bool)

    # --- Reactive power delta tests ---

    def test_reactive_independent_from_p(self):
        """Q delta should be computed with its own reference direction, independent of P."""
        # P enters at t1 in both states (t1 > t2). Reference = after (stronger).
        # Q at t1: after=30, before=10 → same direction, Q delta = 20
        before = _make_flows(
            p1={"L": 100.0}, p2={"L": -98.0},
            q1={"L": 10.0}, q2={"L": -8.0},
        )
        after = _make_flows(
            p1={"L": 200.0}, p2={"L": -198.0},
            q1={"L": 30.0}, q2={"L": -28.0},
        )
        result = self.service._compute_deltas(after, before)
        assert result["reactive_flow_deltas"]["L"]["delta"] == 20.0

    def test_reactive_entering_t2(self):
        """When Q enters at t2 in both states, delta uses t2 reference."""
        before = _make_flows(
            p1={"L": -50.0}, p2={"L": 55.0},
            q1={"L": -8.0}, q2={"L": 10.0},
        )
        after = _make_flows(
            p1={"L": -80.0}, p2={"L": 85.0},
            q1={"L": -10.0}, q2={"L": 15.0},
        )
        result = self.service._compute_deltas(after, before)
        # P: both enter t2, after stronger → delta = 85 - 55 = 30
        assert result["flow_deltas"]["L"]["delta"] == 30.0
        # Q: both enter t2, after stronger → delta = 15 - 10 = 5
        assert result["reactive_flow_deltas"]["L"]["delta"] == 5.0

    def test_reactive_zero_when_q_unchanged(self):
        before = _make_flows(
            p1={"L": 100.0}, p2={"L": -98.0},
            q1={"L": 10.0}, q2={"L": -8.0},
        )
        after = _make_flows(
            p1={"L": 200.0}, p2={"L": -198.0},
            q1={"L": 10.0}, q2={"L": -8.0},
        )
        result = self.service._compute_deltas(after, before)
        assert result["reactive_flow_deltas"]["L"]["delta"] == 0.0

    def test_q_flip_arrow_independent_from_p(self):
        """Q's flip_arrow should be independent from P's flip_arrow."""
        # P: same direction both states → no flip
        # Q: direction reverses, before stronger → flip
        before = _make_flows(
            p1={"L": 100.0}, p2={"L": -98.0},
            q1={"L": 20.0}, q2={"L": -15.0},   # Q enters t1, mag=20
        )
        after = _make_flows(
            p1={"L": 200.0}, p2={"L": -198.0},
            q1={"L": -5.0}, q2={"L": 10.0},     # Q enters t2, mag=10
        )
        result = self.service._compute_deltas(after, before)
        # P: same dir, after stronger → no flip
        assert result["flow_deltas"]["L"]["flip_arrow"] is False
        # Q: direction reversed, before stronger (20 > 10) → flip
        assert result["reactive_flow_deltas"]["L"]["flip_arrow"] is True

    def test_p_flip_q_no_flip(self):
        """P flips but Q does not when they have independent directions."""
        # P: direction reverses, before stronger → flip
        # Q: same direction → no flip
        before = _make_flows(
            p1={"L": 200.0}, p2={"L": -198.0},  # P enters t1, mag=200
            q1={"L": 10.0}, q2={"L": -8.0},      # Q enters t1, mag=10
        )
        after = _make_flows(
            p1={"L": -100.0}, p2={"L": 105.0},   # P enters t2, mag=105
            q1={"L": 15.0}, q2={"L": -12.0},      # Q enters t1, mag=15
        )
        result = self.service._compute_deltas(after, before)
        # P: reversed, before stronger (200 > 105) → flip
        assert result["flow_deltas"]["L"]["flip_arrow"] is True
        # Q: same direction, after stronger → no flip
        assert result["reactive_flow_deltas"]["L"]["flip_arrow"] is False

    def test_reactive_has_flip_arrow_field(self):
        """Reactive flow deltas should always include flip_arrow."""
        before = _make_flows(
            p1={"L": 100.0}, p2={"L": -98.0},
            q1={"L": 10.0}, q2={"L": -8.0},
        )
        after = _make_flows(
            p1={"L": 200.0}, p2={"L": -198.0},
            q1={"L": 20.0}, q2={"L": -18.0},
        )
        result = self.service._compute_deltas(after, before)
        assert "flip_arrow" in result["reactive_flow_deltas"]["L"]
        assert isinstance(result["reactive_flow_deltas"]["L"]["flip_arrow"], bool)


class TestComputeAssetDeltas:
    """Tests for load/generator asset delta computation."""

    def setup_method(self):
        self.service = RecommenderService()

    def test_identical_assets_zero_deltas(self):
        flows = {"GEN_A": {"p": 100.0, "q": 20.0}}
        result = self.service._compute_asset_deltas(flows, flows)
        assert result["GEN_A"]["delta_p"] == 0.0
        assert result["GEN_A"]["delta_q"] == 0.0

    def test_positive_asset_delta(self):
        before = {"GEN_A": {"p": 100.0, "q": 20.0}}
        after = {"GEN_A": {"p": 200.0, "q": 20.0}}
        result = self.service._compute_asset_deltas(after, before)
        assert result["GEN_A"]["delta_p"] == 100.0
        assert result["GEN_A"]["category"] == "positive"

    def test_category_based_on_p_not_q(self):
        before = {"GEN_A": {"p": 100.0, "q": 20.0}}
        after = {"GEN_A": {"p": 100.0, "q": 50.0}}
        result = self.service._compute_asset_deltas(after, before)
        assert result["GEN_A"]["delta_q"] == 30.0
        assert result["GEN_A"]["category"] in ("grey", "negative")

    def test_empty_asset_flows(self):
        result = self.service._compute_asset_deltas({}, {})
        assert result == {}
