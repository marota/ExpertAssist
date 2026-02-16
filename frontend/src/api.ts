import axios from 'axios';
import type { ConfigRequest, AnalysisResult, BranchResponse } from './types';

const API_BASE_URL = 'http://localhost:8000';

export const api = {
    updateConfig: async (config: ConfigRequest) => {
        const response = await axios.post(`${API_BASE_URL}/config`, config);
        return response.data;
    },
    getBranches: async () => {
        const response = await axios.get<BranchResponse>(`${API_BASE_URL}/branches`);
        return response.data.branches;
    },
    runAnalysis: async (disconnected_element: string) => {
        const response = await axios.post<AnalysisResult>(`${API_BASE_URL}/run-analysis`, { disconnected_element });
        return response.data;
    }
};
