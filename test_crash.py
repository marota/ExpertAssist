import asyncio
import sys

from expert_backend.main import ConfigRequest, update_config

config = ConfigRequest(
    network_path="/home/marotant/dev/Expert_op4grid_recommender/data/bare_env_small_grid_test/grid.xiidm",
    action_file_path="/home/marotant/dev/Expert_op4grid_recommender/data/action_space/All_France_actions_from_REPAS.2024.12.10_withPSTs.json",
    layout_path="/home/marotant/dev/Expert_op4grid_recommender/data/bare_env_small_grid_test/grid_layout.json"
)

try:
    res = update_config(config)
    print("SUCCESS", res)
except Exception as e:
    import traceback
    traceback.print_exc()
    sys.exit(1)
