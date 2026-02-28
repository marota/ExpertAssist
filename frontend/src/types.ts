export interface ConfigRequest {
    network_path: string;
    action_file_path: string;
    min_line_reconnections: number;
    min_close_coupling: number;
    min_open_coupling: number;
    min_line_disconnections: number;
    n_prioritized_actions: number;
    lines_monitoring_path?: string;
    monitoring_factor: number;
    pre_existing_overload_threshold?: number;
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
    action_scores?: Record<string, Record<string, unknown>>;
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
    originalViewBox?: ViewBox | null;
    lines_overloaded?: string[];
}

export interface FlowDelta {
    delta: number;
    category: 'positive' | 'negative' | 'grey';
}

export interface ViewBox {
    x: number;
    y: number;
    w: number;
    h: number;
}

// Metadata index for O(1) lookups of SVG elements
export interface NodeMeta {
    equipmentId: string;
    svgId: string;
    x: number;
    y: number;
    legendSvgId?: string;
    legendEdgeSvgId?: string;
    [key: string]: unknown;
}

export interface EdgeInfoMeta {
    svgId: string;
    infoType?: string;
    direction?: string;
    externalLabel?: string;
}

export interface EdgeMeta {
    equipmentId: string;
    svgId: string;
    node1: string;
    node2: string;
    edgeInfo1?: EdgeInfoMeta;
    edgeInfo2?: EdgeInfoMeta;
    [key: string]: unknown;
}

export interface MetadataIndex {
    nodesByEquipmentId: Map<string, NodeMeta>;
    nodesBySvgId: Map<string, NodeMeta>;
    edgesByEquipmentId: Map<string, EdgeMeta>;
    edgesByNode: Map<string, EdgeMeta[]>;
}

export type TabId = 'n' | 'n-1' | 'action' | 'overflow';
