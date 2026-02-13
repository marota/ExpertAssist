export interface ConfigRequest {
    network_path: string;
    action_file_path: string;
}

export interface AnalysisRequest {
    disconnected_element: string;
}

export interface AnalysisResult {
    pdf_path: string | null;
    pdf_url: string | null;
    actions: Record<string, any>;
}

export interface BranchResponse {
    branches: string[];
}
