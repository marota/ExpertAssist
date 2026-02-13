
import requests
import json
import time

def test_stream():
    url = "http://localhost:8000/run-analysis"
    payload = {
        "disconnected_element": "P.SAOL31RONCI"
    }
    
    print(f"Calling {url} with {payload}...")
    try:
        with requests.post(url, json=payload, stream=True) as r:
            if r.status_code != 200:
                print(f"Error: Status code {r.status_code}")
                print(r.text)
                return

            for line in r.iter_lines():
                if line:
                    event = json.loads(line.decode('utf-8'))
                    print(f"Received event: {event.get('type')} - {event.get('pdf_url') or event.get('pdf_path')}")
                    if event.get('type') == 'result':
                        print(f"Actions found: {len(event.get('actions', {}))}")
                        print(f"Message: {event.get('message')}")
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    # Ensure backend is configured
    config_url = "http://localhost:8000/config"
    config_payload = {
        "network_path": "/home/marotant/dev/Expert_op4grid_recommender/data/bare_env_20240828T0100Z_dijon_only",
        "action_file_path": "/home/marotant/dev/Expert_op4grid_recommender/data/action_space/reduced_model_actions_20240828T0100Z_new_dijon.json"
    }
    print(f"Configuring backend: {config_payload['network_path']}")
    requests.post(config_url, json=config_payload)
    
    test_stream()
