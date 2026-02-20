import requests
import json
import time

API_URL = "http://localhost:8000"
NETWORK_PATH = "/home/marotant/dev/Expert_op4grid_recommender/data/bare_env_20240828T0100Z"
ACTION_PATH = "/home/marotant/dev/Expert_op4grid_recommender/data/action_space/AllFrance_coupling_reco_deco_actions_20240828T0100Z.json"
TARGET_ID = "P.SAOL31RONCI" # Known element on Large Grid

def test_sub_network():
    # 1. Initialize Config
    print("Initializing config...")
    res = requests.post(f"{API_URL}/api/config", json={
        "network_path": NETWORK_PATH,
        "action_file_path": ACTION_PATH
    })
    
    if res.status_code != 200:
        print(f"Config failed: {res.text}")
        return

    print("Config initialized.")
    
    # 2. Request Sub-Network Diagram
    print(f"Requesting sub-network for {TARGET_ID}...")
    start = time.time()
    res = requests.post(f"{API_URL}/api/sub-network-diagram", json={
        "target_id": TARGET_ID,
        "depth": 1
    })
    duration = time.time() - start
    
    if res.status_code == 200:
        data = res.json()
        print(f"Success! Request took {duration:.2f}s")
        if "svg" in data:
            print(f"SVG Length: {len(data['svg'])} chars")
            print(f"SVG Start: {data['svg'][:100]}...")
        if "metadata" in data:
            print("Metadata received.")
            # Check if metadata makes sense (should be small)
            try:
                if isinstance(data['metadata'], str):
                    meta = json.loads(data['metadata'])
                else:
                    meta = data['metadata']
                print(f"Nodes in sub-network: {len(meta.get('nodes', []))}")
                print(f"Edges in sub-network: {len(meta.get('edges', []))}")
            except: 
                print("Could not parse metadata")
    else:
        print(f"Failed: {res.status_code} - {res.text}")

if __name__ == "__main__":
    try:
        test_sub_network()
    except Exception as e:
        print(f"Error: {e}")
        print("Is the backend server running?")
