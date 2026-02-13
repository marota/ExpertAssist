import pypowsybl as pp
import json
import pandas as pd
from pypowsybl.network import NadParameters
from pypowsybl_jupyter.util import _get_svg_metadata
import sys
from pathlib import Path

# Path to the grid file
grid_path = "/home/marotant/dev/Expert_op4grid_recommender/data/bare_env_20240828T0100Z_dijon_only/grid.xiidm"
layout_path = "/home/marotant/dev/Expert_op4grid_recommender/data/bare_env_20240828T0100Z_dijon_only/grid_layout.json"

print(f"Loading network from {grid_path}...")
try:
    n = pp.network.load(grid_path)
except Exception as e:
    print(f"Error loading network: {e}")
    sys.exit(1)

# Load layout if available
df_layout = None
if Path(layout_path).exists():
    try:
        with open(layout_path, 'r') as f:
            layout_data = json.load(f)
        records = []
        for node_id, coords in layout_data.items():
            records.append({'id': node_id, 'x': coords[0], 'y': coords[1]})
        df_layout = pd.DataFrame(records).set_index('id')
        print("Loaded layout data.")
    except Exception as e:
        print(f"Warning: Could not load layout: {e}")

# Generate diagram with default parameters used in recommender_service.py
# Note: Replicating parameters from recommender_service.py
npars = NadParameters(
    edge_name_displayed=False,
    id_displayed=False,
    edge_info_along_edge=True,
    power_value_precision=1,
    angle_value_precision=0,
    current_value_precision=1,
    voltage_value_precision=0,
    bus_legend=True,
    substation_description_displayed=True
)

print("Generating network area diagram...")
diagram = n.get_network_area_diagram(
    nad_parameters=npars,
    fixed_positions=df_layout
)

print("Extracting metadata...")
metadata_json = _get_svg_metadata(diagram)

if metadata_json:
    metadata = json.loads(metadata_json)
    print("\nMetadata Keys:", metadata.keys())
    
    if 'nodes' in metadata:
        print("\nFirst 2 nodes:")
        print(json.dumps(metadata['nodes'][:2], indent=2))
        
        # Check if voltage level ID is present in nodes
        print("\nChecking for voltage level info in nodes...")
        sample_node = metadata['nodes'][0] if metadata['nodes'] else {}
        print("Sample node keys:", sample_node.keys())

    if 'edges' in metadata:
        print("\nFirst 2 edges:")
        print(json.dumps(metadata['edges'][:2], indent=2))

    # Check for other potential keys related to voltage levels
    # Voltage Levels are usually groupings of buses/nodes
    
    # Let's see if we can find voltage level IDs in the network
    voltage_levels = n.get_voltage_levels()
    print(f"\nFound {len(voltage_levels)} voltage levels in the network.")
    if not voltage_levels.empty:
        vl_id = voltage_levels.index[0]
        print(f"Sample Voltage Level ID: {vl_id}")
        
        # Check if this ID appears in the metadata string
        if vl_id in metadata_json:
            print(f"Voltage Level ID '{vl_id}' FOUND in metadata!")
        else:
            print(f"Voltage Level ID '{vl_id}' NOT found in metadata.")
            
else:
    print("No metadata found.")
