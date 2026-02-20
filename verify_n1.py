import sys
import os
import grid2op
import pandas as pd
import pypowsybl as pp
import time
import json
from expert_op4grid_recommender.utils.make_env_utils import create_olf_rte_parameter

# Setup paths
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
# BACKEND_DIR = os.path.join(CURRENT_DIR, 'expert_backend')
# sys.path.append(BACKEND_DIR)
sys.path.append(CURRENT_DIR)

from expert_op4grid_recommender import config
from pathlib import Path

# Override ENV_PATH to backend data
config.ENV_PATH = Path('/home/marotant/dev/Expert_op4grid_recommender/data/bare_env_20240828T0100Z')

from expert_backend.services.recommender_service import RecommenderService

def verify_n1_convergence():
    print(f"Python executable: {sys.executable}")
    service = RecommenderService()
    
    # Load network
    print(f"Loading network from {config.ENV_PATH}...")
    n = service._load_network()
    
    # Check layout loading inside service (debug)
    layout_file = config.ENV_PATH / "grid_layout.json"
    print(f"Layout file exists? {layout_file.exists()}")
    
    disconnected_element = "P.SAOL31RONCI"
    print(f"\nRunning N-1 Analysis for {disconnected_element}...")
    
    # Simulate what get_n1_diagram does
    # Disconnect
    try:
        n.disconnect(disconnected_element)
    except Exception as e:
        print(f"Error disconnecting: {e}")
        return

    # AC Load Flow
    params = create_olf_rte_parameter()#pp.loadflow.Parameters()
    results = pp.loadflow.run_ac(n, params)
    
    status = results[0].status.name if results else "UNKNOWN"
    print(f"AC Load Flow Status: {status}")
    
    if status != 'CONVERGED':
        print("WARNING: Simulation did NOT converge despite new environment!")
    else:
        print("SUCCESS: Simulation CONVERGED.")
        
    # Generate Diagram
    print("\nGenerating Diagram...")
    # Using the current (reverted) RecommenderService code
    try:
        diagram = service._generate_diagram(n)
        svg = diagram.get('svg', '')
        
        if params is None or not svg:
             print("Error: No SVG generated.")
             return

        print(f"SVG Header: {svg[:300]}")
        
        if 'NaN' in svg or 'nan' in svg:
            # Check for geometry NaNs
            import re
            points_nans = list(re.finditer(r'points="[^"]*NaN', svg))
            value_nans = list(re.finditer(r'>\s*NaN', svg))
            
            if points_nans:
                print(f"ALERT: Found {len(points_nans)} Geometry NaNs (points=\"...NaN...)")
                pass 
            else:
                print("Geometry seems clean (no points=\"NaN\").")
                
            if value_nans:
                 print(f"ALERT: Found {len(value_nans)} Value NaNs (>NaN)")
            else:
                 print("Values seem clean (no >NaN).")
            
            # Check for dominant-baseline false positive
            # If only dominant-baseline, we are good?
            # actually we don't need to print dominant unless others are 0
            
            if not points_nans and not value_nans:
                 print("Conclusion: NaNs present but likely false positives (e.g. dominant-baseline).")
            else:
                 print("Conclusion: REAL NaNs detected.")
            
    except Exception as e:
        print(f"Error generating diagram: {e}")

if __name__ == "__main__":
    verify_n1_convergence()
