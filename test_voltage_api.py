import requests
import json
import sys

API_BASE = 'http://localhost:8000'

def test_voltage_levels():
    print(f"Testing {API_BASE}/api/voltage-levels...")
    try:
        # First ensure a network is loaded (using default path from code or environment)
        # We can try to load the config first to be safe, using the path from previous steps
        network_path = '/home/marotant/dev/Expert_op4grid_recommender/data/bare_env_20240828T0100Z_dijon_only'
        action_path = '/home/marotant/dev/Expert_op4grid_recommender/data/action_space/reduced_model_actions_20240828T0100Z_new_dijon.json'
        
        print("Loading config...")
        res = requests.post(f"{API_BASE}/api/config", json={
            "network_path": network_path,
            "action_file_path": action_path
        })
        if res.status_code != 200:
            print(f"Failed to load config: {res.text}")
            return False
            
        print("Config loaded. Fetching voltage levels...")
        res = requests.get(f"{API_BASE}/api/voltage-levels")
        
        if res.status_code == 200:
            data = res.json()
            vls = data.get("voltage_levels", [])
            print(f"Success! Found {len(vls)} voltage levels.")
            if len(vls) > 0:
                print("First 5 voltage levels:", vls[:5])
                
                # Verify specific known VL from previous metadata inspection
                known_vl = "1GEN.P7"
                if known_vl in vls:
                    print(f"Verified: Known voltage level '{known_vl}' is present.")
                else:
                    print(f"Warning: Known voltage level '{known_vl}' NOT found.")
            return True
        else:
            print(f"Failed to fetch voltage levels: {res.status_code} - {res.text}")
            return False
            
    except Exception as e:
        print(f"Test failed with exception: {e}")
        return False

if __name__ == "__main__":
    success = test_voltage_levels()
    sys.exit(0 if success else 1)
