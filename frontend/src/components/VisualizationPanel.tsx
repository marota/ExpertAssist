import React from 'react';

interface VisualizationPanelProps {
    pdfUrl: string | null;
}

const VisualizationPanel: React.FC<VisualizationPanelProps> = ({ pdfUrl }) => {
    if (!pdfUrl) {
        return (
            <div style={{
                height: '100%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#666'
            }}>
                Select an element and run analysis to view the Overflow Graph.
            </div>
        );
    }

    return (
        <div style={{ height: '100%', width: '100%' }}>
            <iframe
                src={`http://localhost:8000${pdfUrl}`}
                style={{ width: '100%', height: '100%', border: 'none' }}
                title="Overflow Graph"
            />
        </div>
    );
};

export default VisualizationPanel;
