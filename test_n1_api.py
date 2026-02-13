import requests
import json
import sys

API_BASE = 'http://localhost:8000'

def test_n1_api():
    print(f"Testing {API_BASE}/api/n1-diagram...")
    try:
        # 1. Load Config
        print("Loading config...")
        network_path = '/home/marotant/dev/Expert_op4grid_recommender/data/bare_env_20240828T0100Z_dijon_only'
        action_path = '/home/marotant/dev/Expert_op4grid_recommender/data/action_space/reduced_model_actions_20240828T0100Z_new_dijon.json'
        
        res = requests.post(f"{API_BASE}/api/config", json={
            "network_path": network_path,
            "action_file_path": action_path
        })
        if res.status_code != 200:
            print(f"Failed to load config: {res.text}")
            return False

        # 2. Get Branches to pick a valid one
        print("Fetching branches...")
        res = requests.get(f"{API_BASE}/api/branches")
        if res.status_code != 200:
            print(f"Failed to fetch branches: {res.text}")
            return False
            
        branches = res.json().get("branches", [])
        if not branches:
            print("No branches found.")
            return False
            
        target = branches[0]
        print(f"Selected target for N-1: {target}")

        # 3. Call N-1 Endpoint
        print(f"Requesting N-1 diagram for {target}...")
        res = requests.post(f"{API_BASE}/api/n1-diagram", json={"disconnected_element": target})
        
        if res.status_code == 200:
            data = res.json()
            svg = data.get("svg", "")
            meta = data.get("metadata", "")
            
            print(f"Success! Received N-1 diagram.")
            print(f"SVG Length: {len(svg)} chars")
            print(f"Metadata Length: {len(str(meta))} chars")
            
            if len(svg) > 100 and meta:
                return True
            else:
                print("Warning: SVG too short or metadata missing.")
                return False
        else:
            print(f"Failed to fetch N-1 diagram: {res.status_code} - {res.text}")
            return False
            
    except Exception as e:
        print(f"Test failed with exception: {e}")
        return False

if __name__ == "__main__":
    success = test_n1_api()
    sys.exit(0 if success else 1)
