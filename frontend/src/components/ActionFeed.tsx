import React, { useState, useEffect, useRef, useMemo } from 'react';
import type { ActionDetail } from '../types';
import { api } from '../api';

interface ActionFeedProps {
    actions: Record<string, ActionDetail>;
    actionScores?: Record<string, any>;
    linesOverloaded: string[];
    selectedActionId: string | null;
    onActionSelect: (actionId: string | null) => void;
    disconnectedElement: string | null;
    onManualActionAdded: (actionId: string, detail: ActionDetail) => void;
    actionViewMode: 'network' | 'delta';
    onViewModeChange: (mode: 'network' | 'delta') => void;
}

const formatRhoArray = (rho: number[] | null, lines: string[]): string => {
    if (!rho || rho.length === 0) return '—';
    return rho.map((val, i) => {
        const pct = (val * 100).toFixed(1);
        const name = lines[i] || `line ${i}`;
        return `${name}: ${pct}%`;
    }).join(', ');
};

const ActionFeed: React.FC<ActionFeedProps> = ({
    actions,
    actionScores,
    linesOverloaded,
    selectedActionId,
    onActionSelect,
    disconnectedElement,
    onManualActionAdded,
    actionViewMode,
    onViewModeChange,
}) => {
    const [searchOpen, setSearchOpen] = useState(false);
    const [searchQuery, setSearchQuery] = useState('');
    const [availableActions, setAvailableActions] = useState<{ id: string; description: string }[]>([]);
    const [loadingActions, setLoadingActions] = useState(false);
    const [simulating, setSimulating] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);
    const searchInputRef = useRef<HTMLInputElement>(null);
    const dropdownRef = useRef<HTMLDivElement>(null);

    // Fetch available actions when search is opened
    useEffect(() => {
        if (searchOpen && availableActions.length === 0 && !loadingActions) {
            setLoadingActions(true);
            api.getAvailableActions()
                .then(setAvailableActions)
                .catch((e) => {
                    console.error('Failed to fetch actions:', e);
                    setError('Failed to load actions list');
                })
                .finally(() => setLoadingActions(false));
        }
        if (searchOpen) {
            setTimeout(() => searchInputRef.current?.focus(), 50);
        }
    }, [searchOpen]);

    // Filter actions for dropdown
    const filteredActions = useMemo(() => {
        const q = searchQuery.toLowerCase();
        const alreadyShown = new Set(Object.keys(actions));
        return availableActions
            .filter(a => !alreadyShown.has(a.id))
            .filter(a => a.id.toLowerCase().includes(q) || (a.description || '').toLowerCase().includes(q))
            .slice(0, 20);
    }, [searchQuery, availableActions, actions]);

    // Format scored actions
    const scoredActionsList = useMemo(() => {
        if (!actionScores) return [];
        const list: { type: string; actionId: string; score: number }[] = [];
        for (const [type, data] of Object.entries(actionScores)) {
            const scores = data?.scores || {};
            for (const [actionId, score] of Object.entries(scores)) {
                list.push({ type, actionId, score: Number(score) });
            }
        }
        return list.sort((a, b) => {
            if (a.type !== b.type) {
                if (a.type === 'line_disconnection') return 1;
                if (b.type === 'line_disconnection') return -1;
                return a.type.localeCompare(b.type);
            }
            return b.score - a.score;
        });
    }, [actionScores]);

    // Close dropdown on outside click
    useEffect(() => {
        if (!searchOpen) return;
        const handler = (e: MouseEvent) => {
            if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
                setSearchOpen(false);
                setSearchQuery('');
                setError(null);
            }
        };
        document.addEventListener('mousedown', handler);
        return () => document.removeEventListener('mousedown', handler);
    }, [searchOpen]);

    const handleAddAction = async (actionId: string) => {
        if (!disconnectedElement) {
            setError('Run an analysis first (need a contingency).');
            return;
        }
        setSimulating(actionId);
        setError(null);
        try {
            const result = await api.simulateManualAction(actionId, disconnectedElement);
            const detail: ActionDetail = {
                description_unitaire: result.description_unitaire,
                rho_before: result.rho_before,
                rho_after: result.rho_after,
                max_rho: result.max_rho,
                max_rho_line: result.max_rho_line,
                is_rho_reduction: result.is_rho_reduction,
            };
            onManualActionAdded(actionId, detail);
            setSearchOpen(false);
            setSearchQuery('');
        } catch (e: any) {
            console.error('Simulation failed:', e);
            setError(e?.response?.data?.detail || 'Simulation failed');
        } finally {
            setSimulating(null);
        }
    };

    return (
        <div style={{ padding: '1rem', height: '100%', overflowY: 'auto' }}>
            {/* Header with search */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem', position: 'relative' }}>
                <h3 style={{ margin: 0, flex: 1 }}>Prioritized Actions</h3>
                <button
                    onClick={() => setSearchOpen(!searchOpen)}
                    title="Add an action from dictionary"
                    style={{
                        background: searchOpen ? '#007bff' : '#e9ecef',
                        color: searchOpen ? 'white' : '#333',
                        border: 'none',
                        borderRadius: '6px',
                        padding: '4px 10px',
                        cursor: 'pointer',
                        fontSize: '0.85rem',
                        fontWeight: 600,
                        transition: 'all 0.15s ease',
                    }}
                >
                    + Add
                </button>

                {/* Search dropdown */}
                {searchOpen && (
                    <div
                        ref={dropdownRef}
                        style={{
                            position: 'absolute',
                            top: '100%',
                            right: 0,
                            left: 0,
                            zIndex: 100,
                            backgroundColor: 'white',
                            border: '1px solid #ccc',
                            borderRadius: '8px',
                            boxShadow: '0 4px 16px rgba(0,0,0,0.15)',
                            marginTop: '4px',
                            overflow: 'hidden',
                        }}
                    >
                        <div style={{ padding: '0.5rem' }}>
                            <input
                                ref={searchInputRef}
                                type="text"
                                placeholder="Search action by ID or description..."
                                value={searchQuery}
                                onChange={(e) => setSearchQuery(e.target.value)}
                                style={{
                                    width: '100%',
                                    padding: '6px 10px',
                                    border: '1px solid #ccc',
                                    borderRadius: '4px',
                                    fontSize: '0.85rem',
                                    boxSizing: 'border-box',
                                }}
                            />
                        </div>
                        {error && (
                            <div style={{
                                padding: '0.5rem',
                                fontSize: '0.8rem',
                                color: '#dc3545',
                                borderTop: '1px solid #eee',
                            }}>
                                {error}
                            </div>
                        )}
                        <div style={{ maxHeight: '250px', overflowY: 'auto' }}>
                            {loadingActions ? (
                                <div style={{ padding: '0.75rem', textAlign: 'center', color: '#888', fontSize: '0.85rem' }}>
                                    Loading actions...
                                </div>
                            ) : (
                                <>
                                    {/* Action Scores Table */}
                                    {scoredActionsList.length > 0 && !searchQuery && (
                                        <div style={{ padding: '0 0.5rem', marginBottom: '0.5rem' }}>
                                            <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#555', marginBottom: '4px' }}>
                                                Scored Actions
                                            </div>
                                            <style>{`
                                                .score-param-tooltip { position: relative; display: inline-flex; align-items: center; cursor: help; margin-left: 6px; }
                                                .score-param-tooltip .tooltip-text {
                                                    visibility: hidden; background-color: #343a40; color: #fff; text-align: left; border-radius: 4px;
                                                    padding: 6px 8px; position: absolute; z-index: 1000; top: 100%; right: 0; margin-top: 5px; opacity: 0;
                                                    transition: opacity 0.2s; font-size: 0.65rem; font-weight: normal; white-space: nowrap;
                                                    box-shadow: 0 2px 5px rgba(0,0,0,0.3); text-transform: none; line-height: 1.4;
                                                }
                                                .score-param-tooltip.left-align .tooltip-text { right: auto; left: 0; }
                                                .score-param-tooltip:hover .tooltip-text { visibility: visible; opacity: 1; }
                                            `}</style>
                                            {Array.from(new Set(scoredActionsList.map(item => item.type))).map(type => {
                                                const typeData = actionScores?.[type] || {};
                                                const scoresKeys = Object.keys(typeData.scores || {});
                                                const paramsKeys = Object.keys(typeData.params || {});
                                                const isPerActionParams = paramsKeys.length > 0 && paramsKeys.some(k => scoresKeys.includes(k));
                                                const globalParams = isPerActionParams ? null : (paramsKeys.length > 0 ? typeData.params : null);

                                                return (
                                                    <div key={type} style={{ marginBottom: '8px' }}>
                                                        <div style={{ fontSize: '0.75rem', fontWeight: 600, color: '#0056b3', backgroundColor: '#e9ecef', padding: '2px 6px', borderRadius: '4px 4px 0 0', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                                            <span>{type.replace('_', ' ').toUpperCase()}</span>
                                                            {globalParams && (
                                                                <div className="score-param-tooltip">
                                                                    <span style={{ color: '#6c757d', fontSize: '0.8rem' }}>ⓘ</span>
                                                                    <div className="tooltip-text">
                                                                        <div style={{ fontWeight: 700, marginBottom: '2px', borderBottom: '1px solid #555', paddingBottom: '2px' }}>Scoring Parameters</div>
                                                                        {Object.entries(globalParams).map(([k, v]) => (
                                                                            <div key={k}>
                                                                                <span style={{ color: '#adb5bd' }}>{k}:</span> {typeof v === 'object' ? JSON.stringify(v) : String(v)}
                                                                            </div>
                                                                        ))}
                                                                    </div>
                                                                </div>
                                                            )}
                                                        </div>
                                                        <table style={{ width: '100%', fontSize: '0.75rem', borderCollapse: 'collapse', border: '1px solid #e9ecef', borderTop: 'none' }}>
                                                            <thead>
                                                                <tr style={{ background: '#f8f9fa', borderBottom: '1px solid #ddd' }}>
                                                                    <th style={{ textAlign: 'left', padding: '4px 6px', width: '70%' }}>Action</th>
                                                                    <th style={{ textAlign: 'right', padding: '4px 6px', width: '30%' }}>Score</th>
                                                                </tr>
                                                            </thead>
                                                            <tbody>
                                                                {scoredActionsList.filter(item => item.type === type).map(item => {
                                                                    const isComputed = !!actions[item.actionId];
                                                                    return (
                                                                        <tr key={item.actionId}
                                                                            onClick={() => !isComputed && handleAddAction(item.actionId)}
                                                                            style={{
                                                                                borderBottom: '1px solid #eee',
                                                                                cursor: (isComputed || simulating) ? 'not-allowed' : 'pointer',
                                                                                color: isComputed ? '#888' : 'inherit',
                                                                                opacity: simulating === item.actionId ? 0.7 : 1,
                                                                                background: simulating === item.actionId ? '#e7f1ff' : 'transparent',
                                                                            }}>
                                                                            <td style={{ padding: '4px 6px', fontWeight: 600, display: 'flex', alignItems: 'center' }}>
                                                                                {item.actionId}
                                                                                {isComputed && <span style={{ marginLeft: '4px', background: '#28a745', color: '#fff', padding: '1px 4px', borderRadius: '4px', fontSize: '0.65rem', opacity: 0.8 }}>computed</span>}
                                                                                {isPerActionParams && typeData.params[item.actionId] && (
                                                                                    <div className="score-param-tooltip left-align" onClick={(e) => e.stopPropagation()}>
                                                                                        <span style={{ color: '#6c757d', fontSize: '0.8rem' }}>ⓘ</span>
                                                                                        <div className="tooltip-text">
                                                                                            <div style={{ fontWeight: 700, marginBottom: '2px', borderBottom: '1px solid #555', paddingBottom: '2px' }}>Parameters</div>
                                                                                            {Object.entries(typeData.params[item.actionId]).map(([k, v]) => (
                                                                                                <div key={k}>
                                                                                                    <span style={{ color: '#adb5bd' }}>{k}:</span> {typeof v === 'object' ? JSON.stringify(v) : String(v)}
                                                                                                </div>
                                                                                            ))}
                                                                                        </div>
                                                                                    </div>
                                                                                )}
                                                                            </td>
                                                                            <td style={{ padding: '4px 6px', textAlign: 'right', fontFamily: 'monospace' }}>
                                                                                {item.score.toFixed(2)}
                                                                            </td>
                                                                        </tr>
                                                                    );
                                                                })}
                                                            </tbody>
                                                        </table>
                                                    </div>
                                                );
                                            })}
                                        </div>
                                    )}

                                    {/* Search Results */}
                                    {(!searchQuery && scoredActionsList.length === 0 && filteredActions.length === 0) && (
                                        <div style={{ padding: '0.75rem', textAlign: 'center', color: '#888', fontSize: '0.85rem' }}>
                                            All actions already added
                                        </div>
                                    )}
                                    {(searchQuery && filteredActions.length === 0) && (
                                        <div style={{ padding: '0.75rem', textAlign: 'center', color: '#888', fontSize: '0.85rem' }}>
                                            No matching actions
                                        </div>
                                    )}
                                    {((!searchQuery && scoredActionsList.length === 0) || searchQuery) && filteredActions.map(a => (
                                        <div
                                            key={a.id}
                                            onClick={() => handleAddAction(a.id)}
                                            style={{
                                                padding: '0.5rem 0.75rem',
                                                cursor: simulating ? 'wait' : 'pointer',
                                                borderTop: '1px solid #eee',
                                                backgroundColor: simulating === a.id ? '#e7f1ff' : 'transparent',
                                                opacity: simulating && simulating !== a.id ? 0.5 : 1,
                                                transition: 'background-color 0.1s ease',
                                            }}
                                            onMouseEnter={(e) => { if (!simulating) (e.currentTarget as HTMLDivElement).style.backgroundColor = '#f0f0f0'; }}
                                            onMouseLeave={(e) => { if (simulating !== a.id) (e.currentTarget as HTMLDivElement).style.backgroundColor = 'transparent'; }}
                                        >
                                            <div style={{ fontWeight: 600, fontSize: '0.82rem', color: '#333' }}>
                                                {simulating === a.id ? '⏳ Simulating...' : a.id}
                                            </div>
                                            {a.description && (
                                                <div style={{ fontSize: '0.78rem', color: '#777', marginTop: '2px' }}>
                                                    {a.description}
                                                </div>
                                            )}
                                        </div>
                                    ))}
                                </>
                            )}
                        </div>
                    </div>
                )}
            </div>

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

            {/* View mode toggle - only visible when an action is selected */}
            {selectedActionId && (
                <div style={{
                    marginBottom: '1rem',
                    padding: '0.5rem 0.75rem',
                    backgroundColor: '#f8f9fa',
                    border: '1px solid #dee2e6',
                    borderRadius: '6px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.5rem',
                }}>
                    <span style={{ fontSize: '0.8rem', fontWeight: 600, color: '#555' }}>View:</span>
                    <div
                        style={{
                            display: 'flex',
                            borderRadius: '6px',
                            overflow: 'hidden',
                            border: '1px solid #ccc',
                            fontSize: '0.78rem',
                            fontWeight: 600,
                        }}
                    >
                        <button
                            onClick={() => onViewModeChange('network')}
                            style={{
                                padding: '4px 12px',
                                border: 'none',
                                cursor: 'pointer',
                                backgroundColor: actionViewMode === 'network' ? '#007bff' : '#fff',
                                color: actionViewMode === 'network' ? '#fff' : '#555',
                                transition: 'all 0.15s ease',
                            }}
                        >
                            Flows
                        </button>
                        <button
                            onClick={() => onViewModeChange('delta')}
                            style={{
                                padding: '4px 12px',
                                border: 'none',
                                borderLeft: '1px solid #ccc',
                                cursor: 'pointer',
                                backgroundColor: actionViewMode === 'delta' ? '#007bff' : '#fff',
                                color: actionViewMode === 'delta' ? '#fff' : '#555',
                                transition: 'all 0.15s ease',
                            }}
                        >
                            Δ Flows
                        </button>
                    </div>
                </div>
            )}

            {Object.entries(actions).length === 0 ? (
                <div style={{ color: '#666', fontStyle: 'italic' }}>No actions found.</div>
            ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                    {Object.entries(actions).map(([id, detail], index) => {
                        const maxRhoPct = detail.max_rho != null ? (detail.max_rho * 100).toFixed(1) : null;
                        const severity = detail.max_rho != null
                            ? (detail.max_rho > 1.0 ? 'red' : detail.max_rho > 0.9 ? 'orange' : 'green')
                            : (detail.is_rho_reduction ? 'green' : 'red');
                        const severityMap = {
                            green: { border: '#28a745', badgeBg: '#d4edda', badgeText: '#155724', label: 'Solves overload' },
                            orange: { border: '#f0ad4e', badgeBg: '#fff3cd', badgeText: '#856404', label: 'Solved — low margin' },
                            red: { border: '#dc3545', badgeBg: '#f8d7da', badgeText: '#721c24', label: detail.is_rho_reduction ? 'Still overloaded' : 'No reduction' },
                        };
                        const sc = severityMap[severity];
                        const isSelected = selectedActionId === id;

                        return (
                            <div
                                key={id}
                                onClick={() => onActionSelect(isSelected ? null : id)}
                                style={{
                                    padding: '1rem',
                                    border: `1px solid ${isSelected ? '#007bff' : sc.border}`,
                                    borderLeft: `4px solid ${isSelected ? '#007bff' : sc.border}`,
                                    borderRadius: '8px',
                                    backgroundColor: isSelected ? '#e7f1ff' : 'white',
                                    boxShadow: isSelected
                                        ? '0 0 0 2px rgba(0,123,255,0.3), 0 2px 8px rgba(0,0,0,0.15)'
                                        : '0 2px 4px rgba(0,0,0,0.1)',
                                    cursor: 'pointer',
                                    transition: 'all 0.15s ease',
                                }}
                            >
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                                    <h4 style={{ margin: 0, fontSize: '0.95rem', color: isSelected ? '#0056b3' : '#333' }}>
                                        #{index + 1} — {id}
                                    </h4>
                                    <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                                        {isSelected && (
                                            <span style={{
                                                fontSize: '0.7rem',
                                                fontWeight: 600,
                                                padding: '2px 6px',
                                                borderRadius: '4px',
                                                backgroundColor: '#007bff',
                                                color: 'white',
                                            }}>
                                                VIEWING
                                            </span>
                                        )}
                                        <span style={{
                                            fontSize: '0.75rem',
                                            fontWeight: 600,
                                            padding: '2px 8px',
                                            borderRadius: '12px',
                                            backgroundColor: sc.badgeBg,
                                            color: sc.badgeText,
                                        }}>
                                            {sc.label}
                                        </span>
                                    </div>
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
                                            <span style={{ color: sc.border, fontWeight: 600 }}>
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
