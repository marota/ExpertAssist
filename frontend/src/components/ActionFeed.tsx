import React from 'react';

interface ActionFeedProps {
    actions: Record<string, any>;
}

const ActionFeed: React.FC<ActionFeedProps> = ({ actions }) => {
    return (
        <div style={{ padding: '1rem', height: '100%', overflowY: 'auto' }}>
            <h3>Prioritized Actions</h3>
            {Object.entries(actions).length === 0 ? (
                <div style={{ color: '#666', fontStyle: 'italic' }}>No actions found.</div>
            ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                    {Object.entries(actions).map(([id, details]) => (
                        <div key={id} style={{
                            padding: '1rem',
                            border: '1px solid #ddd',
                            borderRadius: '8px',
                            backgroundColor: 'white',
                            boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
                        }}>
                            <h4 style={{ margin: '0 0 0.5rem 0', wordBreak: 'break-all' }}>{id}</h4>
                            <pre style={{
                                fontSize: '0.8rem',
                                whiteSpace: 'pre-wrap',
                                backgroundColor: '#f4f4f4',
                                padding: '0.5rem',
                                borderRadius: '4px',
                                maxHeight: '200px',
                                overflow: 'auto'
                            }}>
                                {JSON.stringify(details, null, 2)}
                            </pre>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
};

export default ActionFeed;
