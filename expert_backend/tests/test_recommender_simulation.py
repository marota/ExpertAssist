import pytest
import os
from pathlib import Path
from unittest.mock import MagicMock, patch
from expert_backend.services.recommender_service import RecommenderService
from expert_op4grid_recommender import config

class TestRecommenderSimulationRealData:
    @classmethod
    def setup_class(cls):
        # Use the small test grid included in the repo
        cls.test_env_path = Path(__file__).parent.parent.parent / "data" / "bare_env_small_grid_test"
        cls.grid_path = cls.test_env_path / "grid.xiidm"
        
        # Ensure it exists
        if not cls.grid_path.exists():
            pytest.skip(f"Test grid not found at {cls.grid_path}")

    def setup_method(self):
        self.service = RecommenderService()
        # Point config to our test data
        config.ENV_PATH = self.test_env_path
        # Mock actions as an empty dict or minimal
        self.service._dict_action = {}

    def test_get_network_variants_caching_real(self):
        """Verify that variants are cached and not recreated if they already exist."""
        # 1. Base network should be cached
        n1 = self.service._get_base_network()
        n2 = self.service._get_base_network()
        assert n1 is n2
        
        # 2. N variant should be created once
        v_n = self.service._get_n_variant()
        assert v_n == "N_state_cached"
        assert v_n in n1.get_variant_ids()
        
        # Check that calling it again doesn't trigger another clone_variant
        with patch.object(n1, "clone_variant") as mock_clone:
            v_n_2 = self.service._get_n_variant()
            assert v_n_2 == "N_state_cached"
            mock_clone.assert_not_called()

        # 3. N-1 variant should be created once per contingency
        # Let's find a valid line ID from the network
        line_ids = n1.get_line_ids()
        if not line_ids:
            pytest.skip("No lines in test grid")
        
        target_line = line_ids[0]
        v_n1 = self.service._get_n1_variant(target_line)
        expected_v1 = f"N_1_state_{target_line}"
        assert v_n1 == expected_v1
        assert v_n1 in n1.get_variant_ids()
        
        with patch.object(n1, "clone_variant") as mock_clone:
            v_n1_repeat = self.service._get_n1_variant(target_line)
            assert v_n1_repeat == expected_v1
            mock_clone.assert_not_called()

    def test_simulation_env_is_cached(self):
        """Verify that _get_simulation_env returns the same instance and shares the network."""
        env1 = self.service._get_simulation_env()
        env2 = self.service._get_simulation_env()
        
        assert env1 is env2
        # Check that it uses the base network we load
        assert env1.network_manager.network is self.service._get_base_network()

    def test_simulate_manual_action_sets_correct_variant(self):
        """Verify that simulate_manual_action correctly switches variants and sets obs._variant_id."""
        # Set up a dummy action
        self.service._dict_action = {
            "act_1": {
                "content": {"change_line_status": {}}, # Minimal dummy content
                "description_unitaire": "Test Action"
            }
        }
        
        n = self.service._get_base_network()
        line_ids = n.get_line_ids()
        if not line_ids:
            pytest.skip("No lines in test grid")
        target_line = line_ids[0]
        
        # We need to mock the actual simulation to avoid needing a full LightSimBackend/Grid2Op setup
        # but we want to check the state BEFORE simulation call.
        
        env = self.service._get_simulation_env()
        
        with patch.object(env, "action_space") as mock_action_space, \
             patch.object(self.service, "_get_monitoring_parameters", return_value=(set(), set())), \
             patch.object(self.service, "_compute_deltas", return_value={}):
            
            # We want to intercept the get_obs() call to check _variant_id
            real_get_obs = env.get_obs
            def wrapped_get_obs():
                # We can check the working variant of the network here
                # because simulate_manual_action calls set_working_variant right before get_obs
                return mock_obs

            # We need to mock the obs.simulate return value
            mock_obs = MagicMock()
            mock_obs.simulate.return_value = (MagicMock(), None, None, {"exception": None})
            mock_obs.name_line = ["LINE_1"]
            mock_obs.rho = [0.1]
            
            with patch.object(env, "get_obs", side_effect=wrapped_get_obs) as mock_get_obs:
                self.service.simulate_manual_action("act_1", target_line)
                
                # Check that it called get_obs twice (one for N, one for N-1)
                assert mock_get_obs.call_count == 2
                
                # Check that after the second call, the observation was tagged with the N-1 variant ID
                # In the actual code: obs_simu_defaut._variant_id = n1_variant_id
                # Our mock_obs is returned by the second call.
                assert mock_get_obs.return_value._variant_id == f"N_1_state_{target_line}"
                
                # Check that _last_disconnected_element was updated
                assert self.service._last_disconnected_element == target_line
