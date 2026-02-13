
import os
import sys
from pathlib import Path

# Add the package to the path if needed
sys.path.insert(0, os.path.abspath("."))

from expert_op4grid_recommender import config
from expert_op4grid_recommender.main import run_analysis, Backend

# CONFIGURATION
NETWORK_PATH = "/home/marotant/dev/Expert_op4grid_recommender/data/bare_env_20240828T0100Z"
ACTION_FILE = "/home/marotant/dev/Expert_op4grid_recommender/data/action_space/AllFrance_coupling_reco_deco_actions_20240828T0100Z.json"
CONTINGENCY = "P.SAOL31RONCI"
TIMESTEP = 0

def reproduce():
    print(f"Reproducing stuck analysis for {CONTINGENCY}...")
    
    # 1. Setup config
    path_obj = Path(NETWORK_PATH)
    config.ENV_NAME = path_obj.name
    config.ENV_FOLDER = path_obj.parent
    config.ENV_PATH = path_obj
    config.ACTION_FILE_PATH = Path(ACTION_FILE)
    config.DO_VISUALIZATION = True
    config.SAVE_FOLDER_VISUALIZATION = Path(os.getcwd()) / "stuck_repro_visu"
    config.CHECK_ACTION_SIMULATION=False
    
    # Ensure save folder exists
    config.SAVE_FOLDER_VISUALIZATION.mkdir(parents=True, exist_ok=True)
    
    print(f"Using backend: PYPOWSYBL (RTE)")
    print(f"Data: {NETWORK_PATH}")
    print(f"Contingency: {CONTINGENCY}")

    try:
        result = run_analysis(
            analysis_date=None,
            current_timestep=TIMESTEP,
            current_lines_defaut=[CONTINGENCY],
            backend=Backend.PYPOWSYBL
        )
        print("Analysis finished successfully!")
        print(f"Result keys: {result.keys() if result else 'None'}")
    except Exception as e:
        print(f"Analysis failed with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    reproduce()
