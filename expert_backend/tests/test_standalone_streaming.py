import httpx
import json
import time

def test_analysis_full_sequence_no_gzip():
    base_url = "http://localhost:8000/api"
    config_payload = {
        "network_path": "/home/marotant/dev/Expert_op4grid_recommender/data/bare_env_small_grid_test/grid.xiidm",
        "action_file_path": "/home/marotant/dev/Expert_op4grid_recommender/data/action_space/All_France_actions_from_REPAS.2024.12.10_withPSTs.json",
        "layout_path": "/home/marotant/dev/Expert_op4grid_recommender/data/bare_env_small_grid_test/grid_layout.json"
    }
    contingency = "P.SAOL31RONCI"
    
    with httpx.Client(timeout=30.0) as client:
        # 1. Config
        print(f"[Test] Configuring study...")
        r = client.post(f"{base_url}/config", json=config_payload)
        assert r.status_code == 200
        
        # 2. Step 1
        print(f"[Test] Running Analysis Step 1 for {contingency}...")
        r = client.post(f"{base_url}/run-analysis-step1", json={"disconnected_element": contingency})
        assert r.status_code == 200
        step1_data = r.json()
        overloads = step1_data.get("lines_overloaded", [])
        print(f"[Test] Step 1 done. Overloads: {len(overloads)}")
        
        # 3. Step 2 (Streaming)
        print(f"[Test] Running Analysis Step 2 (Streaming)...")
        start_time = time.time()
        with client.stream("POST", f"{base_url}/run-analysis-step2", json={
            "selected_overloads": overloads,
            "all_overloads": overloads,
            "monitor_deselected": False
        }) as response:
            assert response.status_code == 200
            
            # CRITICAL CHECK: Content-Encoding should NOT be gzip for streaming reliability
            ce = response.headers.get("Content-Encoding", "").lower()
            print(f"[Test] Content-Encoding: {ce if ce else 'None'}")
            assert "gzip" not in ce, "FATAL: GZip is enabled on the streaming route, which may cause buffering!"
            
            pdf_event_received = False
            for line in response.iter_lines():
                if not line.strip():
                    continue
                
                elapsed = time.time() - start_time
                event = json.loads(line)
                print(f"[Test] Event received at {elapsed:.2f}s: {event['type']}")
                
                if event["type"] == "pdf":
                    pdf_event_received = True
                    print(f"[Test] SUCCESS: PDF event received at {elapsed:.2f}s")
                    # On small grid, this should be very fast (< 1s locally)
                    assert elapsed < 5.0, f"PDF event arrival too slow: {elapsed:.2f}s"
                    break
            
            assert pdf_event_received, "PDF event was not received in the stream"

if __name__ == "__main__":
    try:
        test_analysis_full_sequence_no_gzip()
        print("\n[Test] ALL CHECKS PASSED: Streaming is fast and unbuffered.")
    except Exception as e:
        print(f"\n[Test] FAILED: {str(e)}")
        exit(1)
