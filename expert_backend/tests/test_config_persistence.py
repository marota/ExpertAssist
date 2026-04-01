# Copyright (c) 2025-2026, RTE (https://www.rte-france.com)
# This Source Code Form is subject to the terms of the Mozilla Public License, version 2.0.
# If a copy of the Mozilla Public License, version 2.0 was not distributed with this file,
# you can obtain one at http://mozilla.org/MPL/2.0/.
# SPDX-License-Identifier: MPL-2.0

import os
import json
import pytest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient

@pytest.fixture
def temp_config_env(tmp_path):
    """Set up a temporary config environment for testing persistence."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    
    config_path_file = project_root / "config_path.txt"
    config_default = project_root / "config.default.json"
    config_user = project_root / "config.json"
    
    # Create a default config
    default_data = {"network_path": "default_net", "min_pst": 1.0}
    config_default.write_text(json.dumps(default_data), encoding="utf-8")
    
    with patch("expert_backend.main._PROJECT_ROOT", project_root), \
         patch("expert_backend.main._CONFIG_DEFAULT", config_default), \
         patch("expert_backend.main._CONFIG_PATH_FILE", config_path_file):
        
        # We need to re-ensure config because main.py does it at import time, 
        # but here we are patching the paths after import.
        from expert_backend.main import _ensure_user_config
        _ensure_user_config()
        
        yield {
            "project_root": project_root,
            "config_path_file": config_path_file,
            "config_default": config_default,
            "config_user": config_user
        }

def test_config_path_persistence(temp_config_env):
    """Verify that changing the config path persists across 'sessions'."""
    from expert_backend.main import app
    client = TestClient(app)
    
    # 1. Initial path should be the default config.json
    res = client.get("/api/config-file-path")
    assert res.status_code == 200
    assert res.json()["config_file_path"].endswith("config.json")
    
    # 2. Change the path to a new custom file
    custom_path = temp_config_env["project_root"] / "custom_config.json"
    res = client.post("/api/config-file-path", json={"path": str(custom_path)})
    assert res.status_code == 200
    assert res.json()["config_file_path"] == str(custom_path)
    
    # 3. Verify config_path.txt was updated
    assert temp_config_env["config_path_file"].read_text().strip() == str(custom_path)
    
    # 4. Simulate a 'reload' by getting the path again
    res = client.get("/api/config-file-path")
    assert res.status_code == 200
    assert res.json()["config_file_path"] == str(custom_path)
    
    # 5. Verify that user-config now returns content from the custom file
    # (Since it was created from default, it should have default content initially)
    res = client.get("/api/user-config")
    assert res.status_code == 200
    assert res.json()["network_path"] == "default_net"
    
    # 6. Modify the custom config and verify it's saved there
    new_data = {"network_path": "custom_net", "min_pst": 2.0}
    res = client.post("/api/user-config", json=new_data)
    assert res.status_code == 200
    
    assert json.loads(custom_path.read_text())["network_path"] == "custom_net"

def test_config_switching_loads_new_content(temp_config_env):
    """Verify that switching back and forth between config files loads correct content."""
    from expert_backend.main import app
    client = TestClient(app)
    
    path1 = temp_config_env["project_root"] / "config1.json"
    path2 = temp_config_env["project_root"] / "config2.json"
    
    # Set path 1 and modify it
    client.post("/api/config-file-path", json={"path": str(path1)})
    client.post("/api/user-config", json={"network_path": "net1"})
    
    # Set path 2 and modify it
    client.post("/api/config-file-path", json={"path": str(path2)})
    client.post("/api/user-config", json={"network_path": "net2"})
    
    # Switch back to path 1
    res = client.post("/api/config-file-path", json={"path": str(path1)})
    assert res.json()["config"]["network_path"] == "net1"
    
    # Verify GET returns path 1 and net 1
    assert client.get("/api/config-file-path").json()["config_file_path"] == str(path1)
    assert client.get("/api/user-config").json()["network_path"] == "net1"
