// Copyright (c) 2025-2026, RTE (https://www.rte-france.com)
// This Source Code Form is subject to the terms of the Mozilla Public License, version 2.0.
// If a copy of the Mozilla Public License, version 2.0 was not distributed with this file,
// you can obtain one at http://mozilla.org/MPL/2.0/.
// SPDX-License-Identifier: MPL-2.0
// This file is part of Co-Study4Grid a Power Grid Study tool Assistant Interface to help solve contigencies for a grid state under study.

import React, { useEffect, useLayoutEffect, useMemo, useRef } from 'react';
import type { ActionDetail, DiagramData, MetadataIndex } from '../types';
import { applyActionOverviewPins, buildActionOverviewPins } from '../utils/svgUtils';

/**
 * Action-overview diagram.
 *
 * When the Remedial Action tab is opened without any action card
 * selected, this view is rendered inside that tab. It shows the
 * N-1 NAD as an immutable background and overlays one Google-Maps
 * style pin per prioritised action, anchored on the asset the
 * corresponding action card highlights in its badges.
 *
 * Design notes:
 *  - We deliberately do NOT reuse `actionSvgContainerRef` /
 *    `actionPZ` from useDiagrams because those are tied to the
 *    post-action diagram. Mixing the two would blur the
 *    "overview vs drill-down" distinction and force us to
 *    invalidate the action diagram state on every pin refresh.
 *  - We DO re-use the N-1 metadata index (same positions that
 *    drive `applyActionTargetHighlights`), so a pin and the
 *    yellow halo for the same asset share one source of truth.
 *  - The view is pan/zoom-less by default — the pins already
 *    act as the overview; a user who wants to drill in clicks
 *    a pin (or the corresponding card) and gets the detailed
 *    action diagram that already supports zoom.
 */
interface ActionOverviewDiagramProps {
    n1Diagram: DiagramData | null;
    n1MetaIndex: MetadataIndex | null;
    actions: Record<string, ActionDetail> | undefined;
    monitoringFactor: number;
    /** Invoked when a pin is clicked — wired to the existing action-select flow. */
    onActionSelect: (actionId: string) => void;
    visible: boolean;
}

const ActionOverviewDiagram: React.FC<ActionOverviewDiagramProps> = ({
    n1Diagram,
    n1MetaIndex,
    actions,
    monitoringFactor,
    onActionSelect,
    visible,
}) => {
    const containerRef = useRef<HTMLDivElement | null>(null);

    // Build the pin list — pure, memo-able, independent from DOM.
    const pins = useMemo(() => {
        if (!n1MetaIndex || !actions) return [];
        return buildActionOverviewPins(actions, n1MetaIndex, monitoringFactor);
    }, [n1MetaIndex, actions, monitoringFactor]);

    // Inject / re-inject the N-1 SVG into our own container whenever
    // the source SVG string changes. Using innerHTML (instead of
    // mutating the shared parsed SVG from useDiagrams) guarantees we
    // get a standalone DOM subtree — the N-1 tab's own container is
    // untouched and keeps its viewBox / zoom state.
    useLayoutEffect(() => {
        const container = containerRef.current;
        if (!container) return;
        if (!n1Diagram?.svg) {
            container.innerHTML = '';
            return;
        }
        container.innerHTML = n1Diagram.svg;
        const svg = container.querySelector('svg');
        if (svg) {
            // Make the SVG fill the container — the existing
            // diagram SVGs embed their viewBox, so width/height
            // 100% lets the browser handle the fit.
            svg.setAttribute('width', '100%');
            svg.setAttribute('height', '100%');
            svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
            (svg as SVGSVGElement).style.width = '100%';
            (svg as SVGSVGElement).style.height = '100%';
        }
    }, [n1Diagram?.svg]);

    // (Re)apply pins whenever the underlying SVG or pin list changes.
    useEffect(() => {
        const container = containerRef.current;
        if (!container) return;
        applyActionOverviewPins(container, pins, onActionSelect);
    }, [pins, onActionSelect, n1Diagram?.svg]);

    const hasAnyAction = !!actions && Object.keys(actions).length > 0;
    const noBackground = !n1Diagram?.svg;

    return (
        <div
            data-testid="action-overview-diagram"
            style={{
                position: 'absolute',
                inset: 0,
                display: visible ? 'flex' : 'none',
                flexDirection: 'column',
                background: 'white',
                // Sit above the hidden MemoizedSvgContainer for
                // actionDiagram (which stays mounted to preserve
                // zoom state) so clicks land on the overview.
                zIndex: 15,
            }}
        >
            {/* Header strip — mirrors the severity legend used by
                the cards so the operator understands the colour
                encoding at a glance. */}
            <div
                style={{
                    flexShrink: 0,
                    padding: '8px 14px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: '10px',
                    fontSize: '12px',
                    background: '#f8fafc',
                    borderBottom: '1px solid #e2e8f0',
                    color: '#334155',
                }}
            >
                <div style={{ fontWeight: 700 }}>
                    {'\uD83D\uDCCD Remedial actions overview'}
                    {hasAnyAction && (
                        <span style={{ marginLeft: 8, fontWeight: 400, color: '#64748b' }}>
                            {pins.length} pin{pins.length === 1 ? '' : 's'} on the N-1 network
                        </span>
                    )}
                </div>
                <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
                    <Legend color="#28a745" label="Solves overload" />
                    <Legend color="#f0ad4e" label="Low margin" />
                    <Legend color="#dc3545" label="Still overloaded" />
                    <Legend color="#9ca3af" label="Divergent / islanded" />
                </div>
            </div>
            <div
                ref={containerRef}
                className="svg-container nad-action-overview-container"
                style={{
                    flex: 1,
                    overflow: 'hidden',
                    position: 'relative',
                }}
            />
            {noBackground && (
                <div style={{
                    position: 'absolute', inset: 0, top: 40,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    color: '#999', fontStyle: 'italic', textAlign: 'center', padding: '40px',
                    pointerEvents: 'none',
                }}>
                    Load a contingency first, then run the analysis to populate this overview.
                </div>
            )}
            {!noBackground && !hasAnyAction && (
                <div style={{
                    position: 'absolute', inset: 0, top: 40,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    color: '#999', fontStyle: 'italic', textAlign: 'center', padding: '40px',
                    pointerEvents: 'none',
                }}>
                    Run &ldquo;Analyze &amp; Suggest&rdquo; to see prioritised remedial actions as pins on the network.
                </div>
            )}
        </div>
    );
};

const Legend: React.FC<{ color: string; label: string }> = ({ color, label }) => (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
        <span
            aria-hidden
            style={{
                display: 'inline-block',
                width: 10,
                height: 10,
                borderRadius: '50%',
                background: color,
                border: '1px solid #1f2937',
            }}
        />
        <span style={{ color: '#475569' }}>{label}</span>
    </span>
);

export default React.memo(ActionOverviewDiagram);
