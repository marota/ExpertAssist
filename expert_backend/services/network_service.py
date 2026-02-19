import pypowsybl.network as pn
import os

class NetworkService:
    def __init__(self):
        self.network = None

    def load_network(self, network_path: str):
        if not os.path.exists(network_path):
            raise FileNotFoundError(f"Network file/directory not found: {network_path}")
        
        # Determine if it's a file or directory and load accordingly
        # Assuming bare_env is a directory of xiidm files or a single xiidm file
        # pypowsybl can load from file. 
        # If it's a directory, we might need to pick the xiidm file inside.
        if os.path.isdir(network_path):
            files = [f for f in os.listdir(network_path) if f.endswith('.xiidm') or f.endswith('.xml')]
            if not files:
                 raise FileNotFoundError(f"No .xiidm or .xml file found in {network_path}")
            file_path = os.path.join(network_path, files[0])
        else:
            file_path = network_path

        self.network = pn.load(file_path)
        return {"message": "Network loaded successfully", "id": self.network.id}

    def get_disconnectable_elements(self):
        if not self.network:
            raise ValueError("Network not loaded")
        
        # get lines and two winding transformers
        lines = self.network.get_lines()
        transformers = self.network.get_2_windings_transformers()
        
        elements = []
        if lines is not None and not lines.empty:
            elements.extend(lines.index.tolist())
        if transformers is not None and not transformers.empty:
            elements.extend(transformers.index.tolist())
            
        return sorted(elements)

    def get_voltage_levels(self):
        if not self.network:
            raise ValueError("Network not loaded")

        voltage_levels = self.network.get_voltage_levels()
        if voltage_levels is not None and not voltage_levels.empty:
            return sorted(voltage_levels.index.tolist())
        return []

    def get_nominal_voltages(self):
        """Return {vl_id: nominal_v_kv} mapping for all voltage levels."""
        if not self.network:
            raise ValueError("Network not loaded")

        voltage_levels = self.network.get_voltage_levels()
        if voltage_levels is not None and not voltage_levels.empty:
            return {vl_id: float(row['nominal_v']) for vl_id, row in voltage_levels.iterrows()}
        return {}

    def get_element_voltage_levels(self, element_id: str):
        """Resolve an equipment ID (line, transformer, or VL) to its voltage level IDs."""
        if not self.network:
            raise ValueError("Network not loaded")

        # Check if it's already a voltage level
        voltage_levels = self.network.get_voltage_levels()
        if voltage_levels is not None and element_id in voltage_levels.index:
            return [element_id]

        # Check lines (have voltage_level1_id and voltage_level2_id columns)
        lines = self.network.get_lines()
        if lines is not None and element_id in lines.index:
            row = lines.loc[element_id]
            vls = set()
            if 'voltage_level1_id' in row.index:
                vls.add(row['voltage_level1_id'])
            if 'voltage_level2_id' in row.index:
                vls.add(row['voltage_level2_id'])
            return sorted(vls)

        # Check 2-winding transformers
        transformers = self.network.get_2_windings_transformers()
        if transformers is not None and element_id in transformers.index:
            row = transformers.loc[element_id]
            vls = set()
            if 'voltage_level1_id' in row.index:
                vls.add(row['voltage_level1_id'])
            if 'voltage_level2_id' in row.index:
                vls.add(row['voltage_level2_id'])
            return sorted(vls)

        return []

network_service = NetworkService()
