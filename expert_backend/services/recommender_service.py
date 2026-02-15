import expert_op4grid_recommender
from expert_op4grid_recommender import config
from expert_op4grid_recommender.main import Backend, run_analysis
import os
import glob
from pathlib import Path
import numpy as np

def sanitize_for_json(obj):
    if isinstance(obj, (np.integer, int)):
        return int(obj)
    elif isinstance(obj, (np.floating, float)):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return sanitize_for_json(obj.tolist())
    elif isinstance(obj, dict):
        return {str(k): sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [sanitize_for_json(i) for i in obj]
    elif isinstance(obj, (str, bool, type(None))):
        return obj
    else:
        # Fallback for unknown objects
        try:
            # Try to get dict representation
            if hasattr(obj, "to_dict"):
                return sanitize_for_json(obj.to_dict())
            return sanitize_for_json(vars(obj))
        except TypeError:
            return str(obj)

class RecommenderService:
    def __init__(self):
        pass

    def update_config(self, network_path: str, action_file_path: str):
        # Update the global config of the package
        path_obj = Path(network_path)
        config.ENV_NAME = path_obj.name
        config.ENV_FOLDER = path_obj.parent
        config.ENV_PATH = path_obj
        
        config.ACTION_FILE_PATH = Path(action_file_path)
        
        # Inject missing config parameter and redirect output
        config.DO_VISUALIZATION = True
        # Don't check all actions
        config.CHECK_ACTION_SIMULATION = False

        # Set visualization output to local 'Overflow_Graph' directory in backend/
        # uvicorn runs from root, so 'Overflow_Graph' in CWD
        config.SAVE_FOLDER_VISUALIZATION = Path(os.getcwd()) / "Overflow_Graph"
        if not config.SAVE_FOLDER_VISUALIZATION.exists():
            config.SAVE_FOLDER_VISUALIZATION.mkdir(parents=True, exist_ok=True)

    def run_analysis(self, disconnected_element: str):
        import io
        import time
        import threading
        import queue
        from contextlib import redirect_stdout
        import re

        analysis_start_time = time.time()
        shared_state = {
            "analysis_message": "Analysis completed successfully using AC Load Flow.",
            "dc_fallback_used": False,
            "result": None,
            "output": "",
            "error": None,
            "done": False,
            "latest_pdf": None
        }
        
        save_folder = config.SAVE_FOLDER_VISUALIZATION

        def find_latest_pdf():
            pdfs = glob.glob(os.path.join(save_folder, "*.pdf"))
            if not pdfs: return None
            # Only consider PDFs modified after we started
            # Use a tiny offset (1s) to be safe against filesystem drift
            recent_pdfs = [p for p in pdfs if os.path.getmtime(p) >= (analysis_start_time - 1.0)]
            if not recent_pdfs: return None
            return max(recent_pdfs, key=os.path.getmtime)

        def _worker():
            try:
                # Attempt 1: AC
                config.USE_DC_LOAD_FLOW = False
                f_stdout = io.StringIO()
                with redirect_stdout(f_stdout):
                    res = run_analysis(
                        analysis_date=None,
                        current_timestep=0,
                        current_lines_defaut=[disconnected_element],
                        backend=Backend.PYPOWSYBL
                    )
                shared_state["result"] = res
                shared_state["output"] = f_stdout.getvalue()
            except RuntimeError as e:
                # Catch convergence error and try DC
                if "Initial contingency simulation failed" in str(e):
                    try:
                        config.USE_DC_LOAD_FLOW = True
                        shared_state["dc_fallback_used"] = True
                        shared_state["analysis_message"] = "Warning: AC Load Flow did not converge. Fallback to DC Load Flow was used."
                        f_stdout = io.StringIO()
                        with redirect_stdout(f_stdout):
                            res = run_analysis(
                                analysis_date=None,
                                current_timestep=0,
                                current_lines_defaut=[disconnected_element],
                                backend=Backend.PYPOWSYBL
                            )
                        shared_state["result"] = res
                        shared_state["output"] = f_stdout.getvalue()
                    except Exception as inner_e:
                        shared_state["error"] = RuntimeError(f"Analysis failed globally (AC and DC): {inner_e}")
                else:
                    shared_state["error"] = e
            except Exception as e:
                shared_state["error"] = e
            finally:
                shared_state["done"] = True

        thread = threading.Thread(target=_worker)
        thread.start()

        pdf_sent = False
        while not shared_state["done"]:
            # Check for PDF
            if not pdf_sent:
                latest = find_latest_pdf()
                if latest:
                    shared_state["latest_pdf"] = latest
                    yield {"type": "pdf", "pdf_path": str(latest)}
                    pdf_sent = True
            
            if shared_state["error"]:
                raise shared_state["error"]
            
            time.sleep(0.5)

        # Final check for error
        if shared_state["error"]:
            raise shared_state["error"]

        # Final check for PDF if not sent during loop
        if not pdf_sent:
            latest = find_latest_pdf()
            if latest:
                shared_state["latest_pdf"] = latest
                yield {"type": "pdf", "pdf_path": str(latest)}
                pdf_sent = True

        result = shared_state["result"]
        output = shared_state["output"]
        analysis_message = shared_state["analysis_message"]
        dc_fallback_used = shared_state["dc_fallback_used"]

        # Parse rho values from output
        rho_info = {}
        current_action_id = None
        lines = output.split('\n')
        for i, line in enumerate(lines):
            line = line.strip()
            if not line: continue
            if result and line in result:
                current_action_id = line
            if "✅ Rho reduction" in line and current_action_id:
                match = re.search(r"Rho reduction from \[(.*?)\] to \[(.*?)\]. New max rho is (.*?) on line (.*)\.", line)
                if match:
                    rho_info[current_action_id] = {
                        "old_rho": match.group(1),
                        "new_rho": match.group(2),
                        "new_max_rho": float(match.group(3)),
                        "max_rho_line": match.group(4)
                    }

        # Load action descriptions
        action_descriptions = {}
        try:
            if hasattr(config, 'ACTION_FILE_PATH') and config.ACTION_FILE_PATH.exists():
                import json
                with open(config.ACTION_FILE_PATH, 'r') as f:
                    action_descriptions = json.load(f)
        except Exception as e:
            print(f"Warning: Could not load action descriptions: {e}")

        if result is None:
            if "No topological solution without load shedding" in output:
                analysis_message = "No topological solution found without load shedding. The grid might be too constrained."
            elif "Overload breaks the grid apart" in output:
                analysis_message = "Grid instability detected: Overload breaks the grid apart."
            else:
                analysis_message = "Analysis finished but no recommendations were found."
            enriched_actions = {}
        else:
            enriched_actions = {}
            raw_actions = sanitize_for_json(result)
            if isinstance(raw_actions, dict):
                 for action_id, action_data in raw_actions.items():
                     enriched_data = action_data.copy() if isinstance(action_data, dict) else {"data": action_data}
                     item = None
                     if action_id in action_descriptions:
                         item = action_descriptions[action_id]
                     else:
                         possible_matches = [k for k in action_descriptions.keys() if k.lower() == action_id.lower()]
                         if possible_matches:
                             item = action_descriptions[possible_matches[0]]
                         else:
                             sub_match = re.search(r"_([A-Z0-9.]+?)$", action_id)
                             if sub_match:
                                 sub_name = sub_match.group(1)
                                 matching_sub_keys = [k for k in action_descriptions.keys() if k.endswith(f"_{sub_name}")]
                                 if matching_sub_keys:
                                     item = action_descriptions[matching_sub_keys[0]]
                             
                             if not item and action_id.startswith("reco_"):
                                 stripped_reco = action_id[5:]
                                 if stripped_reco in action_descriptions:
                                     item = action_descriptions[stripped_reco]
                                 else:
                                     possible_matches = [k for k in action_descriptions.keys() if k.lower() == stripped_reco.lower()]
                                     if possible_matches:
                                         item = action_descriptions[possible_matches[0]]

                     if item:
                         desc = item.get("description", "")
                         desc_unit = item.get("description_unitaire", "")
                         enriched_data["description"] = desc
                         enriched_data["description_unitaire"] = desc_unit if desc_unit else desc
                     else:
                         enriched_data["description"] = "No description available"
                         enriched_data["description_unitaire"] = "No description available"
                     
                     if action_id in rho_info:
                         enriched_data.update(rho_info[action_id])
                     enriched_actions[action_id] = enriched_data

        yield {
            "type": "result",
            "pdf_path": str(shared_state["latest_pdf"]) if shared_state["latest_pdf"] else None,
            "actions": enriched_actions,
            "message": analysis_message,
            "dc_fallback": dc_fallback_used
        }

    def _load_network(self):
        """Load and return a pypowsybl network from config path."""
        import pypowsybl as pp

        network_file = config.ENV_PATH / "grid.xiidm"
        if not network_file.exists():
            xiidm_files = list(config.ENV_PATH.glob("*.xiidm"))
            if xiidm_files:
                network_file = xiidm_files[0]
            else:
                raise FileNotFoundError(f"Network file not found in {config.ENV_PATH}")
        return pp.network.load(str(network_file))

    def _load_layout(self):
        """Load layout DataFrame from grid_layout.json if available."""
        import pandas as pd
        import json

        layout_file = config.ENV_PATH / "grid_layout.json"
        if layout_file.exists():
            try:
                with open(layout_file, 'r') as f:
                    layout_data = json.load(f)
                records = [{'id': k, 'x': v[0], 'y': v[1]} for k, v in layout_data.items()]
                return pd.DataFrame(records).set_index('id')
            except Exception as e:
                print(f"Warning: Could not load layout: {e}")
        return None

    def _default_nad_parameters(self):
        """Return default NadParameters for diagram generation."""
        from pypowsybl.network import NadParameters
        return NadParameters(
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

    def _generate_diagram(self, network, voltage_level_ids=None, depth=0):
        """Generate NAD and return svg + metadata dict.

        Args:
            network: pypowsybl network object
            voltage_level_ids: list of VL IDs to center on (None = full grid)
            depth: number of hops from center VLs to include
        """
        from pypowsybl_jupyter.util import _get_svg_string, _get_svg_metadata

        df_layout = self._load_layout()
        npars = self._default_nad_parameters()

        kwargs = dict(nad_parameters=npars)
        if df_layout is not None:
            kwargs['fixed_positions'] = df_layout
        if voltage_level_ids is not None:
            kwargs['voltage_level_ids'] = voltage_level_ids
            kwargs['depth'] = depth

        diagram = network.get_network_area_diagram(**kwargs)

        return {
            "svg": _get_svg_string(diagram),
            "metadata": _get_svg_metadata(diagram),
        }

    def get_network_diagram(self, voltage_level_ids=None, depth=0):
        n = self._load_network()
        return self._generate_diagram(n, voltage_level_ids=voltage_level_ids, depth=depth)

    def get_n1_diagram(self, disconnected_element: str, voltage_level_ids=None, depth=0):
        import pypowsybl as pp

        n = self._load_network()

        try:
            n.disconnect(disconnected_element)
        except Exception as e:
            raise ValueError(f"Failed to disconnect element {disconnected_element}: {e}")

        params = pp.loadflow.Parameters()
        results = pp.loadflow.run_ac(n, params)

        # Fall back to DC if AC didn't converge (matches run_analysis pattern)
        converged = any(r.status.name == 'CONVERGED' for r in results)
        if not converged:
            print(f"Warning: AC load flow did not converge for N-1 ({disconnected_element}), falling back to DC")
            pp.loadflow.run_dc(n, params)

        return self._generate_diagram(n, voltage_level_ids=voltage_level_ids, depth=depth)

recommender_service = RecommenderService()
