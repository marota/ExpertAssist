import React, { useRef, useCallback, useEffect } from 'react';
import { TransformWrapper, TransformComponent } from 'react-zoom-pan-pinch';
import type { ActionDetail, DiagramData } from '../types';

interface EdgeInfoMeta {
    svgId: string;
    infoType?: string;
    direction?: string;
    externalLabel?: string;
}

interface ElementMeta {
    equipmentId: string;
    svgId: string;
    edgeInfo1?: EdgeInfoMeta;
    edgeInfo2?: EdgeInfoMeta;
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
    actionViewMode: 'network' | 'delta';
}

const VisualizationPanel: React.FC<VisualizationPanelProps> = ({
    pdfUrl,
    actionDiagram,
    actionDiagramLoading,
    selectedActionId,
    onDeselectAction,
    linesOverloaded,
    selectedActionDetail,
    actionViewMode,
}) => {
    const svgContainerRef = useRef<HTMLDivElement>(null);

    // Highlight overloaded lines (orange) and action targets (yellow fluo halo) on action SVG
    // OR apply delta coloring (orange/blue/grey) when in delta mode
    useEffect(() => {
        const container = svgContainerRef.current;
        if (!container || !actionDiagram?.svg) return;

        // Clear ALL previous highlights (both modes)
        container.querySelectorAll('.nad-overloaded').forEach(el => el.classList.remove('nad-overloaded'));
        container.querySelectorAll('.nad-action-target').forEach(el => el.classList.remove('nad-action-target'));
        container.querySelectorAll('.nad-delta-positive').forEach(el => el.classList.remove('nad-delta-positive'));
        container.querySelectorAll('.nad-delta-negative').forEach(el => el.classList.remove('nad-delta-negative'));
        container.querySelectorAll('.nad-delta-grey').forEach(el => el.classList.remove('nad-delta-grey'));
        // Remove old background clones
        container.querySelectorAll('.nad-highlight-clone').forEach(el => el.remove());

        // Parse metadata to build equipmentId -> svgId mappings
        const meta: DiagramMetadata = typeof actionDiagram.metadata === 'string'
            ? JSON.parse(actionDiagram.metadata)
            : (actionDiagram.metadata as DiagramMetadata) ?? {};
        const edgesByEquipmentId = new Map<string, ElementMeta>();
        (meta.edges || []).forEach(e => edgesByEquipmentId.set(e.equipmentId, e));
        const nodesByEquipmentId = new Map<string, ElementMeta>();
        (meta.nodes || []).forEach(n => nodesByEquipmentId.set(n.equipmentId, n));

        // ===== DELTA MODE: apply delta coloring =====
        if (actionViewMode === 'delta' && actionDiagram.flow_deltas) {
            const flowDeltas = actionDiagram.flow_deltas;

            // Build id→element index in a single DOM traversal (O(n) once)
            // instead of thousands of querySelector calls (O(n) each)
            const idMap = new Map<string, Element>();
            container.querySelectorAll('[id]').forEach(el => {
                idMap.set(el.id, el);
            });

            for (const [lineId, deltaInfo] of Object.entries(flowDeltas)) {
                const edge = edgesByEquipmentId.get(lineId);
                if (!edge?.svgId) continue;

                // Apply delta color class on the edge path group
                const el = idMap.get(edge.svgId);
                if (el) {
                    const classMap: Record<string, string> = {
                        positive: 'nad-delta-positive',
                        negative: 'nad-delta-negative',
                        grey: 'nad-delta-grey',
                    };
                    const cls = classMap[deltaInfo.category];
                    if (cls) el.classList.add(cls);
                }

                // Replace edge info text labels with the delta value (same at both ends)
                const deltaStr = deltaInfo.delta >= 0 ? `+${deltaInfo.delta.toFixed(1)}` : deltaInfo.delta.toFixed(1);
                const edgeInfoIds = [
                    edge.edgeInfo1?.svgId,
                    edge.edgeInfo2?.svgId,
                ].filter(Boolean) as string[];

                for (const infoSvgId of edgeInfoIds) {
                    const infoEl = idMap.get(infoSvgId);
                    if (!infoEl) continue;
                    const textTargets = infoEl.querySelectorAll('foreignObject, text');
                    textTargets.forEach(t => {
                        t.textContent = `Δ ${deltaStr}`;
                    });
                }
            }
        }

        if (!selectedActionDetail) return;

        // Create or find background layer at the root of the SVG
        let backgroundLayer = container.querySelector('#nad-background-layer');
        if (!backgroundLayer) {
            const svg = container.querySelector('svg');
            if (svg) {
                backgroundLayer = document.createElementNS('http://www.w3.org/2000/svg', 'g');
                backgroundLayer.setAttribute('id', 'nad-background-layer');
                // Insert as first child to be behind everything else
                if (svg.firstChild) {
                    svg.insertBefore(backgroundLayer, svg.firstChild);
                } else {
                    svg.appendChild(backgroundLayer);
                }
            }
        }

        const highlightById = (svgId: string, className: string) => {
            const el = container.querySelector(`[id="${svgId}"]`) as SVGGraphicsElement;
            if (el) {
                // Determine if we should clone for background effect
                if (className === 'nad-action-target') {
                    // Clone and move to background layer
                    if (backgroundLayer) {
                        const clone = el.cloneNode(true) as SVGGraphicsElement;
                        clone.removeAttribute('id');
                        clone.classList.add(className);
                        clone.classList.add('nad-highlight-clone'); // Marker for cleanup

                        // Calculate transformation to root coordinate system
                        try {
                            // getCTM returns the matrix from current user units to viewport
                            // We want to apply this matrix to the clone at the root level
                            const ctm = el.getCTM();
                            if (ctm) {
                                // Apply CTM as transform
                                const matrixStr = `matrix(${ctm.a}, ${ctm.b}, ${ctm.c}, ${ctm.d}, ${ctm.e}, ${ctm.f})`;
                                clone.setAttribute('transform', matrixStr);
                            }
                        } catch (e) {
                            console.warn('Failed to get CTM for highlight:', e);
                        }

                        backgroundLayer.appendChild(clone);
                    }
                } else {
                    // For overloaded lines, keep existing behavior
                    el.classList.add(className);
                }
            } else {
                console.warn(`VisualizationPanel: Could not find SVG element with id="${svgId}" to apply class "${className}"`);
            }
        };

        // ===== NETWORK MODE ONLY: overloaded line highlights =====
        if (actionViewMode !== 'delta') {
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
        }

        // ===== BOTH MODES: action target highlights (yellow fluo halo) =====
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
    }, [actionDiagram, linesOverloaded, selectedActionDetail, selectedActionId, actionViewMode]);

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
