
import sys
import os
from pathlib import Path

# Add project root to sys.path
sys.path.append("/home/marotant/dev/AntiGravity/ExpertAssist")

import expert_op4grid_recommender
from expert_op4grid_recommender import config
from expert_op4grid_recommender.main import Backend, run_analysis

def reproduce():
    network_path = "/home/marotant/dev/Expert_op4grid_recommender/data/bare_env_20241125T1400Z"
    action_file_path = "/home/marotant/dev/Expert_op4grid_recommender/data/action_space/AllFrance_coupling_reco_deco_actions_20241125T1400Z.json"
    disconnected_element = "BEON L31CPVAN"

    # Setup config similar to RecommenderService.update_config
    path_obj = Path(network_path)
    config.ENV_NAME = path_obj.name
    config.ENV_FOLDER = path_obj.parent
    config.ENV_PATH = path_obj
    config.ACTION_FILE_PATH = Path(action_file_path)
    config.DO_VISUALIZATION = True
    config.USE_DC_LOAD_FLOW = False
    config.SAVE_FOLDER_VISUALIZATION = Path(os.getcwd()) / "repro_visu"
    
    if not os.path.exists(config.SAVE_FOLDER_VISUALIZATION):
        os.makedirs(config.SAVE_FOLDER_VISUALIZATION)

    print(f"Running analysis for {disconnected_element} at timestep 9...")
    try:
        result = run_analysis(
            analysis_date=None,
            current_timestep=9,
            current_lines_defaut=[disconnected_element],
            backend=Backend.PYPOWSYBL
        )
        print("Analysis successful!")
        print(f"Result keys: {result.keys() if result else 'None'}")
    except Exception as e:
        print("Analysis failed with error:")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    reproduce()
