import axios from 'axios';
import type { ConfigRequest, AnalysisResult, BranchResponse, DiagramData } from './types';

const API_BASE_URL = 'http://localhost:8000';

export const api = {
    updateConfig: async (config: ConfigRequest) => {
        const response = await axios.post(`${API_BASE_URL}/api/config`, config);
        return response.data;
    },
    getBranches: async () => {
        const response = await axios.get<BranchResponse>(`${API_BASE_URL}/api/branches`);
        return response.data.branches;
    },
    runAnalysis: async (disconnected_element: string): Promise<AnalysisResult> => {
        // The backend returns NDJSON (one JSON object per line).
        // Use fetch + ReadableStream to parse events incrementally.
        const response = await fetch(`${API_BASE_URL}/api/run-analysis`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ disconnected_element }),
        });
        if (!response.ok) {
            throw new Error(`Analysis failed: ${response.statusText}`);
        }

        const reader = response.body!.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let result: Partial<AnalysisResult> = {};

        for (;;) {
            const { value, done } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop()!;
            for (const line of lines) {
                if (!line.trim()) continue;
                const event = JSON.parse(line);
                if (event.type === 'pdf') {
                    result.pdf_url = event.pdf_url;
                    result.pdf_path = event.pdf_path;
                } else if (event.type === 'result') {
                    result = { ...result, ...event };
                } else if (event.type === 'error') {
                    throw new Error(event.message);
                }
            }
        }

        return result as AnalysisResult;
    },
    getActionVariantDiagram: async (actionId: string): Promise<DiagramData> => {
        const response = await axios.post<DiagramData>(
            `${API_BASE_URL}/api/action-variant-diagram`,
            { action_id: actionId }
        );
        return response.data;
    },
};
