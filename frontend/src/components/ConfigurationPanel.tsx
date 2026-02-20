import React from 'react';
import { api } from '../api';

interface ConfigurationPanelProps {
    networkPath: string;
    actionPath: string;
    onNetworkPathChange: (path: string) => void;
    onActionPathChange: (path: string) => void;
    branches: string[];
    selectedBranch: string;
    onBranchChange: (branch: string) => void;
    inspectQuery: string;
    onInspectQueryChange: (query: string) => void;
    inspectableItems: string[];
    onLoadConfig: () => void;
    onRunAnalysis: () => void;
    onResetView: () => void;
    configLoading: boolean;
    analysisLoading: boolean;
}

const ConfigurationPanel: React.FC<ConfigurationPanelProps> = ({
    networkPath,
    actionPath,
    onNetworkPathChange,
    onActionPathChange,
    branches,
    selectedBranch,
    onBranchChange,
    inspectQuery,
    onInspectQueryChange,
    inspectableItems,
    onLoadConfig,
    onRunAnalysis,
    onResetView,
    configLoading,
    analysisLoading,
}) => {
    const pickPath = async (type: 'file' | 'dir', setter: (path: string) => void) => {
        try {
            const path = await api.pickPath(type);
            if (path) setter(path);
        } catch {
            console.error('Failed to open file picker');
        }
    };

    return (
        <div style={{
            background: '#f4f4f4',
            padding: '15px',
            borderBottom: '1px solid #ccc',
            display: 'flex',
            flexWrap: 'wrap',
            gap: '15px',
            alignItems: 'end',
        }}>
            <div style={{ flex: '1 1 250px', display: 'flex', flexDirection: 'column', gap: '5px' }}>
                <label style={{ fontSize: '0.8rem', fontWeight: 'bold' }}>Network Path</label>
                <div style={{ display: 'flex', gap: '5px' }}>
                    <input
                        type="text"
                        value={networkPath}
                        onChange={e => onNetworkPathChange(e.target.value)}
                        style={{ flex: 1, padding: '8px', border: '1px solid #ccc', borderRadius: '4px' }}
                    />
                    <button
                        onClick={() => pickPath('dir', onNetworkPathChange)}
                        style={{ padding: '8px', background: '#7f8c8d', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }}
                    >
                        Browse
                    </button>
                </div>
            </div>
            <div style={{ flex: '1 1 250px', display: 'flex', flexDirection: 'column', gap: '5px' }}>
                <label style={{ fontSize: '0.8rem', fontWeight: 'bold' }}>Action File Path</label>
                <div style={{ display: 'flex', gap: '5px' }}>
                    <input
                        type="text"
                        value={actionPath}
                        onChange={e => onActionPathChange(e.target.value)}
                        style={{ flex: 1, padding: '8px', border: '1px solid #ccc', borderRadius: '4px' }}
                    />
                    <button
                        onClick={() => pickPath('file', onActionPathChange)}
                        style={{ padding: '8px', background: '#7f8c8d', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }}
                    >
                        Browse
                    </button>
                </div>
            </div>
            <button
                onClick={onLoadConfig}
                disabled={configLoading}
                style={{
                    padding: '8px 15px', cursor: configLoading ? 'not-allowed' : 'pointer',
                    background: configLoading ? '#ccc' : '#3498db', color: 'white',
                    border: 'none', borderRadius: '4px', fontWeight: 'bold',
                }}
            >
                {configLoading ? 'Loading...' : 'Load Config'}
            </button>
            {branches.length > 0 && (
                <div style={{ flex: '1 1 300px', display: 'flex', gap: '15px', alignItems: 'end' }}>
                    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '5px' }}>
                        <label style={{ fontSize: '0.8rem', fontWeight: 'bold' }}>Target Contingency</label>
                        <input
                            list="contingencies"
                            value={selectedBranch}
                            onChange={e => onBranchChange(e.target.value)}
                            placeholder="Search line/bus..."
                            style={{ padding: '8px', border: '1px solid #ccc', borderRadius: '4px' }}
                        />
                        <datalist id="contingencies">
                            {branches.map(b => <option key={b} value={b} />)}
                        </datalist>
                    </div>
                    <button
                        onClick={onRunAnalysis}
                        disabled={!selectedBranch || analysisLoading}
                        style={{
                            padding: '8px 15px',
                            cursor: (!selectedBranch || analysisLoading) ? 'not-allowed' : 'pointer',
                            background: (!selectedBranch || analysisLoading) ? '#ccc' : '#27ae60',
                            color: 'white', border: 'none', borderRadius: '4px', fontWeight: 'bold',
                        }}
                    >
                        {analysisLoading ? 'Running...' : 'Run Analysis'}
                    </button>
                </div>
            )}
            {branches.length > 0 && (
                <div style={{ flex: '1 1 200px', display: 'flex', flexDirection: 'column', gap: '5px' }}>
                    <label style={{ fontSize: '0.8rem', fontWeight: 'bold' }}>Inspect Line/Bus/VL</label>
                    <div style={{ display: 'flex', gap: '5px' }}>
                        <input
                            list="inspectables"
                            value={inspectQuery}
                            onChange={e => onInspectQueryChange(e.target.value)}
                            placeholder="Zoom to..."
                            style={{
                                flex: 1, padding: '8px',
                                border: inspectQuery ? '2px solid #3498db' : '1px solid #ccc',
                                borderRadius: '4px',
                            }}
                        />
                        <datalist id="inspectables">
                            {inspectableItems.map(b => <option key={b} value={b} />)}
                        </datalist>
                        {inspectQuery && (
                            <button
                                onClick={() => onInspectQueryChange('')}
                                style={{
                                    background: '#e74c3c', color: 'white', padding: '0 10px',
                                    border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold',
                                }}
                                title="Clear"
                            >
                                X
                            </button>
                        )}
                    </div>
                </div>
            )}
            <button
                onClick={onResetView}
                style={{
                    padding: '8px 15px', background: '#bdc3c7', color: '#333',
                    border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold',
                }}
            >
                Reset View
            </button>
        </div>
    );
};

export default ConfigurationPanel;
