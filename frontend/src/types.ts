export interface ConfigRequest {
    network_path: string;
    action_file_path: string;
}

export interface AnalysisRequest {
    disconnected_element: string;
}

export interface ActionTopology {
    lines_ex_bus: Record<string, number>;
    lines_or_bus: Record<string, number>;
    gens_bus: Record<string, number>;
    loads_bus: Record<string, number>;
}

export interface ActionDetail {
    description_unitaire: string;
    rho_before: number[] | null;
    rho_after: number[] | null;
    max_rho: number | null;
    max_rho_line: string;
    is_rho_reduction: boolean;
    action_topology?: ActionTopology;
}

export interface AnalysisResult {
    pdf_path: string | null;
    pdf_url: string | null;
    actions: Record<string, ActionDetail>;
    lines_overloaded: string[];
    message: string;
    dc_fallback: boolean;
}

export interface BranchResponse {
    branches: string[];
}

export interface DiagramData {
    svg: string;
    metadata: unknown;
    lf_converged?: boolean;
    lf_status?: string;
    action_id?: string;
    flow_deltas?: Record<string, FlowDelta>;
}

export interface FlowDelta {
    delta: number;
    category: 'positive' | 'negative' | 'grey';
}
