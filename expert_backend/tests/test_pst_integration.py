
import pytest
import numpy as np
from unittest.mock import MagicMock, patch
from expert_backend.services.recommender_service import RecommenderService

@pytest.fixture
def recommender():
    svc = RecommenderService()
    svc._dict_action = {}
    svc._last_result = {"prioritized_actions": {}}
    return svc

def test_enrich_actions_includes_affected_line(recommender):
    """Verify that _enrich_actions propagates affected_line from prioritized_actions_dict."""
    prioritized_actions_dict = {
        "pst_action": {
            "description_unitaire": "PST tap change",
            "rho_before": np.array([0.8]),
            "rho_after": np.array([0.7]),
            "max_rho": 0.7,
            "max_rho_line": "LINE1",
            "is_rho_reduction": True,
            "affected_line": "PST_BRANCH_1",
            "action": MagicMock()
        }
    }
    
    with patch('expert_backend.services.recommender_service.sanitize_for_json', side_effect=lambda x: x):
        enriched = recommender._enrich_actions(prioritized_actions_dict)
        
        assert "pst_action" in enriched
        assert enriched["pst_action"]["affected_line"] == "PST_BRANCH_1"
        assert enriched["pst_action"]["max_rho_line"] == "LINE1"

def test_compute_superposition_merged_topology(recommender):
    """Verify that compute_superposition merges action_topology from both actions."""
    aid1, aid2 = "act1", "act2"
    
    # Mock actions with topology
    act1_obj = MagicMock()
    act1_obj.pst_tap = {"PST1": 2}
    act1_obj.lines_ex_bus = {"LINE1": 1}
    
    act2_obj = MagicMock()
    act2_obj.lines_ex_bus = {"LINE2": 1}
    act2_obj.substations = {"SUB1": 1}
    
    recommender._last_result["prioritized_actions"] = {
        aid1: {"action": act1_obj, "observation": MagicMock()},
        aid2: {"action": act2_obj, "observation": MagicMock()}
    }
    
    # Mock obs
    recommender._last_result["prioritized_actions"][aid1]["observation"].rho = np.array([0.9])
    recommender._last_result["prioritized_actions"][aid2]["observation"].rho = np.array([0.9])
    
    # Mock dependencies for compute_superposition
    recommender._get_simulation_env = MagicMock()
    recommender._get_n_variant = MagicMock(return_value="N")
    recommender._get_n1_variant = MagicMock(return_value="N-1")
    recommender._get_lines_we_care_about = MagicMock(return_value=None)
    
    env = recommender._get_simulation_env.return_value
    env.name_line = ["LINE1", "LINE2"]
    env.network_manager.network.get_working_variant_id.return_value = "ORIG"
    
    obs_start = MagicMock()
    obs_start.rho = np.array([1.1])
    env.get_obs.return_value = obs_start
    
    with patch('expert_backend.services.recommender_service._identify_action_elements', return_value=([0, 1], [])), \
         patch('expert_backend.services.recommender_service.compute_combined_pair_superposition') as mock_combine:
        
        mock_combine.return_value = {
            "betas": [0.5, 0.5],
            "p_or_combined": [100.0, 100.0]
        }
        
        result = recommender.compute_superposition(aid1, aid2, "contingency")
        
        assert "action_topology" in result
        topo = result["action_topology"]
        
        # Check merged fields
        assert "PST1" in topo["pst_tap"]
        assert "LINE1" in topo["lines_ex_bus"]
        assert "LINE2" in topo["lines_ex_bus"]
        assert "SUB1" in topo["substations"]

if __name__ == "__main__":
    pytest.main([__file__])
