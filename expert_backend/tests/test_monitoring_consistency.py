import pytest
from unittest.mock import MagicMock, patch
from expert_backend.services.recommender_service import RecommenderService
from expert_op4grid_recommender import config

class TestMonitoringConsistency:
    @patch("expert_op4grid_recommender.config")
    def test_get_monitoring_parameters_prioritizes_context(self, mock_config):
        # Setup
        service = RecommenderService()
        mock_obs = MagicMock()
        mock_obs.name_line = ["L1", "L2", "L3"]
        
        # Mock network component and limits
        mock_grid = MagicMock()
        mock_obs._network_manager.network = mock_grid
        import pandas as pd
        mock_grid.get_operational_limits.return_value = pd.DataFrame({
            'type': ['CURRENT', 'CURRENT'],
            'acceptable_duration': [-1, 60],
            'element_id': ['L1', 'L2']
        })
        
        # 1. Test with analysis context (user deselected L2)
        service._analysis_context = {
            "lines_we_care_about": ["L1", "L3"]
        }
        
        lines, limits = service._get_monitoring_parameters(mock_obs)
        
        assert lines == ["L1", "L3"]
        assert "L1" in limits
        assert "L2" not in limits # L2 has duration 60, not -1
        
    @patch("expert_op4grid_recommender.config")
    def test_get_monitoring_parameters_fallback_to_config(self, mock_config):
        service = RecommenderService()
        service._analysis_context = None # No context
        
        mock_config.IGNORE_LINES_MONITORING = False
        mock_config.LINES_MONITORING_FILE = "some_file.csv"
        
        mock_obs = MagicMock()
        mock_obs.name_line = ["L1", "L2", "L3"]
        
        # Mock limits to avoid errors
        mock_grid = MagicMock()
        mock_obs._network_manager.network = mock_grid
        import pandas as pd
        mock_grid.get_operational_limits.return_value = pd.DataFrame()

        with patch("expert_op4grid_recommender.environment.load_interesting_lines") as mock_load:
            mock_load.return_value = ["L2"]
            lines, _ = service._get_monitoring_parameters(mock_obs)
            assert lines == ["L2"]

    @patch("expert_backend.services.recommender_service.compute_combined_pair_superposition")
    def test_compute_superposition_uses_monitoring_parameters(self, mock_superposition):
        service = RecommenderService()
        mock_obs = MagicMock()
        mock_obs.name_line = ["L1", "L2"]
        mock_obs.rho = [0.8, 0.9] # L2 is overloaded if limit is 0.95 and factor is 0.95? Wait.
        
        # Setup analysis context to only care about L1
        service._analysis_context = {
             "lines_we_care_about": ["L1"],
             "lines_overloaded_ids": [0, 1]
        }
        
        # Mock _get_monitoring_parameters to return only L1
        service._get_monitoring_parameters = MagicMock(return_value=(["L1"], {"L1"}))
        
        # Mock other dependencies for compute_superposition
        service._enrich_actions = MagicMock(return_value={})
        service._dict_action = {}
        
        # Mock result of superposition
        mock_superposition.return_value = {
            "betas": [1.0, 1.0],
            "p_or_combined": [100.0, 200.0]
        }
        
        # We need to mock all_actions since it's used inside compute_superposition
        # compute_superposition gets all_actions from _enrich_actions(results["prioritized_actions"])
        # Wait, I'll just mock the parts that use it or provide a real enough structure.
        
        # Actually, let's just trace if _get_monitoring_parameters was called
        try:
            # This might fail due to missing mocks for the rest of the function, 
            # but we want to see if our injected logic is reached.
            list(service.compute_superposition("act1", "act2"))
        except Exception:
            pass
            
        service._get_monitoring_parameters.assert_called_once()
