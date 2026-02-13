import pypowsybl as pp
import json
import pandas as pd
from pypowsybl.network import NadParameters
from pypowsybl_jupyter.util import _get_svg_metadata
import sys
from pathlib import Path
import os

grid_path = "/home/marotant/dev/Expert_op4grid_recommender/data/bare_env_20240828T0100Z_dijon_only/grid.xiidm"
layout_path = "/home/marotant/dev/Expert_op4grid_recommender/data/bare_env_20240828T0100Z_dijon_only/grid_layout.json"

print(f"Loading network from {grid_path}...")
try:
    n = pp.network.load(grid_path)
    print("Network loaded.")
except Exception as e:
    print(f"Error loading network: {e}")
    sys.exit(1)

lines = n.get_lines()
if lines.empty:
    print("No lines found!")
    sys.exit(1)
    
target_line_id = lines.index[0]
print(f"Targeting line for disconnection: {target_line_id}")

print("Disconnecting line...")
try:
    # Try the disconnect method
    # Usually: n.disconnect(id, element_type='LINE')?
    # Or just n.disconnect(id) if ID is unique?
    # Let's try guessing signature or check if it needs args.
    # Based on pypowsybl docs it might be disconnect(id)
    n.disconnect(target_line_id)
    print(f"Successfully disconnected {target_line_id}")
    
    # Run LoadFlow
    print("Running AC LoadFlow...")
    params = pp.loadflow.Parameters()
    results = pp.loadflow.run_ac(n, params)
    print("LoadFlow run complete.")
    for result in results:
        print(f"LoadFlow Status: {result.status}")

    # Generate Diagram
    print("Generating N-1 diagram...")
    
    # Load layout if available
    df_layout = None
    if Path(layout_path).exists():
        with open(layout_path, 'r') as f:
            layout_data = json.load(f)
        records = []
        for node_id, coords in layout_data.items():
            records.append({'id': node_id, 'x': coords[0], 'y': coords[1]})
        df_layout = pd.DataFrame(records).set_index('id')

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
    
    diagram = n.get_network_area_diagram(
        nad_parameters=npars,
        fixed_positions=df_layout
    )
    
    # Check if we can find metadata indicating disconnection?
    # Or just check size of svg
    svg = diagram.document.to_string() # Internal method? No, usually helper.
    # The helper _get_svg_string uses _repr_svg_()
    svg_str = diagram._repr_svg_()
    print(f"Generated SVG size: {len(svg_str)} bytes")
    
except Exception as e:
    print(f"Error during N-1 simulation: {e}")
    import traceback
    traceback.print_exc()

# Create a minimal N-1 endpoint simulation in python directly
