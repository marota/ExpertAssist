import React, { useState, useEffect, useRef, useMemo } from 'react';
import type { ActionDetail, NodeMeta, EdgeMeta } from '../types';
import { api } from '../api';
import { getActionTargetVoltageLevel, getActionTargetLines } from '../utils/svgUtils';

interface ActionFeedProps {
    actions: Record<string, ActionDetail>;
    actionScores?: Record<string, Record<string, unknown>>;
    linesOverloaded: string[];
    selectedActionId: string | null;
    onActionSelect: (actionId: string | null) => void;
    onAssetClick: (actionId: string, assetName: string, tab?: 'action' | 'n-1') => void;
    nodesByEquipmentId: Map<string, NodeMeta> | null;
    edgesByEquipmentId: Map<string, EdgeMeta> | null;
    disconnectedElement: string | null;
    onManualActionAdded: (actionId: string, detail: ActionDetail, linesOverloaded: string[]) => void;
    analysisLoading: boolean;
    monitoringFactor: number;
}

const ActionFeed: React.FC<ActionFeedProps> = ({
    actions,
    actionScores,
    linesOverloaded,
    selectedActionId,
    onActionSelect,
    onAssetClick,
    nodesByEquipmentId,
    edgesByEquipmentId,
    disconnectedElement,
    onManualActionAdded,
    analysisLoading,
    monitoringFactor,
}) => {
    const [searchOpen, setSearchOpen] = useState(false);
    const [searchQuery, setSearchQuery] = useState('');
    const [availableActions, setAvailableActions] = useState<{ id: string; description: string }[]>([]);
    const [loadingActions, setLoadingActions] = useState(false);
    const [simulating, setSimulating] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [typeFilters, setTypeFilters] = useState({ disco: true, reco: true, open: true, close: true });
    const searchInputRef = useRef<HTMLInputElement>(null);
    const dropdownRef = useRef<HTMLDivElement>(null);
    const [tooltip, setTooltip] = useState<{ content: React.ReactNode; x: number; y: number } | null>(null);

    const showTooltip = (e: React.MouseEvent, content: React.ReactNode) => {
        const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
        setTooltip({ content, x: rect.left, y: rect.bottom + 5 });
    };
    const hideTooltip = () => setTooltip(null);

    // Fetch available actions when search is opened
    const handleOpenSearch = async () => {
        if (searchOpen) { setSearchOpen(false); return; }
        setSearchOpen(true);
        setSearchQuery('');
        setError(null);
        if (availableActions.length === 0) {
            setLoadingActions(true);
            try {
                const list = await api.getAvailableActions();
                setAvailableActions(list);
            } catch (e) {
                console.error('Failed to fetch actions:', e);
                setError('Failed to load actions list');
            } finally {
                setLoadingActions(false);
            }
        }
        setTimeout(() => searchInputRef.current?.focus(), 50);
    };

    // Filter actions for dropdown
    const filteredActions = useMemo(() => {
        const q = searchQuery.toLowerCase();
        const alreadyShown = new Set(Object.keys(actions));
        return availableActions
            .filter(a => !alreadyShown.has(a.id))
            .filter((a: any) => {
                const t = a.type || 'unknown';
                if ((t.includes('disco') || t.includes('open_line') || t.includes('open_load')) && !typeFilters.disco) return false;
                if ((t.includes('reco') || t.includes('close_line') || t.includes('close_load')) && !typeFilters.reco) return false;
                if (t === 'open_coupling' && !typeFilters.open) return false;
                if (t === 'close_coupling' && !typeFilters.close) return false;
                // If it's truly 'unknown' or something else, only show if all are checked or perhaps none?
                // For now, if all filters are unchecked, return false.
                if (!typeFilters.disco && !typeFilters.reco && !typeFilters.open && !typeFilters.close) return false;
                return true;
            })
            .filter(a => a.id.toLowerCase().includes(q) || (a.description || '').toLowerCase().includes(q))
            .slice(0, 20);
    }, [searchQuery, availableActions, actions, typeFilters]);

    // Format scored actions
    const scoredActionsList = useMemo(() => {
        if (!actionScores) return [];
        const list: { type: string; actionId: string; score: number }[] = [];
        for (const [type, data] of Object.entries(actionScores)) {
            // Apply filtering
            if (type === 'line_disconnection' && !typeFilters.disco) continue;
            if (type === 'line_reconnection' && !typeFilters.reco) continue;
            if (type === 'open_coupling' && !typeFilters.open) continue;
            if (type === 'close_coupling' && !typeFilters.close) continue;

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
    }, [actionScores, typeFilters]);

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
            setError('Select a contingency first.');
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
            onManualActionAdded(actionId, detail, result.lines_overloaded || []);
            setSearchOpen(false);
            setSearchQuery('');
        } catch (e: unknown) {
            console.error('Simulation failed:', e);
            const err = e as { response?: { data?: { detail?: string } } };
            setError(err?.response?.data?.detail || 'Simulation failed');
        } finally {
            setSimulating(null);
        }
    };

    const clickableLinkStyle: React.CSSProperties = {
        background: 'none',
        border: 'none',
        cursor: 'pointer',
        padding: 0,
        fontSize: 'inherit',
        color: '#1e40af',
        fontWeight: 600,
        textDecoration: 'underline dotted',
    };

    const renderRho = (arr: number[] | null, actionId: string, tab: 'action' | 'n-1' = 'action'): React.ReactNode => {
        if (!arr || arr.length === 0) return '\u2014';
        return arr.map((v, i) => {
            const lineName = linesOverloaded[i] || `line ${i}`;
            return (
                <React.Fragment key={i}>
                    {i > 0 && ', '}
                    <button
                        style={clickableLinkStyle}
                        title={`Zoom to ${lineName}`}
                        onClick={(e) => { e.stopPropagation(); onAssetClick(actionId, lineName, tab); }}
                    >{lineName}</button>
                    {`: ${(v * 100).toFixed(1)}%`}
                </React.Fragment>
            );
        });
    };

    // Sort actions by max_rho ascending (matching standalone)
    const sortedActionEntries = useMemo(() => {
        return Object.entries(actions).sort(([, a], [, b]) => (a.max_rho ?? 999) - (b.max_rho ?? 999));
    }, [actions]);

    return (
        <div style={{ padding: '15px', height: '100%', overflowY: 'auto' }}>
            {/* Header with search */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '10px', position: 'relative' }}>
                <h3 style={{ margin: 0, flex: 1 }}>Simulated Actions</h3>
                <button
                    onClick={handleOpenSearch}
                    style={{
                        background: searchOpen ? '#007bff' : '#e9ecef',
                        color: searchOpen ? 'white' : '#333',
                        border: 'none',
                        borderRadius: '6px',
                        padding: '4px 10px',
                        cursor: 'pointer',
                        fontSize: '13px',
                        fontWeight: 600,
                    }}
                >
                    + Manual Selection
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
                        <div style={{ padding: '8px' }}>
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
                                    fontSize: '13px',
                                    boxSizing: 'border-box',
                                }}
                            />
                        </div>
                        {/* Action type filter checkboxes */}
                        <div style={{ padding: '4px 8px', display: 'flex', flexWrap: 'wrap', gap: '6px', borderTop: '1px solid #eee', fontSize: '11px' }}>
                            {([['disco', 'Disconnections'], ['reco', 'Reconnections'], ['open', 'Open coupling'], ['close', 'Close coupling']] as const).map(([key, label]) => (
                                <label key={key} style={{ display: 'flex', alignItems: 'center', gap: '3px', cursor: 'pointer', color: '#555' }}>
                                    <input
                                        type="checkbox"
                                        checked={typeFilters[key]}
                                        onChange={() => setTypeFilters(prev => ({ ...prev, [key]: !prev[key] }))}
                                        style={{ margin: 0, cursor: 'pointer' }}
                                    />
                                    {label}
                                </label>
                            ))}
                        </div>
                        {error && (
                            <div style={{
                                padding: '6px 8px',
                                fontSize: '12px',
                                color: '#dc3545',
                                borderTop: '1px solid #eee',
                            }}>
                                {error}
                            </div>
                        )}
                        <div style={{ maxHeight: '250px', overflowY: 'auto' }}>
                            {loadingActions ? (
                                <div style={{ padding: '10px', textAlign: 'center', color: '#888', fontSize: '13px' }}>
                                    Loading actions...
                                </div>
                            ) : (
                                <>
                                    {/* Action Scores Table */}
                                    {scoredActionsList.length > 0 && !searchQuery && (
                                        <div style={{ padding: '0 8px', marginBottom: '8px' }}>
                                            <div style={{ fontSize: '12px', fontWeight: 600, color: '#555', marginBottom: '4px' }}>
                                                Scored Actions
                                            </div>
                                            {Array.from(new Set(scoredActionsList.map(item => item.type))).map(type => {
                                                const typeData = (actionScores?.[type] || {}) as { scores?: Record<string, number>; params?: Record<string, Record<string, unknown>> };
                                                const scoresKeys = Object.keys(typeData.scores || {});
                                                const paramsKeys = Object.keys(typeData.params || {});
                                                const isPerActionParams = paramsKeys.length > 0 && paramsKeys.some((k: string) => scoresKeys.includes(k));
                                                const globalParams = isPerActionParams ? null : (paramsKeys.length > 0 ? typeData.params : null);

                                                return (
                                                    <div key={type} style={{ marginBottom: '8px' }}>
                                                        <div style={{ fontSize: '11px', fontWeight: 600, color: '#0056b3', backgroundColor: '#e9ecef', padding: '2px 6px', borderRadius: '4px 4px 0 0', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                                            <span>{type.replace('_', ' ').toUpperCase()}</span>
                                                            {globalParams && (
                                                                <span
                                                                    style={{ color: '#6c757d', fontSize: '12px', cursor: 'help', marginLeft: '6px' }}
                                                                    onMouseEnter={(e) => showTooltip(e, (
                                                                        <>
                                                                            <div style={{ fontWeight: 700, marginBottom: '2px', borderBottom: '1px solid #555', paddingBottom: '2px' }}>Scoring Parameters</div>
                                                                            {Object.entries(globalParams).map(([k, v]) => (
                                                                                <div key={k}>
                                                                                    <span style={{ color: '#adb5bd' }}>{k}:</span> {typeof v === 'object' ? JSON.stringify(v) : String(v)}
                                                                                </div>
                                                                            ))}
                                                                        </>
                                                                    ))}
                                                                    onMouseLeave={hideTooltip}
                                                                >i</span>
                                                            )}
                                                        </div>
                                                        <table style={{ width: '100%', fontSize: '11px', borderCollapse: 'collapse', border: '1px solid #e9ecef', borderTop: 'none' }}>
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
                                                                                {isComputed && <span style={{ marginLeft: '4px', background: '#28a745', color: '#fff', padding: '2px 4px', borderRadius: '4px', fontSize: '9px', opacity: 0.8 }}>computed</span>}
                                                                                {isPerActionParams && typeData.params?.[item.actionId] && (
                                                                                    <span
                                                                                        style={{ color: '#6c757d', fontSize: '12px', cursor: 'help', marginLeft: '6px' }}
                                                                                        onClick={(e) => e.stopPropagation()}
                                                                                        onMouseEnter={(e) => showTooltip(e, (
                                                                                            <>
                                                                                                <div style={{ fontWeight: 700, marginBottom: '2px', borderBottom: '1px solid #555', paddingBottom: '2px' }}>Parameters</div>
                                                                                                {Object.entries(typeData.params![item.actionId]).map(([k, v]) => (
                                                                                                    <div key={k}>
                                                                                                        <span style={{ color: '#adb5bd' }}>{k}:</span> {typeof v === 'object' ? JSON.stringify(v) : String(v)}
                                                                                                    </div>
                                                                                                ))}
                                                                                            </>
                                                                                        ))}
                                                                                        onMouseLeave={hideTooltip}
                                                                                    >i</span>
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
                                        <div style={{ padding: '10px', textAlign: 'center', color: '#888', fontSize: '13px' }}>
                                            All actions already added
                                        </div>
                                    )}
                                    {(searchQuery && filteredActions.length === 0) && (
                                        <div style={{ padding: '10px', textAlign: 'center', color: '#888', fontSize: '13px' }}>
                                            No matching actions
                                        </div>
                                    )}
                                    {((!searchQuery && scoredActionsList.length === 0) || searchQuery) && filteredActions.map(a => (
                                        <div
                                            key={a.id}
                                            onClick={() => handleAddAction(a.id)}
                                            style={{
                                                padding: '6px 10px',
                                                cursor: simulating ? 'wait' : 'pointer',
                                                borderTop: '1px solid #eee',
                                                backgroundColor: simulating === a.id ? '#e7f1ff' : 'transparent',
                                                opacity: simulating && simulating !== a.id ? 0.5 : 1,
                                            }}
                                            onMouseEnter={(e) => { if (!simulating) (e.currentTarget as HTMLDivElement).style.backgroundColor = '#f0f0f0'; }}
                                            onMouseLeave={(e) => { if (simulating !== a.id) (e.currentTarget as HTMLDivElement).style.backgroundColor = 'transparent'; }}
                                        >
                                            <div style={{ fontWeight: 600, fontSize: '12px', color: '#333' }}>
                                                {simulating === a.id ? 'Simulating...' : a.id}
                                            </div>
                                            {a.description && (
                                                <div style={{ fontSize: '11px', color: '#777', marginTop: '2px' }}>
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
            {sortedActionEntries.length > 0 ? (
                sortedActionEntries.map(([id, details], index) => {
                    const maxRhoPct = details.max_rho != null ? (details.max_rho * 100).toFixed(1) : null;
                    const severity = details.max_rho != null
                        ? (details.max_rho > monitoringFactor ? 'red' as const : details.max_rho > (monitoringFactor - 0.05) ? 'orange' as const : 'green' as const)
                        : (details.is_rho_reduction ? 'green' as const : 'red' as const);
                    const severityColors = {
                        green: { border: '#28a745', badgeBg: '#d4edda', badgeText: '#155724', label: 'Solves overload' },
                        orange: { border: '#f0ad4e', badgeBg: '#fff3cd', badgeText: '#856404', label: 'Solved \u2014 low margin' },
                        red: { border: '#dc3545', badgeBg: '#f8d7da', badgeText: '#721c24', label: details.is_rho_reduction ? 'Still overloaded' : 'No reduction' },
                    };
                    const sc = severityColors[severity];
                    const isSelected = selectedActionId === id;
                    return (
                        <div key={id} style={{
                            background: isSelected ? '#e7f1ff' : 'white',
                            border: '1px solid #ddd',
                            borderRadius: '8px',
                            padding: '10px',
                            marginBottom: '10px',
                            boxShadow: isSelected ? '0 0 0 2px rgba(0,123,255,0.3), 0 2px 8px rgba(0,0,0,0.15)' : '0 2px 4px rgba(0,0,0,0.1)',
                            borderLeft: `5px solid ${isSelected ? '#007bff' : sc.border}`,
                            cursor: 'pointer',
                            transition: 'all 0.15s ease',
                        }} onClick={() => onActionSelect(id)}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                <h4 style={{ margin: 0, fontSize: '14px', color: isSelected ? '#0056b3' : undefined }}>
                                    #{index + 1} {'\u2014'} {id}
                                </h4>
                                <div style={{ display: 'flex', gap: '5px', alignItems: 'center' }}>
                                    {isSelected && (
                                        <span style={{ fontSize: '10px', fontWeight: 600, padding: '2px 6px', borderRadius: '4px', background: '#007bff', color: 'white' }}>
                                            VIEWING
                                        </span>
                                    )}
                                    <span style={{ fontSize: '11px', fontWeight: 600, padding: '2px 8px', borderRadius: '12px', background: sc.badgeBg, color: sc.badgeText }}>
                                        {sc.label}
                                    </span>
                                </div>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '8px', margin: '4px 0 5px' }}>
                                <p style={{ fontSize: '13px', margin: 0, flex: 1 }}>{details.description_unitaire}</p>
                                {(() => {
                                    const badgeBtn = (name: string, bg: string, color: string, title: string) => (
                                        <button key={name}
                                            style={{ padding: '2px 7px', borderRadius: '4px', border: 'none', cursor: 'pointer', fontSize: '11px', fontWeight: 600, textDecoration: 'underline dotted', flexShrink: 0, backgroundColor: bg, color }}
                                            title={title}
                                            onClick={(e) => { e.stopPropagation(); onAssetClick(id, name, 'action'); }}>
                                            {name}
                                        </button>
                                    );
                                    const vlName = nodesByEquipmentId
                                        ? getActionTargetVoltageLevel(details, id, nodesByEquipmentId)
                                        : null;
                                    if (vlName) return badgeBtn(vlName, '#d1fae5', '#065f46', `Zoom to voltage level ${vlName}`);
                                    const lineNames = edgesByEquipmentId
                                        ? getActionTargetLines(details, id, edgesByEquipmentId)
                                        : Array.from(new Set([
                                            ...Object.keys(details.action_topology?.lines_ex_bus || {}),
                                            ...Object.keys(details.action_topology?.lines_or_bus || {}),
                                        ]));
                                    if (lineNames.length > 0) return (
                                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', flexShrink: 0 }}>
                                            {lineNames.map(name => badgeBtn(name, '#dbeafe', '#1e40af', `Zoom to line ${name}`))}
                                        </div>
                                    );
                                    // Fallback: gen/load equipment names from topology
                                    const topo = details.action_topology;
                                    const equipNames = [
                                        ...Object.keys(topo?.gens_bus || {}),
                                        ...Object.keys(topo?.loads_bus || {}),
                                    ];
                                    if (equipNames.length > 0) return (
                                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', flexShrink: 0 }}>
                                            {equipNames.map(name => badgeBtn(name, '#dbeafe', '#1e40af', `Zoom to ${name}`))}
                                        </div>
                                    );
                                    return null;
                                })()}
                            </div>
                            <div style={{ fontSize: '12px', background: isSelected ? '#dce8f7' : '#f8f9fa', padding: '5px', marginTop: '5px' }}>
                                <div>Rho before: {renderRho(details.rho_before, id, 'n-1')}</div>
                                <div>Rho after: {renderRho(details.rho_after, id, 'action')}</div>
                                {maxRhoPct != null && (
                                    <div style={{ marginTop: '3px' }}>
                                        Max rho: <strong style={{ color: sc.border }}>{maxRhoPct}%</strong>
                                        {details.max_rho_line && (
                                            <span style={{ color: '#888' }}> on <button
                                                style={{ ...clickableLinkStyle, color: '#888' }}
                                                title={`Zoom to ${details.max_rho_line}`}
                                                onClick={(e) => { e.stopPropagation(); onAssetClick(id, details.max_rho_line, 'action'); }}
                                            >{details.max_rho_line}</button></span>
                                        )}
                                    </div>
                                )}
                            </div>
                        </div>
                    );
                })
            ) : (
                <p style={{ color: '#666', fontStyle: 'italic' }}>
                    {analysisLoading ? 'Processing...' : 'No actions available.'}
                </p>
            )}

            {/* Loading indicator shown below existing cards during analysis */}
            {analysisLoading && sortedActionEntries.length > 0 && (
                <div style={{
                    textAlign: 'center', padding: '12px', color: '#666',
                    fontStyle: 'italic', fontSize: '13px',
                    borderTop: '1px dashed #ccc', marginTop: '8px',
                }}>
                    ⏳ Running analysis...
                </div>
            )}

            {/* Fixed-position tooltip rendered outside any overflow context */}
            {tooltip && (
                <div style={{
                    position: 'fixed',
                    top: tooltip.y,
                    left: tooltip.x,
                    zIndex: 99999,
                    backgroundColor: '#343a40',
                    color: '#fff',
                    textAlign: 'left',
                    borderRadius: '4px',
                    padding: '6px 8px',
                    fontSize: '10px',
                    fontWeight: 'normal',
                    whiteSpace: 'nowrap',
                    boxShadow: '0 2px 8px rgba(0,0,0,0.4)',
                    lineHeight: 1.4,
                    pointerEvents: 'none',
                    maxWidth: '90vw',
                }}>
                    {tooltip.content}
                </div>
            )}
        </div>
    );
};

export default ActionFeed;
