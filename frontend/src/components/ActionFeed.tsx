import React from 'react';
import type { ActionDetail } from '../types';

interface ActionFeedProps {
    actions: Record<string, ActionDetail>;
    linesOverloaded: string[];
}

const formatRhoArray = (rho: number[] | null, lines: string[]): string => {
    if (!rho || rho.length === 0) return '—';
    return rho.map((val, i) => {
        const pct = (val * 100).toFixed(1);
        const name = lines[i] || `line ${i}`;
        return `${name}: ${pct}%`;
    }).join(', ');
};

const ActionFeed: React.FC<ActionFeedProps> = ({ actions, linesOverloaded }) => {
    return (
        <div style={{ padding: '1rem', height: '100%', overflowY: 'auto' }}>
            <h3 style={{ marginTop: 0 }}>Prioritized Actions</h3>

            {linesOverloaded.length > 0 && (
                <div style={{
                    marginBottom: '1rem',
                    padding: '0.5rem 0.75rem',
                    backgroundColor: '#fff3cd',
                    border: '1px solid #ffc107',
                    borderRadius: '6px',
                    fontSize: '0.85rem',
                }}>
                    <strong>Overloaded lines:</strong>{' '}
                    {linesOverloaded.join(', ')}
                </div>
            )}

            {Object.entries(actions).length === 0 ? (
                <div style={{ color: '#666', fontStyle: 'italic' }}>No actions found.</div>
            ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                    {Object.entries(actions).map(([id, detail], index) => {
                        const maxRhoPct = detail.max_rho != null ? (detail.max_rho * 100).toFixed(1) : null;
                        const isOverloaded = detail.max_rho != null && detail.max_rho > 1.0;

                        return (
                            <div key={id} style={{
                                padding: '1rem',
                                border: `1px solid ${detail.is_rho_reduction ? '#28a745' : '#dc3545'}`,
                                borderLeft: `4px solid ${detail.is_rho_reduction ? '#28a745' : '#dc3545'}`,
                                borderRadius: '8px',
                                backgroundColor: 'white',
                                boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
                            }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                                    <h4 style={{ margin: 0, fontSize: '0.95rem', color: '#333' }}>
                                        #{index + 1} — {id}
                                    </h4>
                                    <span style={{
                                        fontSize: '0.75rem',
                                        fontWeight: 600,
                                        padding: '2px 8px',
                                        borderRadius: '12px',
                                        backgroundColor: detail.is_rho_reduction ? '#d4edda' : '#f8d7da',
                                        color: detail.is_rho_reduction ? '#155724' : '#721c24',
                                    }}>
                                        {detail.is_rho_reduction ? 'Reduces overload' : 'No reduction'}
                                    </span>
                                </div>

                                <p style={{ margin: '0.25rem 0 0.75rem', fontSize: '0.9rem', color: '#555' }}>
                                    {detail.description_unitaire}
                                </p>

                                <div style={{ fontSize: '0.82rem', lineHeight: 1.6, color: '#444' }}>
                                    <div>
                                        <strong>Rho before:</strong>{' '}
                                        {formatRhoArray(detail.rho_before, linesOverloaded)}
                                    </div>
                                    <div>
                                        <strong>Rho after:</strong>{' '}
                                        {formatRhoArray(detail.rho_after, linesOverloaded)}
                                    </div>
                                    {maxRhoPct != null && (
                                        <div style={{ marginTop: '0.25rem' }}>
                                            <strong>Max rho:</strong>{' '}
                                            <span style={{ color: isOverloaded ? '#dc3545' : '#28a745', fontWeight: 600 }}>
                                                {maxRhoPct}%
                                            </span>
                                            {detail.max_rho_line && (
                                                <span style={{ color: '#888' }}> on {detail.max_rho_line}</span>
                                            )}
                                        </div>
                                    )}
                                </div>
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
};

export default ActionFeed;
