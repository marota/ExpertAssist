import React, { useRef, useCallback, useEffect } from 'react';
import { TransformWrapper, TransformComponent } from 'react-zoom-pan-pinch';
import type { ActionDetail, DiagramData } from '../types';

interface ElementMeta {
    equipmentId: string;
    svgId: string;
    [key: string]: unknown;
}

interface DiagramMetadata {
    nodes?: ElementMeta[];
    edges?: ElementMeta[];
}

interface VisualizationPanelProps {
    pdfUrl: string | null;
    actionDiagram: DiagramData | null;
    actionDiagramLoading: boolean;
    selectedActionId: string | null;
    onDeselectAction: () => void;
    linesOverloaded: string[];
    selectedActionDetail: ActionDetail | null;
}

const VisualizationPanel: React.FC<VisualizationPanelProps> = ({
    pdfUrl,
    actionDiagram,
    actionDiagramLoading,
    selectedActionId,
    onDeselectAction,
    linesOverloaded,
    selectedActionDetail,
}) => {
    const svgContainerRef = useRef<HTMLDivElement>(null);

    // Highlight overloaded lines (orange) and action targets (yellow fluo halo) on action SVG
    useEffect(() => {
        const container = svgContainerRef.current;
        if (!container || !actionDiagram?.svg) return;

        // Clear previous highlights
        container.querySelectorAll('.nad-overloaded').forEach(el => el.classList.remove('nad-overloaded'));
        container.querySelectorAll('.nad-action-target').forEach(el => el.classList.remove('nad-action-target'));

        if (!selectedActionDetail) return;

        // Parse metadata to build equipmentId -> svgId mappings
        const meta: DiagramMetadata = typeof actionDiagram.metadata === 'string'
            ? JSON.parse(actionDiagram.metadata)
            : (actionDiagram.metadata as DiagramMetadata) ?? {};
        const edgesByEquipmentId = new Map<string, ElementMeta>();
        (meta.edges || []).forEach(e => edgesByEquipmentId.set(e.equipmentId, e));
        const nodesByEquipmentId = new Map<string, ElementMeta>();
        (meta.nodes || []).forEach(n => nodesByEquipmentId.set(n.equipmentId, n));

        const highlightById = (svgId: string, className: string) => {
            const el = container.querySelector(`[id="${svgId}"]`);
            if (el) el.classList.add(className);
        };

        // Orange: lines that remain >100% after the action
        if (linesOverloaded.length > 0) {
            const stillOverloaded: string[] = [];
            if (selectedActionDetail.rho_after) {
                linesOverloaded.forEach((name, i) => {
                    if (selectedActionDetail.rho_after![i] != null && selectedActionDetail.rho_after![i] > 1.0) {
                        stillOverloaded.push(name);
                    }
                });
            }
            if (selectedActionDetail.max_rho != null && selectedActionDetail.max_rho > 1.0 && selectedActionDetail.max_rho_line) {
                if (!stillOverloaded.includes(selectedActionDetail.max_rho_line)) {
                    stillOverloaded.push(selectedActionDetail.max_rho_line);
                }
            }
            stillOverloaded.forEach(name => {
                const edge = edgesByEquipmentId.get(name);
                if (edge?.svgId) highlightById(edge.svgId, 'nad-overloaded');
            });
        }

        // Yellow fluo halo: action targets (VL node or line edges)
        // 1. Try VL detection first (handles nodal AND coupler actions)
        const findVoltageLevel = (): string | null => {
            const desc = selectedActionDetail.description_unitaire;
            if (desc && desc !== 'No description available') {
                const quotedMatches = desc.match(/'([^']+)'/g);
                if (quotedMatches && quotedMatches.length > 0) {
                    const vl = quotedMatches[quotedMatches.length - 1].replace(/'/g, '');
                    if (nodesByEquipmentId.has(vl)) return vl;
                }
                const posteMatch = desc.match(/dans le poste\s+(\S+)/i);
                if (posteMatch) {
                    const vl = posteMatch[1].replace(/['"]/g, '');
                    if (nodesByEquipmentId.has(vl)) return vl;
                }
            }
            if (selectedActionId) {
                const parts = selectedActionId.split('_');
                const candidate = parts[parts.length - 1];
                if (nodesByEquipmentId.has(candidate)) return candidate;
            }
            return null;
        };

        const vlName = findVoltageLevel();
        if (vlName) {
            const node = nodesByEquipmentId.get(vlName);
            if (node?.svgId) highlightById(node.svgId, 'nad-action-target');
        } else {
            // 2. Fall back to line action: highlight edges from topology
            const topo = selectedActionDetail.action_topology;
            if (topo) {
                const lineKeys = new Set([
                    ...Object.keys(topo.lines_ex_bus || {}),
                    ...Object.keys(topo.lines_or_bus || {}),
                ]);
                const genKeys = Object.keys(topo.gens_bus || {});
                const loadKeys = Object.keys(topo.loads_bus || {});

                let targetLines: string[] = [];
                if (lineKeys.size > 0 && genKeys.length === 0 && loadKeys.length === 0) {
                    targetLines = [...lineKeys];
                } else {
                    const allValues = [
                        ...Object.values(topo.lines_ex_bus || {}),
                        ...Object.values(topo.lines_or_bus || {}),
                        ...Object.values(topo.gens_bus || {}),
                        ...Object.values(topo.loads_bus || {}),
                    ];
                    if (allValues.length > 0 && allValues.every(v => v === -1)) {
                        targetLines = [...lineKeys];
                    }
                }
                targetLines.forEach(name => {
                    const edge = edgesByEquipmentId.get(name);
                    if (edge?.svgId) highlightById(edge.svgId, 'nad-action-target');
                });
            }
        }
    }, [actionDiagram, linesOverloaded, selectedActionDetail, selectedActionId]);

    const showingAction = selectedActionId !== null;
    const showingPdf = !showingAction && pdfUrl !== null;
    const showingEmpty = !showingAction && !showingPdf;

    const handleBackToOverflow = useCallback(() => {
        onDeselectAction();
    }, [onDeselectAction]);

    return (
        <div style={{ height: '100%', width: '100%', display: 'flex', flexDirection: 'column' }}>
            {/* Tab bar */}
            <div style={{
                display: 'flex',
                borderBottom: '1px solid #ccc',
                backgroundColor: '#f0f0f0',
                flexShrink: 0,
            }}>
                <button
                    onClick={handleBackToOverflow}
                    style={{
                        flex: showingAction ? undefined : 1,
                        padding: '8px 16px',
                        border: 'none',
                        borderBottom: !showingAction ? '3px solid #27ae60' : 'none',
                        backgroundColor: !showingAction ? 'white' : '#ecf0f1',
                        color: !showingAction ? '#2c3e50' : '#7f8c8d',
                        cursor: 'pointer',
                        fontWeight: !showingAction ? 600 : 400,
                        fontSize: '0.85rem',
                    }}
                >
                    Overflow Graph
                </button>
                {showingAction && (
                    <button
                        style={{
                            flex: 1,
                            padding: '8px 16px',
                            border: 'none',
                            borderBottom: '3px solid #007bff',
                            backgroundColor: 'white',
                            color: '#0056b3',
                            cursor: 'default',
                            fontWeight: 600,
                            fontSize: '0.85rem',
                        }}
                    >
                        Action: {selectedActionId}
                    </button>
                )}
            </div>

            {/* Content area */}
            <div style={{ flex: 1, position: 'relative', overflow: 'hidden' }}>
                {/* Action variant SVG view */}
                {showingAction && (
                    <>
                        {/* Convergence warning */}
                        {actionDiagram && actionDiagram.lf_converged === false && (
                            <div style={{
                                position: 'absolute', top: 0, left: 0, right: 0, zIndex: 10,
                                background: '#fff3cd', color: '#856404', padding: '6px 12px',
                                fontSize: '0.8rem', borderBottom: '1px solid #ffc107',
                                textAlign: 'center', pointerEvents: 'none',
                            }}>
                                AC load flow: {actionDiagram.lf_status || 'did not converge'} — voltage values may be missing or approximate
                            </div>
                        )}

                        {actionDiagramLoading ? (
                            <div style={{
                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                                height: '100%', color: '#999',
                            }}>
                                Generating diagram for action {selectedActionId}...
                            </div>
                        ) : actionDiagram?.svg ? (
                            <TransformWrapper
                                initialScale={1}
                                minScale={0.1}
                                maxScale={20}
                                wheel={{ step: 0.08 }}
                                panning={{ velocityDisabled: true }}
                            >
                                <TransformComponent
                                    wrapperStyle={{ width: '100%', height: '100%' }}
                                    contentStyle={{ width: '100%', height: '100%' }}
                                >
                                    <div
                                        ref={svgContainerRef}
                                        style={{ width: '100%', height: '100%' }}
                                        dangerouslySetInnerHTML={{ __html: actionDiagram.svg }}
                                    />
                                </TransformComponent>
                            </TransformWrapper>
                        ) : (
                            <div style={{
                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                                height: '100%', color: '#999',
                            }}>
                                Failed to load diagram for action {selectedActionId}.
                            </div>
                        )}
                    </>
                )}

                {/* PDF overflow graph view */}
                {showingPdf && (
                    <iframe
                        src={`http://localhost:8000${pdfUrl}`}
                        style={{ width: '100%', height: '100%', border: 'none' }}
                        title="Overflow Graph"
                    />
                )}

                {/* Empty state */}
                {showingEmpty && (
                    <div style={{
                        height: '100%',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        color: '#666',
                    }}>
                        Select an element and run analysis to view the Overflow Graph.
                    </div>
                )}
            </div>
        </div>
    );
};

export default VisualizationPanel;
