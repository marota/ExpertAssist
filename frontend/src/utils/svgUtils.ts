import type { ViewBox, MetadataIndex, NodeMeta, EdgeMeta, ActionDetail } from '../types';

/**
 * Scale SVG elements for large grids so text, nodes, and flow values
 * are readable when zoomed in and naturally shrink at full view.
 */
export const boostSvgForLargeGrid = (svgString: string, viewBox: ViewBox | null, vlCount: number): string => {
    if (!viewBox) return svgString;

    // Skip boost entirely for grids with < 500 voltage levels
    if (!vlCount || vlCount < 500) return svgString;

    const diagramSize = Math.max(viewBox.w, viewBox.h);
    const REFERENCE_SIZE = 1250;
    const BOOST_THRESHOLD = 3;
    const ratio = diagramSize / REFERENCE_SIZE;
    if (ratio <= BOOST_THRESHOLD) return svgString;

    const boost = Math.sqrt(ratio / BOOST_THRESHOLD);
    console.log(`[SVG] vlCount=${vlCount}, viewBox ${diagramSize.toFixed(0)}, ratio ${ratio.toFixed(2)}, boost ${boost.toFixed(2)}`);

    const parser = new DOMParser();
    const doc = parser.parseFromString(svgString, 'image/svg+xml');
    const svgEl = doc.documentElement;

    if (ratio > 6) {
        svgEl.setAttribute('data-large-grid', 'true');
    }

    // === 1. Scale CSS values in <style> blocks ===
    const styles = svgEl.querySelectorAll('style');
    styles.forEach(style => {
        let css = style.textContent || '';
        css = css.replace(/font:\s*25px\s+serif/, `font: ${Math.round(25 * boost)}px serif`);
        css = css.replace(
            'padding: 10px; border-radius: 10px;',
            `padding: ${Math.round(10 * boost)}px; border-radius: ${Math.round(10 * boost)}px;`
        );
        css = css.replace(
            'margin-right: 10px; width: 20px; height: 20px;',
            `margin-right: ${Math.round(10 * boost)}px; width: ${Math.round(20 * boost)}px; height: ${Math.round(20 * boost)}px;`
        );
        style.textContent = css;
    });

    // === 2. Scale node groups (circles + inner bus sectors/paths) ===
    const scaledGroups = new Set<Element>();
    svgEl.querySelectorAll('circle').forEach(circle => {
        const g = circle.parentElement;
        if (!g || g.tagName !== 'g' || scaledGroups.has(g)) return;
        if (g.querySelector('foreignObject')) return;
        scaledGroups.add(g);
        const cx = parseFloat(circle.getAttribute('cx') || '0');
        const cy = parseFloat(circle.getAttribute('cy') || '0');
        const t = g.getAttribute('transform') || '';
        g.setAttribute('transform',
            `${t} translate(${cx},${cy}) scale(${boost.toFixed(2)}) translate(${-cx},${-cy})`);
    });

    // === 3. Scale edge-info group transforms (flow arrows + values) ===
    const edgeInfoGroup = svgEl.querySelector('.nad-edge-infos');
    if (edgeInfoGroup) {
        edgeInfoGroup.querySelectorAll(':scope > g[transform]').forEach(g => {
            const t = g.getAttribute('transform');
            if (t && t.includes('translate(') && !t.includes('scale(')) {
                g.setAttribute('transform', t + ` scale(${boost.toFixed(2)})`);
            }
        });
    }

    return new XMLSerializer().serializeToString(svgEl);
};

/**
 * Parse viewBox from raw SVG string and apply boost for large grids.
 */
export const processSvg = (rawSvg: string, vlCount: number): { svg: string; viewBox: ViewBox | null } => {
    const match = rawSvg.match(/viewBox=["']([^"']+)["']/);
    let vb: ViewBox | null = null;
    if (match) {
        const parts = match[1].split(/\s+|,/).map(parseFloat);
        if (parts.length === 4) vb = { x: parts[0], y: parts[1], w: parts[2], h: parts[3] };
    }

    const svg = boostSvgForLargeGrid(rawSvg, vb, vlCount);
    return { svg, viewBox: vb };
};

/**
 * Build Map indices from metadata for O(1) lookups.
 */
export const buildMetadataIndex = (metadata: unknown): MetadataIndex | null => {
    if (!metadata) return null;
    const meta = typeof metadata === 'string' ? JSON.parse(metadata) : metadata;
    const nodes: NodeMeta[] = (meta as { nodes?: NodeMeta[] }).nodes || [];
    const edges: EdgeMeta[] = (meta as { edges?: EdgeMeta[] }).edges || [];

    const nodesByEquipmentId = new Map<string, NodeMeta>();
    const nodesBySvgId = new Map<string, NodeMeta>();
    const edgesByEquipmentId = new Map<string, EdgeMeta>();
    const edgesByNode = new Map<string, EdgeMeta[]>();

    nodes.forEach(n => {
        nodesByEquipmentId.set(n.equipmentId, n);
        nodesBySvgId.set(n.svgId, n);
    });

    edges.forEach(e => {
        edgesByEquipmentId.set(e.equipmentId, e);
        if (!edgesByNode.has(e.node1)) edgesByNode.set(e.node1, []);
        edgesByNode.get(e.node1)!.push(e);
        if (!edgesByNode.has(e.node2)) edgesByNode.set(e.node2, []);
        edgesByNode.get(e.node2)!.push(e);
    });

    return { nodesByEquipmentId, nodesBySvgId, edgesByEquipmentId, edgesByNode };
};

/**
 * Apply orange highlights to overloaded line edges on a given SVG container.
 */
export const applyOverloadedHighlights = (
    container: HTMLElement,
    metaIndex: MetadataIndex,
    overloadedLines: string[],
) => {
    if (!container || !metaIndex || !overloadedLines || overloadedLines.length === 0) return;

    container.querySelectorAll('.nad-overloaded').forEach(el => el.classList.remove('nad-overloaded'));

    const { edgesByEquipmentId } = metaIndex;
    overloadedLines.forEach(lineName => {
        const edge = edgesByEquipmentId.get(lineName);
        if (edge && edge.svgId) {
            const el = container.querySelector(`[id="${edge.svgId}"]`);
            if (el) el.classList.add('nad-overloaded');
        }
    });
};

/**
 * Determine which lines an action acts upon (for line disconnection/reconnection actions).
 */
export const getActionTargetLines = (
    actionDetail: ActionDetail | null,
    actionId: string | null,
    edgesByEquipmentId: Map<string, EdgeMeta>,
): string[] => {
    const topo = actionDetail?.action_topology;
    if (topo) {
        const lineKeys = new Set([
            ...Object.keys(topo.lines_ex_bus || {}),
            ...Object.keys(topo.lines_or_bus || {}),
        ]);
        const genKeys = Object.keys(topo.gens_bus || {});
        const loadKeys = Object.keys(topo.loads_bus || {});

        if (lineKeys.size > 0 && genKeys.length === 0 && loadKeys.length === 0) {
            return [...lineKeys];
        }

        const allValues = [
            ...Object.values(topo.lines_ex_bus || {}),
            ...Object.values(topo.lines_or_bus || {}),
            ...Object.values(topo.gens_bus || {}),
            ...Object.values(topo.loads_bus || {}),
        ];
        if (allValues.length > 0 && allValues.every(v => v === -1)) {
            return [...lineKeys];
        }
    }

    if (actionId) {
        const parts = actionId.split('_');
        const candidate = parts[parts.length - 1];
        if (edgesByEquipmentId && edgesByEquipmentId.has(candidate)) {
            return [candidate];
        }
    }

    return [];
};

/**
 * Extract the voltage level name for nodal actions.
 * Skips pure line actions so that line edge highlights are not suppressed.
 */
export const getActionTargetVoltageLevel = (
    actionDetail: ActionDetail | null,
    actionId: string | null,
    nodesByEquipmentId: Map<string, NodeMeta>,
): string | null => {
    const topo = actionDetail?.action_topology;

    // Pure line action (lines only, no gen/load changes) → not a nodal action
    if (topo) {
        const lineKeys = new Set([
            ...Object.keys(topo.lines_ex_bus || {}),
            ...Object.keys(topo.lines_or_bus || {}),
        ]);
        const genKeys = Object.keys(topo.gens_bus || {});
        const loadKeys = Object.keys(topo.loads_bus || {});
        if (lineKeys.size > 0 && genKeys.length === 0 && loadKeys.length === 0) {
            return null;
        }
    }

    const desc = actionDetail?.description_unitaire;
    if (desc && desc !== 'No description available') {
        // Try all quoted strings (last-first) — any might be the VL name
        const quotedMatches = desc.match(/'([^']+)'/g);
        if (quotedMatches) {
            for (let i = quotedMatches.length - 1; i >= 0; i--) {
                const vl = quotedMatches[i].replace(/'/g, '');
                if (nodesByEquipmentId.has(vl)) return vl;
            }
        }
        const posteMatch = desc.match(/dans le poste\s+(\S+)/i);
        if (posteMatch) {
            const vl = posteMatch[1].replace(/['"]/g, '');
            if (nodesByEquipmentId.has(vl)) return vl;
        }
    }

    // Derive VL from gen/load names: strip prefix before first "." (e.g. GEN.PY762 → PY762)
    if (topo) {
        const equipNames = [
            ...Object.keys(topo.gens_bus || {}),
            ...Object.keys(topo.loads_bus || {}),
        ];
        for (const name of equipNames) {
            const dotIdx = name.indexOf('.');
            if (dotIdx >= 0) {
                const suffix = name.substring(dotIdx + 1);
                if (nodesByEquipmentId.has(suffix)) return suffix;
            }
        }
    }

    // Fallback: last _-separated segment of action ID
    if (actionId) {
        const parts = actionId.split('_');
        const candidate = parts[parts.length - 1];
        if (nodesByEquipmentId.has(candidate)) return candidate;
    }
    return null;
};

/**
 * Apply yellow fluo halo to action targets: edges (line actions) or nodes (nodal actions).
 */
export const applyActionTargetHighlights = (
    container: HTMLElement,
    metaIndex: MetadataIndex | null,
    actionDetail: ActionDetail | null,
    actionId: string | null,
) => {
    if (!container) return;
    container.querySelectorAll('.nad-action-target').forEach(el => el.classList.remove('nad-action-target'));
    container.querySelectorAll('.nad-highlight-clone').forEach(el => el.remove());
    if (!metaIndex || !actionDetail) return;

    const { edgesByEquipmentId, nodesByEquipmentId } = metaIndex;

    // Create or find background layer at the root of the SVG
    let backgroundLayer = container.querySelector('#nad-background-layer');
    if (!backgroundLayer) {
        const svg = container.querySelector('svg');
        if (svg) {
            backgroundLayer = document.createElementNS('http://www.w3.org/2000/svg', 'g');
            backgroundLayer.setAttribute('id', 'nad-background-layer');
            if (svg.firstChild) {
                svg.insertBefore(backgroundLayer, svg.firstChild);
            } else {
                svg.appendChild(backgroundLayer);
            }
        }
    }

    const applyHighlight = (el: Element) => {
        if (!el) return;

        if (backgroundLayer) {
            const clone = el.cloneNode(true) as SVGGraphicsElement;
            clone.removeAttribute('id');
            clone.classList.add('nad-action-target');
            clone.classList.add('nad-highlight-clone');

            try {
                const elCTM = (el as SVGGraphicsElement).getScreenCTM();
                const bgCTM = (backgroundLayer as unknown as SVGGraphicsElement).getScreenCTM();
                if (elCTM && bgCTM) {
                    const relativeCTM = bgCTM.inverse().multiply(elCTM);
                    const matrixStr = `matrix(${relativeCTM.a}, ${relativeCTM.b}, ${relativeCTM.c}, ${relativeCTM.d}, ${relativeCTM.e}, ${relativeCTM.f})`;
                    clone.setAttribute('transform', matrixStr);
                }
            } catch (e) {
                console.warn('Failed to get CTM for highlight:', e);
            }
            backgroundLayer.appendChild(clone);
        } else {
            el.classList.add('nad-action-target');
        }
    };

    // 1. Try VL detection first (handles nodal AND coupler actions)
    const vlName = getActionTargetVoltageLevel(actionDetail, actionId, nodesByEquipmentId);
    if (vlName) {
        const node = nodesByEquipmentId.get(vlName);
        if (node && node.svgId) {
            const el = container.querySelector(`[id="${node.svgId}"]`);
            if (el) {
                applyHighlight(el);
                return;
            }
        }
    }

    // 2. Fall back to line action: highlight edges from topology or action ID
    const targetLines = getActionTargetLines(actionDetail, actionId, edgesByEquipmentId);
    targetLines.forEach(lineName => {
        const edge = edgesByEquipmentId.get(lineName);
        if (edge && edge.svgId) {
            const el = container.querySelector(`[id="${edge.svgId}"]`);
            if (el) applyHighlight(el);
        }
    });
};

/**
 * Apply delta flow visualizations (coloring + text replacement) on a container.
 * Saves original text in data-original-text attribute for restoration.
 */
export const applyDeltaVisuals = (
    container: HTMLElement | null,
    diagram: { flow_deltas?: Record<string, { delta: number; category: string }> } | null,
    metaIndex: MetadataIndex | null,
    isDeltaMode: boolean,
) => {
    if (!container || !diagram || !metaIndex) return;

    // Clear delta classes
    container.querySelectorAll('.nad-delta-positive').forEach(el => el.classList.remove('nad-delta-positive'));
    container.querySelectorAll('.nad-delta-negative').forEach(el => el.classList.remove('nad-delta-negative'));
    container.querySelectorAll('.nad-delta-grey').forEach(el => el.classList.remove('nad-delta-grey'));

    // Restore original text labels
    container.querySelectorAll('[data-original-text]').forEach(el => {
        el.textContent = el.getAttribute('data-original-text');
        el.removeAttribute('data-original-text');
    });

    if (!isDeltaMode || !diagram.flow_deltas) return;

    const { edgesByEquipmentId } = metaIndex;
    const flowDeltas = diagram.flow_deltas;
    const idMap = new Map<string, Element>();
    container.querySelectorAll('[id]').forEach(el => idMap.set(el.id, el));

    for (const [lineId, deltaInfo] of Object.entries(flowDeltas)) {
        const edge = edgesByEquipmentId.get(lineId);
        if (!edge || !edge.svgId) continue;

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

        const deltaStr = deltaInfo.delta >= 0 ? `+${deltaInfo.delta.toFixed(1)}` : deltaInfo.delta.toFixed(1);
        const edgeInfoIds = [edge.edgeInfo1?.svgId, edge.edgeInfo2?.svgId].filter(Boolean) as string[];

        for (const infoSvgId of edgeInfoIds) {
            const infoEl = idMap.get(infoSvgId);
            if (!infoEl) continue;
            const textTargets = infoEl.querySelectorAll('foreignObject, text');
            textTargets.forEach(t => {
                if (!t.hasAttribute('data-original-text')) {
                    t.setAttribute('data-original-text', t.textContent || '');
                }
                t.textContent = `\u0394 ${deltaStr}`;
            });
        }
    }
};
