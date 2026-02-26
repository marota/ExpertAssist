import expert_op4grid_recommender
from expert_op4grid_recommender import config
from expert_op4grid_recommender.main import Backend, run_analysis
from expert_op4grid_recommender.data_loader import load_actions
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
        self._dict_action = None

    def update_config(self, settings):
        # Update the global config of the package
        path_obj = Path(settings.network_path)
        config.ENV_NAME = path_obj.name
        config.ENV_FOLDER = path_obj.parent
        config.ENV_PATH = path_obj
        
        config.ACTION_FILE_PATH = Path(settings.action_file_path)
        
        # Apply the new settings parameters
        config.MIN_LINE_RECONNECTIONS = settings.min_line_reconnections
        config.MIN_CLOSE_COUPLING = settings.min_close_coupling
        config.MIN_OPEN_COUPLING = settings.min_open_coupling
        config.MIN_LINE_DISCONNECTIONS = settings.min_line_disconnections
        config.N_PRIORITIZED_ACTIONS = settings.n_prioritized_actions

        # Force the requested global flags
        config.MAX_RHO_BOTH_EXTREMITIES = True
        
        # Handle lines monitoring optionally
        if hasattr(settings, 'lines_monitoring_path') and settings.lines_monitoring_path and os.path.exists(settings.lines_monitoring_path):
            config.IGNORE_LINES_MONITORING = False
            config.LINES_MONITORING_FILE = Path(settings.lines_monitoring_path)
            print(f"Loaded lines monitoring file: {settings.lines_monitoring_path}")
        else:
            config.IGNORE_LINES_MONITORING = True
            print("Ignoring lines monitoring (file path not provided or does not exist).")
        
        # Load and cache the action dictionary immediately if path changed or not loaded
        new_action_path = Path(settings.action_file_path)
        if getattr(self, '_last_action_path', None) != new_action_path or self._dict_action is None:
            self._dict_action = load_actions(config.ACTION_FILE_PATH)
            self._last_action_path = new_action_path

            # Auto-generate disco actions if none exist
            has_disco = any(k.startswith("disco_") for k in self._dict_action)
            if not has_disco:
                from expert_backend.services.network_service import network_service
                branches = network_service.get_disconnectable_elements()
                for branch in branches:
                    action_id = f"disco_{branch}"
                    self._dict_action[action_id] = {
                        "description": f"Disconnection of line/transformer '{branch}'",
                        "description_unitaire": f"Ouverture de la ligne '{branch}'",
                        "content": {
                            "set_bus": {
                                "lines_or_id": {branch: -1},
                                "lines_ex_id": {branch: -1},
                                "loads_id": {},
                                "generators_id": {},
                            }
                        },
                    }
                print(f"[RecommenderService] Auto-generated {len(branches)} disco_ actions")
                
                # Save the updated dictionary back to file so the core analysis engine can load it
                import json
                with open(config.ACTION_FILE_PATH, 'w') as f:
                    json.dump(self._dict_action, f, indent=2)
        else:
            print("Action dictionary already loaded, skipping reload.")

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
            action_scores = {}
        else:
            lines_overloaded = result.get("lines_overloaded_names", [])
            prioritized = result.get("prioritized_actions", {})
            action_scores = sanitize_for_json(result.get("action_scores", {}))

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

                # Extract topology from the underlying action object
                action_obj = action_data.get("action")
                if action_obj is not None:
                    topo = {}
                    for field in ("lines_ex_bus", "lines_or_bus", "gens_bus", "loads_bus"):
                        val = getattr(action_obj, field, None)
                        if val is None and isinstance(action_obj, dict):
                            val = action_obj.get(field)
                        topo[field] = sanitize_for_json(val) if val else {}
                    enriched_actions[action_id]["action_topology"] = topo

        yield {
            "type": "result",
            "pdf_path": str(shared_state["latest_pdf"]) if shared_state["latest_pdf"] else None,
            "actions": enriched_actions,
            "action_scores": action_scores,
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

        # Include flow deltas vs base (N) state
        try:
            n_base = self._load_network()
            pp.loadflow.run_ac(n_base, params)
            base_flows = self._get_network_flows(n_base)
            n1_flows = self._get_network_flows(n)
            diagram["flow_deltas"] = self._compute_deltas(n1_flows, base_flows)
        except Exception as e:
            print(f"Warning: Failed to compute N-1 flow deltas: {e}")
            diagram["flow_deltas"] = {}

        return diagram

    def get_action_variant_diagram(self, action_id, voltage_level_ids=None, depth=0, mode="network"):
        """Generate a NAD showing the network state after applying a remedial action.

        Uses the variant ID and network manager stored in the observation from
        the last analysis run to switch to the post-action network state
        directly, avoiding the need to replay disconnections on a fresh network.

        Args:
            action_id: ID of the action to visualize
            voltage_level_ids: list of VL IDs to center on (None = full grid)
            depth: number of hops from center VLs to include
            mode: "network" for bare NAD, "delta" to include flow deltas vs N-1
        """
        import pypowsybl as pp
        
        if not self._last_result or not self._last_result.get("prioritized_actions"):
            raise ValueError("No analysis result available. Run analysis first.")

        actions = self._last_result["prioritized_actions"]
        if action_id not in actions:
            raise ValueError(f"Action '{action_id}' not found in last analysis result.")

        obs = actions[action_id]["observation"]

        # Extract the variant ID and network manager from the observation
        variant_id = obs._variant_id
        nm = obs._network_manager

        # Switch to the action's variant which already contains the
        # post-action network state with load flow results
        nm.set_working_variant(variant_id)

        # Use the underlying pypowsybl network directly
        network = nm.network

        diagram = self._generate_diagram(network, voltage_level_ids=voltage_level_ids, depth=depth)
        diagram["action_id"] = action_id

        # Always include flow deltas so mode switching is instant on the frontend
        try:
            # Get Action flows
            action_flows = self._get_network_flows(network)
            
            # Get N-1 flows (re-simulate contingency on a fresh network)
            n1_network = self._load_network()
            disconnected_element = self._last_disconnected_element
            if disconnected_element:
                try:
                    n1_network.disconnect(disconnected_element)
                except Exception:
                    pass
            params = create_olf_rte_parameter()
            pp.loadflow.run_ac(n1_network, params)
            n1_flows = self._get_network_flows(n1_network)

            diagram["flow_deltas"] = self._compute_deltas(action_flows, n1_flows)
        except Exception as e:
            print(f"Warning: Failed to compute flow deltas: {e}")
            diagram["flow_deltas"] = {}

        return diagram

    def get_action_variant_sld(self, action_id: str, voltage_level_id: str) -> dict:
        """Generate a Single Line Diagram (SLD) for a specific VL in the post-action state.

        Args:
            action_id: ID of the action to visualize
            voltage_level_id: ID of the voltage level to diagram
        """
        if not self._last_result or not self._last_result.get("prioritized_actions"):
            raise ValueError("No analysis result available. Run analysis first.")

        actions = self._last_result["prioritized_actions"]
        if action_id not in actions:
            raise ValueError(f"Action '{action_id}' not found in last analysis result.")

        obs = actions[action_id]["observation"]
        variant_id = obs._variant_id
        nm = obs._network_manager
        nm.set_working_variant(variant_id)
        network = nm.network

        sld = network.get_single_line_diagram(voltage_level_id)
        try:
            from pypowsybl_jupyter.util import _get_svg_string
            svg = _get_svg_string(sld)
        except Exception:
            svg = str(sld)

        return {
            "svg": svg,
            "action_id": action_id,
            "voltage_level_id": voltage_level_id,
        }

    def _get_network_flows(self, network):
        """Extract p1/p2 flows for lines and transformers from a simulated network."""
        import numpy as np
        
        lines = network.get_lines()[['p1', 'p2']]
        trafos = network.get_2_windings_transformers()[['p1', 'p2']]

        p1 = {}
        p2 = {}
        for lid in lines.index:
            v1 = lines.loc[lid, 'p1']
            v2 = lines.loc[lid, 'p2']
            p1[lid] = v1 if not np.isnan(v1) else 0.0
            p2[lid] = v2 if not np.isnan(v2) else 0.0
        for tid in trafos.index:
            v1 = trafos.loc[tid, 'p1']
            v2 = trafos.loc[tid, 'p2']
            p1[tid] = v1 if not np.isnan(v1) else 0.0
            p2[tid] = v2 if not np.isnan(v2) else 0.0
        
        return {"p1": p1, "p2": p2}

    def _compute_deltas(self, after_flows, before_flows):
        """Compute per-line flow deltas between two flow sets.

        Returns a dict mapping line_id -> {delta, category}.
        """
        ap1, ap2 = after_flows["p1"], after_flows["p2"]
        bp1, bp2 = before_flows["p1"], before_flows["p2"]

        all_line_ids = set(ap1.keys()) | set(bp1.keys())
        deltas = {}
        for lid in all_line_ids:
            cur_ap1 = ap1.get(lid, 0.0)
            cur_ap2 = ap2.get(lid, 0.0)
            cur_bp1 = bp1.get(lid, 0.0)
            cur_bp2 = bp2.get(lid, 0.0)

            # Determine entering terminal and value for 'After' state
            if cur_ap1 >= cur_ap2:
                after_idx = 1
                after_val = cur_ap1
            else:
                after_idx = 2
                after_val = cur_ap2
            
            # Determine entering terminal and value for 'Before' state
            if cur_bp1 >= cur_bp2:
                before_idx = 1
                before_val = cur_bp1
            else:
                before_idx = 2
                before_val = cur_bp2

            # Compute delta using the logic from Conversation 93d0da00:
            # Align to the direction of the flow with highest absolute magnitude.
            if after_idx != before_idx and before_val > after_val:
                # Flipped & Before stronger → use Before direction
                if before_idx == 1:
                    delta = cur_ap1 - cur_bp1
                else:
                    delta = cur_ap2 - cur_bp2
            else:
                # Standard case: use After direction
                if after_idx == 1:
                    delta = cur_ap1 - cur_bp1
                else:
                    delta = cur_ap2 - cur_bp2
            
            deltas[lid] = delta

        # Apply threshold (5% of max delta)
        if deltas:
            max_abs_delta = max(abs(d) for d in deltas.values())
        else:
            max_abs_delta = 0.0
        threshold = max_abs_delta * 0.05

        flow_deltas = {}
        for lid, delta in deltas.items():
            if abs(delta) < threshold:
                category = "grey"
            elif delta > 0:
                category = "positive"
            else:
                category = "negative"

            flow_deltas[lid] = {
                "delta": round(float(delta), 1),
                "category": category,
            }

        return flow_deltas

    def get_all_action_ids(self):
        """Return a list of {id, description} for every action in the loaded dictionary."""
        if not self._dict_action:
            raise ValueError("No action dictionary loaded. Load a config first.")
        result = []
        for action_id, action_desc in self._dict_action.items():
            result.append({
                "id": action_id,
                "description": action_desc.get("description_unitaire",
                                               action_desc.get("description", "")),
            })
        return result

    def simulate_manual_action(self, action_id: str, disconnected_element: str):
        """Simulate a single action from the loaded dictionary and return its impact.

        Reuses the environment/simulation setup from the last analysis when possible.
        Falls back to creating a fresh environment if no prior analysis exists.
        """
        if not self._dict_action:
            raise ValueError("No action dictionary loaded. Load a config first.")
        if action_id not in self._dict_action:
            raise ValueError(f"Action '{action_id}' not found in the loaded action dictionary.")

        action_desc = self._dict_action[action_id]

        # Setup environment (lightweight – same logic as run_analysis init)
        from expert_op4grid_recommender.environment_pypowsybl import (
            get_env_first_obs_pypowsybl,
        )
        from expert_op4grid_recommender.utils.simulation_pypowsybl import (
            create_default_action,
            simulate_contingency,
            compute_baseline_simulation,
        )

        env, obs, _ = get_env_first_obs_pypowsybl(
            config.ENV_FOLDER, config.ENV_NAME, is_DC=config.USE_DC_LOAD_FLOW
        )

        # Fix thermal limits if needed (same as in run_analysis)
        if np.mean(env.get_thermal_limit()) >= 10 ** 4:
            from expert_op4grid_recommender.main import set_thermal_limits
            n_grid = env.network_manager.network
            env = set_thermal_limits(n_grid, env, thresold_thermal_limit=0.95)
            obs = env.get_obs()

        # Simulate the N-1 contingency
        act_reco_maintenance = env.action_space({})
        obs_simu_defaut, has_converged = simulate_contingency(
            env, obs, [disconnected_element], act_reco_maintenance, 0
        )
        if not has_converged:
            raise RuntimeError(f"Contingency simulation for '{disconnected_element}' failed.")

        lines_we_care_about = obs.name_line
        lines_overloaded_ids = [
            i for i, l in enumerate(obs_simu_defaut.name_line)
            if l in lines_we_care_about and obs_simu_defaut.rho[i] >= 1
        ]
        lines_overloaded_names = [obs_simu_defaut.name_line[i] for i in lines_overloaded_ids]

        # Build the action object from its content
        try:
            action = env.action_space(action_desc["content"])
        except Exception as e:
            raise ValueError(f"Could not create action from description: {e}")

        # Create contingency action and compute baseline rho
        act_defaut = create_default_action(env.action_space, [disconnected_element])
        baseline_rho, _ = compute_baseline_simulation(
            obs, 0, act_defaut, act_reco_maintenance, lines_overloaded_ids
        )

        # Simulate contingency + candidate action
        obs_simu_action, _, _, info_action = obs.simulate(
            action + act_defaut + act_reco_maintenance,
            time_step=0,
            keep_variant=True,
        )

        rho_before = baseline_rho
        rho_after = None
        max_rho = 0.0
        max_rho_line = "N/A"
        is_rho_reduction = False
        description_unitaire = action_desc.get(
            "description_unitaire", action_desc.get("description", "No description")
        )

        if not info_action["exception"]:
            rho_after = obs_simu_action.rho[lines_overloaded_ids]
            if rho_before is not None:
                is_rho_reduction = bool(np.all(rho_after + 0.01 < rho_before))
            if lines_we_care_about is not None and len(lines_we_care_about) > 0:
                care_mask = np.isin(obs_simu_action.name_line, lines_we_care_about)
                if np.any(care_mask):
                    rhos_of_interest = obs_simu_action.rho[care_mask]
                    max_rho = float(np.max(rhos_of_interest))
                    max_rho_line_idx = np.where(obs_simu_action.rho == max_rho)[0]
                    if max_rho_line_idx.size > 0 and max_rho_line_idx[0] < len(obs.name_line):
                        max_rho_line = obs.name_line[max_rho_line_idx[0]]

        # Store the observation so get_action_variant_diagram can generate the NAD
        if not info_action["exception"] and obs_simu_action is not None:
            if self._last_result is None:
                self._last_result = {"prioritized_actions": {}}
            if "prioritized_actions" not in self._last_result:
                self._last_result["prioritized_actions"] = {}
            self._last_result["prioritized_actions"][action_id] = {
                "observation": obs_simu_action,
                "description_unitaire": description_unitaire,
            }

        return {
            "action_id": action_id,
            "description_unitaire": description_unitaire,
            "rho_before": sanitize_for_json(rho_before),
            "rho_after": sanitize_for_json(rho_after),
            "max_rho": sanitize_for_json(max_rho),
            "max_rho_line": max_rho_line,
            "is_rho_reduction": is_rho_reduction,
            "lines_overloaded": sanitize_for_json(lines_overloaded_names),
        }

recommender_service = RecommenderService()
