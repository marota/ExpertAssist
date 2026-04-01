import pytest
import numpy as np
from unittest.mock import MagicMock, patch
from expert_backend.services.recommender_service import RecommenderService

class TestManualActionEnrichment:
    @pytest.fixture
    def service(self):
        s = RecommenderService()
        s._dict_action = {"dummy": {}}
        # Mock _is_renewable_gen to always return True for testing curtailment
        s._is_renewable_gen = MagicMock(return_value=True)
        return s

    @pytest.fixture
    def mock_env(self):
        with patch("expert_backend.services.recommender_service.RecommenderService._get_simulation_env") as mock_get_env:
            env = MagicMock()
            mock_get_env.return_value = env
            
            obs = MagicMock()
            obs.n_components = 1
            obs.main_component_load_mw = 1000.0
            obs.name_line = ["LINE_1"]
            obs.rho = np.array([0.1])
            obs.name_gen = ["GEN_1"]
            obs.gen_p = np.array([100.0])
            obs.name_load = ["LOAD_1"]
            obs.load_p = np.array([50.0])
            
            sim_obs = MagicMock()
            sim_obs.n_components = 1
            sim_obs.main_component_load_mw = 1000.0
            sim_obs.rho = np.array([0.05])
            sim_obs.name_line = ["LINE_1"]
            sim_obs.name_gen = ["GEN_1"]
            sim_obs.gen_p = np.array([20.0]) # 80 MW curtailed
            sim_obs.name_load = ["LOAD_1"]
            sim_obs.load_p = np.array([10.0]) # 40 MW shed
            
            obs.simulate.return_value = (sim_obs, 0.5, False, {"exception": None})
            env.get_obs.return_value = obs
            
            class MockAction:
                def __init__(self, content):
                    set_bus = content.get("set_bus", {})
                    self.loads_bus = set_bus.get("loads_id", {})
                    self.gens_bus = set_bus.get("generators_id", {})
                    self.lines_ex_bus = set_bus.get("lines_ex_id", {})
                    self.lines_or_bus = set_bus.get("lines_or_id", {})
                    self.switches = set_bus.get("switches_id", {})

            env.action_space.side_effect = lambda content: MockAction(content)
            yield env

    @patch("expert_backend.services.network_service.network_service.get_generator_voltage_level")
    def test_curtailment_enrichment(self, mock_get_vl, service, mock_env):
        """Test that curtailment manual actions are enriched with topology and correct description."""
        mock_get_vl.return_value = "VL_GEN"
        action_id = "curtail_GEN_1"
        
        with patch.object(service, "_get_monitoring_parameters", return_value=(set(), set())), \
             patch.object(service, "_compute_deltas", return_value={}):
            
            result = service.simulate_manual_action(action_id, "CONTINGENCY")
            
            # Check topology in immediate response
            assert "action_topology" in result
            assert result["action_topology"]["gens_bus"] == {"GEN_1": -1}
            
            # Check description (quoted and VL-aware)
            assert "on generator 'GEN_1'" in service._dict_action[action_id]["description"]
            assert "at voltage level 'VL_GEN'" in service._dict_action[action_id]["description"]
            assert result["description_unitaire"] == "Effacement 'GEN_1' ('VL_GEN')"
            
            # Check curtailment details
            assert "curtailment_details" in result
            assert result["curtailment_details"][0]["gen_name"] == "GEN_1"
            assert result["curtailment_details"][0]["curtailed_mw"] == 80.0

    @patch("expert_backend.services.network_service.network_service.get_load_voltage_level")
    def test_load_shedding_enrichment(self, mock_get_vl, service, mock_env):
        """Test that load shedding manual actions are enriched with topology and correct description."""
        mock_get_vl.return_value = "VL_LOAD"
        action_id = "load_shedding_LOAD_1"
        
        with patch.object(service, "_get_monitoring_parameters", return_value=(set(), set())), \
             patch.object(service, "_compute_deltas", return_value={}):
            
            result = service.simulate_manual_action(action_id, "CONTINGENCY")
            
            # Check topology in immediate response
            assert "action_topology" in result
            assert result["action_topology"]["loads_bus"] == {"LOAD_1": -1}
            
            # Check description (quoted and VL-aware)
            assert "on 'LOAD_1'" in service._dict_action[action_id]["description"]
            assert "at voltage level 'VL_LOAD'" in service._dict_action[action_id]["description"]
            assert result["description_unitaire"] == "Effacement 'LOAD_1' ('VL_LOAD')"
            
            # Check load shedding details
            assert "load_shedding_details" in result
            assert result["load_shedding_details"][0]["load_name"] == "LOAD_1"
            assert result["load_shedding_details"][0]["shedded_mw"] == 40.0

    def test_immediate_topology_response(self, service, mock_env):
        """Test that any manual action returns action_topology in the result dict."""
        # Setup a dummy action in the dictionary
        service._dict_action = {
            "LINE_1_OPEN": {
                "content": {"set_bus": {"lines_ex_id": {"LINE_1": -1}}}
            }
        }
        
        with patch.object(service, "_get_monitoring_parameters", return_value=(set(), set())), \
             patch.object(service, "_compute_deltas", return_value={}):
            
            result = service.simulate_manual_action("LINE_1_OPEN", "CONTINGENCY")
            
            # Ensure action_topology is present in the response
            assert "action_topology" in result
            assert "lines_ex_bus" in result["action_topology"]
            assert result["action_topology"]["lines_ex_bus"] == {"LINE_1": -1}
