# Copyright (c) 2025-2026, RTE (https://www.rte-france.com)
# This Source Code Form is subject to the terms of the Mozilla Public License, version 2.0.
# If a copy of the Mozilla Public License, version 2.0 was not distributed with this file,
# you can obtain one at http://mozilla.org/MPL/2.0/.
# SPDX-License-Identifier: MPL-2.0
# This file is part of Co-Study4Grid a Power Grid Study tool Assistant Interface to help solve contigencies for a grid state under study. 

import os
from pathlib import Path
from unittest.mock import patch, mock_open, MagicMock

import numpy as np
import pytest

from expert_backend.services.recommender_service import RecommenderService
from expert_backend.main import ConfigRequest
from expert_op4grid_recommender import config

class TestRecommenderService:
    @patch("expert_backend.services.recommender_service.enrich_actions_lazy")
    @patch("expert_backend.services.recommender_service.load_actions")
    @patch("expert_backend.services.network_service.network_service")
    @patch("builtins.open", new_callable=mock_open)
    def test_update_config_applies_settings(self, mock_file, mock_network_service, mock_load_actions, mock_enrich):
        # Set up mocks
        mock_load_actions.return_value = {"existing_action": {}}
        mock_network_service.get_disconnectable_elements.return_value = ["line1", "line2"]
        mock_network_service.get_monitored_elements.return_value = ["line1"]
        
        service = RecommenderService()
        
        # Test paths
        network_path = "/tmp/test_network.xiidm"
        action_path = "/tmp/test_actions.json"
        layout_path = "/tmp/test_layout.json"

        # Create a sample config request with test data paths and custom values
        settings = ConfigRequest(
            network_path=network_path,
            action_file_path=action_path,
            layout_path=layout_path,
            min_line_reconnections=5.0,
            min_close_coupling=4.0,
            min_open_coupling=3.0,
            min_line_disconnections=2.0,
            n_prioritized_actions=20,
            monitoring_factor=0.85,
            pre_existing_overload_threshold=0.05,
            ignore_reconnections=True,
            pypowsybl_fast_mode=False
        )

        service.update_config(settings)

        # Verify that config module was updated correctly
        assert config.ENV_PATH == Path(network_path)
        assert config.ENV_NAME == "test_network.xiidm"
        assert config.ENV_FOLDER == Path("/tmp")
        assert config.ACTION_FILE_PATH == Path(action_path)
        assert config.LAYOUT_FILE_PATH == Path(layout_path)
        
        assert config.MIN_LINE_RECONNECTIONS == 5.0
        assert config.MIN_CLOSE_COUPLING == 4.0
        assert config.MIN_OPEN_COUPLING == 3.0
        assert config.MIN_LINE_DISCONNECTIONS == 2.0
        assert config.N_PRIORITIZED_ACTIONS == 20
        assert config.MONITORING_FACTOR_THERMAL_LIMITS == 0.85
        assert config.PRE_EXISTING_OVERLOAD_WORSENING_THRESHOLD == 0.05
        
        # Verify the new settings are applied
        assert config.IGNORE_RECONNECTIONS is True
        assert config.PYPOWSYBL_FAST_MODE is False

        # Verify side effects (mocks)
        mock_load_actions.assert_called_once_with(Path(action_path))
        # Since disco_ actions were not in mock_load_actions.return_value, it should have auto-generated them
        # and called open(action_path, 'w')
        mock_file.assert_called_with(Path(action_path), 'w')
        
    def test_update_config_defaults(self):
        # We also want to verify that default settings work as expected
        with patch("expert_backend.services.recommender_service.load_actions") as mock_load, \
             patch("expert_backend.services.recommender_service.enrich_actions_lazy") as mock_enrich, \
             patch("expert_backend.services.network_service.network_service") as mock_ns, \
             patch("builtins.open", mock_open()):
            
            mock_load.return_value = {"disco_line1": {}} # already has disco
            service = RecommenderService()
            
            settings = ConfigRequest(
                network_path="/tmp/net",
                action_file_path="/tmp/act.json"
                # using defaults for the rest
            )
            
            service.update_config(settings)
            
            # Defaults check (based on main.py)
            assert config.IGNORE_RECONNECTIONS is False
            assert config.PYPOWSYBL_FAST_MODE is True
            assert config.MONITORING_FACTOR_THERMAL_LIMITS == 0.95
            assert config.PRE_EXISTING_OVERLOAD_WORSENING_THRESHOLD == 0.02


class TestRestoreAnalysisContext:
    """Tests for RecommenderService.restore_analysis_context()."""

    def test_restore_sets_analysis_context(self):
        service = RecommenderService()
        assert service._analysis_context is None

        service.restore_analysis_context(
            lines_we_care_about=["LINE_A", "LINE_B"],
            disconnected_element="LINE_X",
            lines_overloaded=["LINE_A"],
        )

        assert service._analysis_context is not None
        assert service._analysis_context["lines_we_care_about"] == ["LINE_A", "LINE_B"]
        assert service._analysis_context["lines_overloaded"] == ["LINE_A"]
        assert service._last_disconnected_element == "LINE_X"

    def test_restore_with_none_lines(self):
        service = RecommenderService()
        service.restore_analysis_context(lines_we_care_about=None)

        assert service._analysis_context is not None
        assert service._analysis_context["lines_we_care_about"] is None

    def test_restore_with_computed_pairs(self):
        service = RecommenderService()
        pairs = {"act1+act2": {"max_rho": 0.5, "betas": [0.1, 0.2]}}
        service.restore_analysis_context(
            lines_we_care_about=["L1"],
            computed_pairs=pairs,
        )

        assert service._saved_computed_pairs == pairs
        assert service.get_saved_computed_pairs() == pairs

    def test_restore_without_computed_pairs(self):
        service = RecommenderService()
        service.restore_analysis_context(lines_we_care_about=["L1"])

        assert service._saved_computed_pairs is None
        assert service.get_saved_computed_pairs() is None

    def test_restore_without_optional_fields(self):
        service = RecommenderService()
        service.restore_analysis_context(lines_we_care_about=["L1", "L2"])

        assert service._analysis_context["lines_we_care_about"] == ["L1", "L2"]
        assert "lines_overloaded" not in service._analysis_context
        assert service._last_disconnected_element is None

    def test_restore_updates_disconnected_element(self):
        service = RecommenderService()
        service._last_disconnected_element = "OLD_LINE"
        service.restore_analysis_context(
            lines_we_care_about=["L1"],
            disconnected_element="NEW_LINE",
        )
        assert service._last_disconnected_element == "NEW_LINE"

    def test_restore_does_not_overwrite_disconnected_element_if_none(self):
        service = RecommenderService()
        service._last_disconnected_element = "EXISTING"
        service.restore_analysis_context(
            lines_we_care_about=["L1"],
            disconnected_element=None,
        )
        # None is falsy, so it should not overwrite
        assert service._last_disconnected_element == "EXISTING"

    def test_reset_clears_restored_context(self):
        service = RecommenderService()
        service.restore_analysis_context(
            lines_we_care_about=["L1"],
            computed_pairs={"p": {}},
        )
        assert service._analysis_context is not None
        assert service._saved_computed_pairs is not None

        service.reset()
        assert service._analysis_context is None
        assert service._saved_computed_pairs is None


class TestGetMonitoringParametersWithContext:
    """Tests that _get_monitoring_parameters uses restored analysis context."""

    def _make_mock_obs(self, line_names):
        obs = MagicMock()
        obs.name_line = line_names
        obs._network_manager = MagicMock()
        network = MagicMock()
        obs._network_manager.network = network
        # Return empty limits so branches_with_limits defaults to set()
        import pandas as pd
        network.get_operational_limits.return_value = pd.DataFrame()
        return obs

    def test_uses_context_lines_we_care_about(self):
        service = RecommenderService()
        service._analysis_context = {
            "lines_we_care_about": ["LINE_A", "LINE_C"]
        }
        obs = self._make_mock_obs(["LINE_A", "LINE_B", "LINE_C"])

        lines, _ = service._get_monitoring_parameters(obs)
        assert lines == ["LINE_A", "LINE_C"]

    def test_fallback_without_context(self):
        service = RecommenderService()
        service._analysis_context = None
        obs = self._make_mock_obs(["LINE_A", "LINE_B"])

        # With IGNORE_LINES_MONITORING=True (default), falls back to all lines
        original = getattr(config, 'IGNORE_LINES_MONITORING', True)
        config.IGNORE_LINES_MONITORING = True
        try:
            lines, _ = service._get_monitoring_parameters(obs)
            assert lines == ["LINE_A", "LINE_B"]
        finally:
            config.IGNORE_LINES_MONITORING = original

    def test_context_with_none_care_falls_back_to_all_lines(self):
        service = RecommenderService()
        service._analysis_context = {"lines_we_care_about": None}
        obs = self._make_mock_obs(["L1", "L2", "L3"])

        lines, _ = service._get_monitoring_parameters(obs)
        assert lines == ["L1", "L2", "L3"]


class TestGetBaseNetworkMutualisation:
    """`_get_base_network` must reuse `network_service.network` when available
    to avoid re-parsing the same .xiidm file twice (~3-5 s of wasted pypowsybl
    work on large grids). See docs/perf-shared-network.md."""

    def test_reuses_network_service_network_when_available(self):
        from expert_backend.services.network_service import network_service

        service = RecommenderService()
        sentinel = MagicMock(name="shared_pypowsybl_network")
        # `_capture_initial_pst_taps` touches pypowsybl tap-changer APIs —
        # stub it out so the test doesn't need a real pp object.
        saved = network_service.network
        network_service.network = sentinel
        try:
            with patch.object(service, "_capture_initial_pst_taps"), \
                 patch("pypowsybl.network.load") as mock_load:
                n = service._get_base_network()
                # Mutualisation: no fresh pp.network.load() was issued.
                mock_load.assert_not_called()
                assert n is sentinel
                # Convenience method installed.
                assert callable(getattr(n, "get_line_ids", None))
                # Cache populated so the next call is a no-op.
                assert service._base_network is sentinel
        finally:
            network_service.network = saved

    def test_falls_back_to_standalone_load_when_network_service_empty(self):
        """Preserves direct-instantiation path for unit tests and callers
        that bypass `/api/config` (and therefore don't populate
        `network_service.network`)."""
        from expert_backend.services.network_service import network_service

        service = RecommenderService()
        loaded = MagicMock(name="freshly_loaded")

        saved = network_service.network
        network_service.network = None
        try:
            env_path = MagicMock()
            env_path.is_dir.return_value = False
            env_path.exists.return_value = True
            env_path.__str__ = lambda self: "/fake/grid.xiidm"  # type: ignore[assignment]

            with patch.object(config, "ENV_PATH", env_path), \
                 patch.object(service, "_capture_initial_pst_taps"), \
                 patch("pypowsybl.network.load", return_value=loaded) as mock_load:
                n = service._get_base_network()
                mock_load.assert_called_once()
                assert n is loaded
        finally:
            network_service.network = saved


class TestPrefetchBaseNad:
    """Tests for the base-NAD prefetch (perf #2 — see docs/perf-nad-prefetch.md).

    The prefetch runs concurrently with `setup_environment_configs_pypowsybl`
    inside `update_config` so the subsequent `/api/network-diagram` XHR can
    skip the ~6 s of pypowsybl NAD regeneration entirely.
    """

    def test_initial_state_has_no_prefetch(self):
        service = RecommenderService()
        assert service._prefetched_base_nad is None
        assert service._prefetched_base_nad_event is None
        assert service.get_prefetched_base_nad() is None

    def test_prefetch_populates_cache_on_success(self):
        service = RecommenderService()

        expected = {"svg": "<svg>prefetched</svg>", "metadata": None}
        # `_get_base_network()` is called in the main thread to pre-warm
        # the network cache; the worker then calls `get_network_diagram`
        # on the hot cache. Patch both so we don't need pypowsybl.
        with patch.object(service, "_get_base_network", return_value=MagicMock()), \
             patch.object(service, "get_network_diagram", return_value=expected):
            service.prefetch_base_nad_async()
            # Block until the worker completes.
            result = service.get_prefetched_base_nad(timeout=10)

        assert result == expected
        assert service._prefetched_base_nad_error is None

    def test_prefetch_surfaces_worker_exception(self):
        service = RecommenderService()

        boom = RuntimeError("pypowsybl exploded")
        with patch.object(service, "_get_base_network", return_value=MagicMock()), \
             patch.object(service, "get_network_diagram", side_effect=boom):
            service.prefetch_base_nad_async()
            with pytest.raises(RuntimeError, match="pypowsybl exploded"):
                service.get_prefetched_base_nad(timeout=10)

    def test_prefetch_records_network_load_error_without_spawning_worker(self):
        """If `_get_base_network()` fails in the main thread, no worker
        should be started — the error is recorded directly and the event
        is pre-set so the next `get_prefetched_base_nad()` re-raises
        instantly."""
        service = RecommenderService()

        boom = FileNotFoundError("network file gone")
        with patch.object(service, "_get_base_network", side_effect=boom):
            service.prefetch_base_nad_async()
        # Worker thread was never started.
        assert service._prefetched_base_nad_thread is None
        # Event is pre-set so there is no wait.
        assert service._prefetched_base_nad_event is not None
        assert service._prefetched_base_nad_event.is_set()
        with pytest.raises(FileNotFoundError):
            service.get_prefetched_base_nad(timeout=0.1)

    def test_reset_drains_pending_prefetch_and_clears_state(self):
        """A dangling worker thread that finishes after reset() would
        otherwise write stale SVG into the next study's cache. `reset()`
        must join the worker and then zero the fields."""
        service = RecommenderService()
        expected = {"svg": "<svg>first_study</svg>", "metadata": None}
        with patch.object(service, "_get_base_network", return_value=MagicMock()), \
             patch.object(service, "get_network_diagram", return_value=expected):
            service.prefetch_base_nad_async()
            # Make sure the worker ran to completion before reset.
            service.get_prefetched_base_nad(timeout=10)

        service.reset()
        assert service._prefetched_base_nad is None
        assert service._prefetched_base_nad_error is None
        assert service._prefetched_base_nad_event is None
        assert service._prefetched_base_nad_thread is None
        assert service.get_prefetched_base_nad() is None

    def test_timeout_returns_none_without_raising(self):
        """When the caller runs out of patience, `get_prefetched_base_nad`
        returns None (signalling 'fall through to fresh compute') rather
        than raising, so the endpoint stays usable. The worker keeps
        running — its eventual result will be discarded on the next reset."""
        service = RecommenderService()

        import threading
        release = threading.Event()

        def slow_get_diagram():
            release.wait(timeout=5)
            return {"svg": "<svg/>", "metadata": None}

        try:
            with patch.object(service, "_get_base_network", return_value=MagicMock()), \
                 patch.object(service, "get_network_diagram", side_effect=slow_get_diagram):
                service.prefetch_base_nad_async()
                result = service.get_prefetched_base_nad(timeout=0.05)
                assert result is None
        finally:
            # Let the worker finish so the daemon thread doesn't linger.
            release.set()
            if service._prefetched_base_nad_thread is not None:
                service._prefetched_base_nad_thread.join(timeout=5)


class TestUpdateConfigSharesNetworkWithGrid2op:
    """`update_config` must pass the already-loaded Network to the upstream
    `setup_environment_configs_pypowsybl(network=...)` so grid2op does not
    re-parse the same .xiidm file. See docs/perf-grid2op-shared-network.md."""

    @patch("builtins.open", new_callable=mock_open)
    @patch("expert_backend.services.network_service.network_service")
    @patch("expert_backend.services.recommender_service.load_actions")
    @patch("expert_backend.services.recommender_service.enrich_actions_lazy")
    def test_update_config_injects_preloaded_network_into_upstream(
        self, mock_enrich, mock_load, mock_ns, mock_file
    ):
        mock_load.return_value = {"disco_line1": {}}  # skip disco auto-gen
        mock_ns.get_disconnectable_elements.return_value = []
        mock_ns.get_monitored_elements.return_value = []

        service = RecommenderService()
        # Pre-populate the base network so `prefetch_base_nad_async` doesn't
        # try the real load. The same sentinel must land in the upstream call.
        preloaded = MagicMock(name="preloaded_network")
        service._base_network = preloaded

        settings = ConfigRequest(
            network_path="/tmp/net.xiidm",
            action_file_path="/tmp/actions.json",
        )

        with patch(
            "expert_op4grid_recommender.environment_pypowsybl.setup_environment_configs_pypowsybl"
        ) as mock_setup, patch.object(
            service, "prefetch_base_nad_async"
        ), patch.object(
            service, "prefetch_non_reconnectable_lines_async"
        ):
            mock_setup.return_value = (
                MagicMock(),  # env
                MagicMock(),  # obs
                "/tmp/env",   # env_path
                "chronic",    # chronic_name
                None,         # custom_layout
                {},           # raw_dict
                [],           # lines_non_reconnectable
                [],           # lines_we_care_about
            )

            service.update_config(settings)

            # Upstream helper MUST receive the pre-loaded Network to skip
            # its own pp.network.load() — this is the whole point of the
            # perf-grid2op-shared-network optimisation.
            mock_setup.assert_called_once()
            call_kwargs = mock_setup.call_args.kwargs
            assert call_kwargs.get("network") is preloaded
            # AND it MUST receive skip_non_reconnectable_detection=True —
            # the topology walk now runs in a background thread spawned by
            # `update_config`. See docs/perf-deferred-non-reconnectable-detection.md.
            assert call_kwargs.get("skip_non_reconnectable_detection") is True





class TestEnsureNStateReady:
    """Guard that runs at the entry of every analyze/suggest/simulate
    endpoint: must drain any pending NAD prefetch AND position the shared
    pypowsybl Network on the N variant. See docs/perf-grid2op-shared-network.md
    ("variant-state guard")."""

    def test_drains_prefetch_then_positions_n_variant(self):
        service = RecommenderService()
        fake_net = MagicMock(name="shared_network")
        fake_net.get_variant_ids.return_value = ["N_state_cached"]
        service._base_network = fake_net

        with patch.object(service, "_drain_pending_base_nad_prefetch") as drain, \
             patch.object(service, "_get_n_variant", return_value="N_state_cached"):
            service._ensure_n_state_ready()

            drain.assert_called_once()
            fake_net.set_working_variant.assert_called_once_with("N_state_cached")

    def test_is_noop_before_any_network_is_loaded(self):
        """Calling the guard before /api/config has run at all must not
        raise — callers downstream will produce their own error when
        they actually need the network."""
        service = RecommenderService()
        assert service._base_network is None
        saved_env_path = getattr(config, "ENV_PATH", None)
        try:
            config.ENV_PATH = None
            service._ensure_n_state_ready()  # Must not raise.
        finally:
            config.ENV_PATH = saved_env_path

    def test_swallows_and_logs_variant_positioning_errors(self):
        """If `_get_n_variant` fails (e.g. LF diverged), the guard must not
        propagate — downstream code produces a clearer error on its first
        variant access."""
        service = RecommenderService()
        service._base_network = MagicMock(name="net")
        with patch.object(service, "_drain_pending_base_nad_prefetch"), \
             patch.object(service, "_get_n_variant", side_effect=RuntimeError("LF diverged")):
            service._ensure_n_state_ready()  # Must not re-raise.


class TestVariantRestorationIsSafeOnException:
    """`_get_n_variant` and `_get_n1_variant` must restore the original
    working variant even when the AC load flow raises. Otherwise the
    shared Network (used by network_service and grid2op) gets stuck on
    a `*_cached` variant and silently corrupts concurrent reads."""

    def test_get_n_variant_restores_original_on_lf_failure(self):
        service = RecommenderService()
        fake_net = MagicMock(name="net")
        fake_net.get_working_variant_id.return_value = "InitialState"
        fake_net.get_variant_ids.return_value = []  # variant doesn't exist → create path
        service._base_network = fake_net

        with patch.object(service, "_run_ac_with_fallback", side_effect=RuntimeError("LF boom")):
            with pytest.raises(RuntimeError, match="LF boom"):
                service._get_n_variant()

        # MUST have been called to restore the original variant, even
        # though the LF raised inside the try block.
        fake_net.set_working_variant.assert_any_call("InitialState")

    def test_get_n1_variant_restores_original_on_lf_failure(self):
        service = RecommenderService()
        fake_net = MagicMock(name="net")
        fake_net.get_working_variant_id.return_value = "InitialState"
        # N variant already exists → _get_n_variant is a fast path (no LF).
        fake_net.get_variant_ids.return_value = ["N_state_cached"]
        service._base_network = fake_net

        with patch.object(service, "_run_ac_with_fallback", side_effect=RuntimeError("LF boom")):
            with pytest.raises(RuntimeError, match="LF boom"):
                service._get_n1_variant("LINE_A")

        fake_net.set_working_variant.assert_any_call("InitialState")


class TestEnsureN1StateReady:
    """`_ensure_n1_state_ready(disconnected_element)` is used by
    `simulate_manual_action` and `compute_superposition` — they operate
    on top of a known contingency, so the natural entry state is N-1
    (not N). The guard drains the NAD prefetch worker, then positions
    the shared Network on the N-1 variant for the given contingency."""

    def test_drains_prefetch_then_positions_n1_variant(self):
        service = RecommenderService()
        fake_net = MagicMock(name="shared_network")
        service._base_network = fake_net

        with patch.object(service, "_drain_pending_base_nad_prefetch") as drain, \
             patch.object(service, "_get_n1_variant", return_value="N_1_state_LINE_A") as n1:
            service._ensure_n1_state_ready("LINE_A")

            drain.assert_called_once()
            n1.assert_called_once_with("LINE_A")
            fake_net.set_working_variant.assert_called_once_with("N_1_state_LINE_A")

    def test_is_noop_before_any_network_is_loaded(self):
        service = RecommenderService()
        assert service._base_network is None
        saved_env_path = getattr(config, "ENV_PATH", None)
        try:
            config.ENV_PATH = None
            service._ensure_n1_state_ready("LINE_A")  # Must not raise.
        finally:
            config.ENV_PATH = saved_env_path

    def test_drain_only_when_disconnected_element_is_empty(self):
        """If the caller has no contingency in hand (e.g. an odd fallback
        path), drain but don't attempt to position — there's no
        meaningful N-1 to ask for."""
        service = RecommenderService()
        service._base_network = MagicMock(name="net")
        with patch.object(service, "_drain_pending_base_nad_prefetch") as drain, \
             patch.object(service, "_get_n1_variant") as n1:
            service._ensure_n1_state_ready("")

            drain.assert_called_once()
            n1.assert_not_called()

    def test_swallows_and_logs_variant_positioning_errors(self):
        service = RecommenderService()
        service._base_network = MagicMock(name="net")
        with patch.object(service, "_drain_pending_base_nad_prefetch"), \
             patch.object(service, "_get_n1_variant", side_effect=RuntimeError("LF diverged")):
            service._ensure_n1_state_ready("LINE_A")  # Must not re-raise.


class TestPrefetchNonReconnectableLines:
    """`prefetch_non_reconnectable_lines_async()` runs the ~2-10 s
    topology walk (`env.network_manager.detect_non_reconnectable_lines()`)
    in a background thread AFTER `/api/config` returns, invisible to
    the user. The result is merged into
    `_cached_env_context['lines_non_reconnectable']`. See
    docs/perf-deferred-non-reconnectable-detection.md."""

    def _make_env_context(self, detected, existing=None, raise_exc=None):
        """Build a fake `_cached_env_context` whose `env.network_manager
        .detect_non_reconnectable_lines()` returns `detected`."""
        env = MagicMock(name="env")
        if raise_exc is not None:
            env.network_manager.detect_non_reconnectable_lines.side_effect = raise_exc
        else:
            env.network_manager.detect_non_reconnectable_lines.return_value = detected
        return {
            "env": env,
            "lines_non_reconnectable": list(existing or []),
            "lines_we_care_about": [],
            "path_chronic": "/tmp",
            "chronic_name": "chronic",
            "custom_layout": None,
        }

    def test_noop_when_env_context_missing(self):
        service = RecommenderService()
        service._cached_env_context = None
        service.prefetch_non_reconnectable_lines_async()
        # No thread was started.
        assert service._non_reconnectable_detection_thread is None

    def test_worker_merges_detected_lines_into_context(self):
        service = RecommenderService()
        service._cached_env_context = self._make_env_context(
            detected=["L_topo_1", "L_topo_2"],
            existing=["L_csv_1"],
        )

        service.prefetch_non_reconnectable_lines_async()
        service._drain_pending_non_reconnectable_detection(timeout=5)

        merged = service._cached_env_context["lines_non_reconnectable"]
        # CSV line preserved + topology-detected appended, no dupes.
        assert "L_csv_1" in merged
        assert "L_topo_1" in merged
        assert "L_topo_2" in merged
        assert len(merged) == 3

    def test_worker_is_idempotent_on_duplicate_detection(self):
        """If the topology detection returns a line already in the CSV
        list, it MUST NOT be duplicated."""
        service = RecommenderService()
        service._cached_env_context = self._make_env_context(
            detected=["L_shared"],
            existing=["L_shared"],
        )

        service.prefetch_non_reconnectable_lines_async()
        service._drain_pending_non_reconnectable_detection(timeout=5)

        merged = service._cached_env_context["lines_non_reconnectable"]
        assert merged.count("L_shared") == 1

    def test_worker_swallows_exceptions_and_keeps_csv_list(self):
        """If `detect_non_reconnectable_lines()` raises, the worker must
        NOT propagate — the CSV-loaded list stays intact so downstream
        analysis can proceed with slightly degraded non-reco coverage."""
        service = RecommenderService()
        service._cached_env_context = self._make_env_context(
            detected=None,
            existing=["L_csv_only"],
            raise_exc=RuntimeError("topology walk crashed"),
        )

        # Must not raise.
        service.prefetch_non_reconnectable_lines_async()
        service._drain_pending_non_reconnectable_detection(timeout=5)

        # CSV list preserved; nothing appended.
        assert service._cached_env_context["lines_non_reconnectable"] == ["L_csv_only"]

    def test_ensure_n_state_ready_drains_the_worker(self):
        """The variant-state guard MUST drain the deferred detection
        worker so `run_analysis_step1` sees the merged list."""
        service = RecommenderService()
        service._cached_env_context = self._make_env_context(
            detected=["L_topo"], existing=[],
        )
        service._base_network = MagicMock()

        service.prefetch_non_reconnectable_lines_async()

        # Calling the guard must block until the worker is done.
        with patch.object(service, "_get_n_variant", return_value="N_state_cached"):
            service._ensure_n_state_ready()

        thread = service._non_reconnectable_detection_thread
        assert thread is None or not thread.is_alive()
        merged = service._cached_env_context["lines_non_reconnectable"]
        assert "L_topo" in merged

    def test_reset_drains_the_worker_before_clearing_state(self):
        """A dangling worker that finishes after reset() would write its
        detected lines into the NEXT study's context. reset() must
        join it first."""
        service = RecommenderService()
        service._cached_env_context = self._make_env_context(
            detected=["L_topo"], existing=[],
        )

        service.prefetch_non_reconnectable_lines_async()
        service.reset()

        assert service._non_reconnectable_detection_thread is None
        assert service._non_reconnectable_detection_event is None
