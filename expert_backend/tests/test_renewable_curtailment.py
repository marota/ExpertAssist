import pytest
import os
from unittest.mock import MagicMock, patch
from types import SimpleNamespace
from expert_backend.services.recommender_service import RecommenderService
from expert_op4grid_recommender import config

def test_compute_curtailment_details():
    service = RecommenderService()
    
    # Mock a generator disconnection action. 
    # The code expects action_data.get("action") to have "gens_bus"
    mock_action = MagicMock()
    mock_action.gens_bus = {"gen_1": -1}
    
    action_detail = {
        "action": mock_action,
        "disconnected_mw": 50.5
    }
    
    # Patch the network_service instance in its own module
    with patch("expert_backend.services.network_service.network_service") as mock_ns:
        mock_ns.get_generator_voltage_level.return_value = "VL1"
        
        # We need to mock _is_renewable_gen as well
        with patch.object(service, '_is_renewable_gen', return_value=True):
            details = service._compute_curtailment_details(action_detail)
            
        assert details is not None
        assert len(details) == 1
        assert details[0]["gen_name"] == "gen_1"
        assert details[0]["curtailed_mw"] == 50.5
        assert details[0]["voltage_level_id"] == "VL1"

def test_config_update_curtailment(tmp_path):
    service = RecommenderService()
    
    # Create dummy files to avoid FileNotFoundError
    mock_env = tmp_path / "mock_env"
    mock_env.mkdir()
    mock_actions = tmp_path / "mock_actions.json"
    mock_actions.write_text("{}")
    
    # Mock settings object as expected by update_config
    settings = SimpleNamespace(
        network_path=str(mock_env),
        action_file_path=str(mock_actions),
        min_line_reconnections=1,
        min_close_coupling=1,
        min_open_coupling=1,
        min_line_disconnections=1,
        n_prioritized_actions=10,
        min_renewable_curtailment_actions=7
    )
    
    # Mock network_service.network to avoid ValueError: Network not loaded
    with patch("expert_backend.services.network_service.network_service") as mock_ns:
        mock_ns.network = MagicMock()
        service.update_config(settings)
    
    # Verify it was passed to the global config
    assert config.MIN_RENEWABLE_CURTAILMENT_ACTIONS == 7
