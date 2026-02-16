import expert_op4grid_recommender
from expert_op4grid_recommender import config
from expert_op4grid_recommender.main import Backend, run_analysis
from expert_op4grid_recommender.utils.make_env_utils import create_olf_rte_parameter
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
        self._last_result = None
        self._last_disconnected_element = None

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
        from contextlib import redirect_stdout

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

        # Store the full result for later action variant diagram generation
        self._last_result = result
        self._last_disconnected_element = disconnected_element

        if result is None:
            if "No topological solution without load shedding" in output:
                analysis_message = "No topological solution found without load shedding. The grid might be too constrained."
            elif "Overload breaks the grid apart" in output:
                analysis_message = "Grid instability detected: Overload breaks the grid apart."
            else:
                analysis_message = "Analysis finished but no recommendations were found."
            enriched_actions = {}
            lines_overloaded = []
        else:
            lines_overloaded = result.get("lines_overloaded_names", [])
            prioritized = result.get("prioritized_actions", {})

            enriched_actions = {}
            for action_id, action_data in prioritized.items():
                enriched_actions[action_id] = {
                    "description_unitaire": action_data.get("description_unitaire") or "No description available",
                    "rho_before": sanitize_for_json(action_data.get("rho_before")),
                    "rho_after": sanitize_for_json(action_data.get("rho_after")),
                    "max_rho": sanitize_for_json(action_data.get("max_rho")),
                    "max_rho_line": action_data.get("max_rho_line", ""),
                    "is_rho_reduction": bool(action_data.get("is_rho_reduction", False)),
                }

        yield {
            "type": "result",
            "pdf_path": str(shared_state["latest_pdf"]) if shared_state["latest_pdf"] else None,
            "actions": enriched_actions,
            "lines_overloaded": sanitize_for_json(lines_overloaded),
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

        params = create_olf_rte_parameter()#pp.loadflow.Parameters()
        results = pp.loadflow.run_ac(n, params)

        # Check convergence — partial AC results are still better than DC
        # (DC only computes angles/power, not voltage magnitudes).
        converged = any(r.status.name == 'CONVERGED' for r in results)
        lf_status = results[0].status.name if results else "UNKNOWN"
        if not converged:
            print(f"Warning: AC load flow did not converge for N-1 ({disconnected_element}): {lf_status}")

        diagram = self._generate_diagram(n, voltage_level_ids=voltage_level_ids, depth=depth)
        diagram["lf_converged"] = converged
        diagram["lf_status"] = lf_status
        return diagram

    def get_action_variant_diagram(self, action_id, voltage_level_ids=None, depth=0):
        """Generate a NAD showing the network state after applying a remedial action.

        Uses the observation stored from the last analysis run to determine
        which lines are disconnected in the post-action state, then replays
        those disconnections on a fresh pypowsybl network.
        """
        import pypowsybl as pp

        if not self._last_result or not self._last_result.get("prioritized_actions"):
            raise ValueError("No analysis result available. Run analysis first.")

        actions = self._last_result["prioritized_actions"]
        if action_id not in actions:
            raise ValueError(f"Action '{action_id}' not found in last analysis result.")

        obs = actions[action_id]["observation"]

        n = self._load_network()

        # Apply line statuses from the observation.
        # obs.line_status covers both power lines and transformers in grid2op.
        line_names = list(obs.name_line)
        line_status = obs.line_status

        for name, connected in zip(line_names, line_status):
            if not connected:
                try:
                    n.disconnect(name)
                except Exception as e:
                    print(f"Warning: Could not disconnect {name}: {e}")

        params = create_olf_rte_parameter()
        results = pp.loadflow.run_ac(n, params)
        converged = any(r.status.name == 'CONVERGED' for r in results)
        lf_status = results[0].status.name if results else "UNKNOWN"
        if not converged:
            print(f"Warning: AC load flow did not converge for action variant ({action_id}): {lf_status}")

        diagram = self._generate_diagram(n, voltage_level_ids=voltage_level_ids, depth=depth)
        diagram["lf_converged"] = converged
        diagram["lf_status"] = lf_status
        diagram["action_id"] = action_id
        return diagram

recommender_service = RecommenderService()
