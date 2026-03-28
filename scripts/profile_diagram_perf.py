import time
import json
import sys
import os
import argparse
from pathlib import Path
import cProfile
import pstats
import io

# Add the project root to sys.path so we can import expert_backend
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

from expert_backend.services.network_service import network_service
from expert_backend.services.recommender_service import recommender_service
from expert_op4grid_recommender import config as recommender_config

class Profiler:
    def __init__(self):
        self.timings = {}
        self.current_scenario = None

    def start_scenario(self, name):
        self.current_scenario = name
        self.timings[name] = {}
        print(f"\n>>> Starting Scenario: {name}")

    def time_block(self, name):
        return TimerContext(self, name)

class TimerContext:
    def __init__(self, profiler, name):
        self.profiler = profiler
        self.name = name
        self.start_time = None

    def __enter__(self):
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        end_time = time.perf_counter()
        elapsed = end_time - self.start_time
        self.profiler.timings[self.profiler.current_scenario][self.name] = elapsed
        print(f"  {self.name}: {elapsed:.4f}s")

def run_profiling(config_path, use_cprofile=False):
    p = Profiler()

    # Load config
    with open(config_path, 'r') as f:
        config_data = json.load(f)

    # --- Scenario 1: Load network & display N-state diagram ---
    p.start_scenario("1_InitialLoad_N_Diagram")
    
    with p.time_block("total_scenario_1"):
        with p.time_block("update_config"):
            from expert_backend.main import ConfigRequest
            req = ConfigRequest(**config_data)
            # Simulate the /api/config endpoint logic
            recommender_service.reset()
            network_service.load_network(req.network_path)
            recommender_service.update_config(req)
        
        with p.time_block("get_network_diagram"):
            with p.time_block("get_base_network"):
                n = recommender_service._get_base_network()
            
            with p.time_block("nad_generation"):
                # We time the internal _generate_diagram
                res = recommender_service.get_network_diagram()
            
            p.timings[p.current_scenario]["svg_size_bytes"] = len(res["svg"])
            p.timings[p.current_scenario]["metadata_size_bytes"] = len(json.dumps(res["metadata"]))
            print(f"  SVG size: {len(res['svg']) / 1024 / 1024:.2f} MB")

    # --- Scenario 2: Select contingency ---
    contingency_id = "P.SAOL31RONCI"
    p.start_scenario("2_ContingencySelection_N1_Diagram")
    
    with p.time_block("total_scenario_2"):
        with p.time_block("run_analysis_step1"):
            recommender_service.run_analysis_step1(contingency_id)
        
        with p.time_block("get_n1_diagram"):
            # This generates the N-1 diagram and computes flow deltas
            res_n1 = recommender_service.get_n1_diagram(contingency_id)
            
        p.timings[p.current_scenario]["svg_size_bytes"] = len(res_n1["svg"])
        print(f"  SVG size: {len(res_n1['svg']) / 1024 / 1024:.2f} MB")

    # --- Scenario 3: Simulate manual action ---
    # Manual action: "f344b395-9908-43c2-bca0-75c5f298465e_COUCHP6_coupling"
    action_id = "f344b395-9908-43c2-bca0-75c5f298465e_COUCHP6_coupling"
    
    p.start_scenario("3_ManualAction_Simulation_Diagram")
    
    with p.time_block("total_scenario_3"):
        with p.time_block("simulate_manual_action"):
            # This is the heavy simulation part
            sim_res = recommender_service.simulate_manual_action(action_id, contingency_id)
        
        with p.time_block("get_action_variant_diagram"):
            # This generates the post-action diagram and flow deltas
            res_act = recommender_service.get_action_variant_diagram(action_id)
            
        p.timings[p.current_scenario]["svg_size_bytes"] = len(res_act["svg"])
        print(f"  SVG size: {len(res_act['svg']) / 1024 / 1024:.2f} MB")

    # --- Output results ---
    output_file = Path("profiling_results.json")
    with open(output_file, 'w') as f:
        json.dump(p.timings, f, indent=4)
    print(f"\nProfiling results saved to {output_file}")

    # Summary table
    print("\n" + "="*50)
    print(f"{'Phase':<40} | {'Time (s)':>8}")
    print("-" * 50)
    for scenario, data in p.timings.items():
        print(f"\nScenario: {scenario}")
        for k, v in data.items():
            if isinstance(v, float):
                print(f"  {k:<38} | {v:>8.4f}")
    print("="*50)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Profile ExpertAssist diagram generation.")
    parser.add_argument("config", help="Path to the config JSON file")
    parser.add_argument("--cprofile", action="store_true", help="Run with cProfile")
    args = parser.parse_args()

    config_path = args.config
    if not os.path.exists(config_path):
        # Try relative to project root
        config_path = str(project_root / args.config)
        if not os.path.exists(config_path):
            print(f"Error: Config file not found: {args.config}")
            sys.exit(1)

    if args.cprofile:
        print("Running with cProfile...")
        pr = cProfile.Profile()
        pr.enable()
        run_profiling(config_path)
        pr.disable()
        s = io.StringIO()
        sortby = 'cumulative'
        ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
        ps.print_stats(30)
        print(s.getvalue())
        
        prof_file = "profiling.prof"
        pr.dump_stats(prof_file)
        print(f"Detailed profile saved to {prof_file}")
    else:
        run_profiling(config_path)
