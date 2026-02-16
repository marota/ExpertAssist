import React, { useRef, useCallback, useEffect } from 'react';
import { TransformWrapper, TransformComponent } from 'react-zoom-pan-pinch';
import type { DiagramData } from '../types';

interface EdgeMeta {
    equipmentId: string;
    svgId: string;
    node1: string;
    node2: string;
}

interface DiagramMetadata {
    nodes?: unknown[];
    edges?: EdgeMeta[];
}

interface VisualizationPanelProps {
    pdfUrl: string | null;
    actionDiagram: DiagramData | null;
    actionDiagramLoading: boolean;
    selectedActionId: string | null;
    onDeselectAction: () => void;
    linesOverloaded: string[];
}

const VisualizationPanel: React.FC<VisualizationPanelProps> = ({
    pdfUrl,
    actionDiagram,
    actionDiagramLoading,
    selectedActionId,
    onDeselectAction,
    linesOverloaded,
}) => {
    const svgContainerRef = useRef<HTMLDivElement>(null);

    // Highlight overloaded lines in orange after the action SVG is rendered
    useEffect(() => {
        const container = svgContainerRef.current;
        if (!container || !actionDiagram?.svg || linesOverloaded.length === 0) return;

        // Parse metadata to build equipmentId -> svgId mapping
        const meta: DiagramMetadata = typeof actionDiagram.metadata === 'string'
            ? JSON.parse(actionDiagram.metadata)
            : (actionDiagram.metadata as DiagramMetadata) ?? {};

        const edges = meta.edges || [];
        const edgesByEquipmentId = new Map<string, EdgeMeta>();
        edges.forEach(e => edgesByEquipmentId.set(e.equipmentId, e));

        // Clear previous overloaded highlights
        container.querySelectorAll('.nad-overloaded').forEach(el => el.classList.remove('nad-overloaded'));

        // Apply orange highlight to each overloaded line's SVG edge element
        linesOverloaded.forEach(lineName => {
            const edge = edgesByEquipmentId.get(lineName);
            if (edge?.svgId) {
                const el = container.querySelector(`[id="${edge.svgId}"]`);
                if (el) el.classList.add('nad-overloaded');
            }
        });
    }, [actionDiagram, linesOverloaded]);

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
