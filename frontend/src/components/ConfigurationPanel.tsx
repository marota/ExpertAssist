import React, { useState } from 'react';
import Select from 'react-select';
// @ts-ignore
import { api } from '../api';

interface ConfigurationPanelProps {
    onAnalysisRun: (result: any, disconnectedElement: string) => void;
}

const ConfigurationPanel: React.FC<ConfigurationPanelProps> = ({ onAnalysisRun }) => {
    const [networkPath, setNetworkPath] = useState('/home/marotant/dev/Expert_op4grid_recommender/data/bare_env_20240828T0100Z_dijon_only');
    const [actionPath, setActionPath] = useState('/home/marotant/dev/Expert_op4grid_recommender/data/action_space/reduced_model_actions_20240828T0100Z_new_dijon.json');
    const [branches, setBranches] = useState<{ value: string; label: string }[]>([]);
    const [selectedBranch, setSelectedBranch] = useState<{ value: string; label: string } | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const handleLoadConfig = async () => {
        setLoading(true);
        setError(null);
        try {
            await api.updateConfig({ network_path: networkPath, action_file_path: actionPath });
            const branchList = await api.getBranches();
            setBranches(branchList.map((b: string) => ({ value: b, label: b })));
        } catch (err: any) {
            setError(err.message || 'Failed to load configuration');
        } finally {
            setLoading(false);
        }
    };

    const handleRunAnalysis = async () => {
        if (!selectedBranch) return;
        setLoading(true);
        setError(null);
        try {
            const result = await api.runAnalysis(selectedBranch.value);
            onAnalysisRun(result, selectedBranch.value);
        } catch (err: any) {
            setError(err.message || 'Analysis failed');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div style={{ padding: '1rem', borderBottom: '1px solid #ccc', backgroundColor: '#f9f9f9' }}>
            <div style={{ display: 'flex', gap: '1rem', marginBottom: '1rem', alignItems: 'center' }}>
                <input
                    type="text"
                    value={networkPath}
                    onChange={(e) => setNetworkPath(e.target.value)}
                    placeholder="Path to Network (.xiidm folder)"
                    style={{ flex: 1, padding: '0.5rem' }}
                />
                <input
                    type="text"
                    value={actionPath}
                    onChange={(e) => setActionPath(e.target.value)}
                    placeholder="Path to Action File (.json)"
                    style={{ flex: 1, padding: '0.5rem' }}
                />
                <button onClick={handleLoadConfig} disabled={loading} style={{ padding: '0.5rem 1rem' }}>
                    {loading ? 'Loading...' : 'Load Configuration'}
                </button>
            </div>
            {branches.length > 0 && (
                <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
                    <div style={{ flex: 1 }}>
                        <Select
                            options={branches}
                            value={selectedBranch}
                            onChange={(option: any) => setSelectedBranch(option)}
                            placeholder="Select disconnected element..."
                            isSearchable
                        />
                    </div>
                    <button
                        onClick={handleRunAnalysis}
                        disabled={!selectedBranch || loading}
                        style={{ padding: '0.5rem 1rem', backgroundColor: '#007bff', color: 'white', border: 'none', borderRadius: '4px' }}
                    >
                        {loading ? 'Running...' : 'Run Analysis'}
                    </button>
                </div>
            )}
            {error && <div style={{ color: 'red', marginTop: '0.5rem' }}>{error}</div>}
        </div>
    );
};

export default ConfigurationPanel;
