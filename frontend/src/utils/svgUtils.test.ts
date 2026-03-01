import { describe, it, expect } from 'vitest';
import {
    processSvg,
    boostSvgForLargeGrid,
    buildMetadataIndex,
    getActionTargetLines,
    getActionTargetVoltageLevel,
} from './svgUtils';
import type { ActionDetail, NodeMeta, EdgeMeta } from '../types';

describe('processSvg', () => {
    it('extracts viewBox from SVG string', () => {
        const svg = '<svg viewBox="0 10 800 600"><rect/></svg>';
        const result = processSvg(svg, 10);
        expect(result.viewBox).toEqual({ x: 0, y: 10, w: 800, h: 600 });
    });

    it('returns null viewBox when not present', () => {
        const svg = '<svg><rect/></svg>';
        const result = processSvg(svg, 10);
        expect(result.viewBox).toBeNull();
    });

    it('returns svg string', () => {
        const svg = '<svg viewBox="0 0 100 100"><rect/></svg>';
        const result = processSvg(svg, 10);
        expect(result.svg).toContain('<svg');
    });

    it('handles viewBox with commas', () => {
        const svg = '<svg viewBox="0,0,500,400"><rect/></svg>';
        const result = processSvg(svg, 10);
        expect(result.viewBox).toEqual({ x: 0, y: 0, w: 500, h: 400 });
    });
});

describe('boostSvgForLargeGrid', () => {
    it('returns unchanged SVG for small grids (< 500 VLs)', () => {
        const svg = '<svg viewBox="0 0 1000 1000"><text>hello</text></svg>';
        const vb = { x: 0, y: 0, w: 1000, h: 1000 };
        const result = boostSvgForLargeGrid(svg, vb, 100);
        expect(result).toBe(svg);
    });

    it('returns unchanged SVG when viewBox is null', () => {
        const svg = '<svg><text>hello</text></svg>';
        const result = boostSvgForLargeGrid(svg, null, 600);
        expect(result).toBe(svg);
    });

    it('returns unchanged SVG when ratio <= threshold', () => {
        const svg = '<svg viewBox="0 0 1000 1000"><text>hello</text></svg>';
        // ratio = 1000/1250 = 0.8, below threshold of 3
        const vb = { x: 0, y: 0, w: 1000, h: 1000 };
        const result = boostSvgForLargeGrid(svg, vb, 600);
        expect(result).toBe(svg);
    });

    it('boosts SVG for large grids with high ratio', () => {
        // ratio = 10000/1250 = 8 > 3, should boost
        const svg = '<svg viewBox="0 0 10000 10000"><style>font: 25px serif</style><circle cx="100" cy="100" r="5"/></svg>';
        const vb = { x: 0, y: 0, w: 10000, h: 10000 };
        const result = boostSvgForLargeGrid(svg, vb, 600);
        expect(result).not.toBe(svg);
        expect(result).toContain('data-large-grid');
    });
});

describe('buildMetadataIndex', () => {
    it('returns null for null metadata', () => {
        expect(buildMetadataIndex(null)).toBeNull();
    });

    it('returns null for undefined metadata', () => {
        expect(buildMetadataIndex(undefined)).toBeNull();
    });

    it('builds index from object metadata', () => {
        const metadata = {
            nodes: [
                { equipmentId: 'VL1', svgId: 'svg-vl1', x: 100, y: 200 },
                { equipmentId: 'VL2', svgId: 'svg-vl2', x: 300, y: 400 },
            ],
            edges: [
                { equipmentId: 'LINE_A', svgId: 'svg-line-a', node1: 'svg-vl1', node2: 'svg-vl2' },
            ],
        };

        const index = buildMetadataIndex(metadata);
        expect(index).not.toBeNull();
        expect(index!.nodesByEquipmentId.get('VL1')?.svgId).toBe('svg-vl1');
        expect(index!.nodesBySvgId.get('svg-vl2')?.equipmentId).toBe('VL2');
        expect(index!.edgesByEquipmentId.get('LINE_A')?.svgId).toBe('svg-line-a');
        expect(index!.edgesByNode.get('svg-vl1')).toHaveLength(1);
        expect(index!.edgesByNode.get('svg-vl2')).toHaveLength(1);
    });

    it('builds index from JSON string metadata', () => {
        const metadata = JSON.stringify({
            nodes: [{ equipmentId: 'VL1', svgId: 'svg-1', x: 0, y: 0 }],
            edges: [],
        });

        const index = buildMetadataIndex(metadata);
        expect(index).not.toBeNull();
        expect(index!.nodesByEquipmentId.get('VL1')).toBeDefined();
    });

    it('handles empty nodes and edges', () => {
        const index = buildMetadataIndex({ nodes: [], edges: [] });
        expect(index).not.toBeNull();
        expect(index!.nodesByEquipmentId.size).toBe(0);
        expect(index!.edgesByEquipmentId.size).toBe(0);
    });

    it('handles missing nodes and edges', () => {
        const index = buildMetadataIndex({});
        expect(index).not.toBeNull();
        expect(index!.nodesByEquipmentId.size).toBe(0);
    });

    it('indexes edges by both nodes', () => {
        const metadata = {
            nodes: [],
            edges: [
                { equipmentId: 'LINE_X', svgId: 'svg-x', node1: 'n1', node2: 'n2' },
                { equipmentId: 'LINE_Y', svgId: 'svg-y', node1: 'n1', node2: 'n3' },
            ],
        };

        const index = buildMetadataIndex(metadata);
        expect(index!.edgesByNode.get('n1')).toHaveLength(2);
        expect(index!.edgesByNode.get('n2')).toHaveLength(1);
        expect(index!.edgesByNode.get('n3')).toHaveLength(1);
    });
});

describe('getActionTargetLines', () => {
    const makeEdgeMap = (...ids: string[]) => {
        const map = new Map<string, EdgeMeta>();
        ids.forEach(id => map.set(id, { equipmentId: id, svgId: `svg-${id}`, node1: '', node2: '' }));
        return map;
    };

    it('returns lines from topology when only lines are affected', () => {
        const detail: ActionDetail = {
            description_unitaire: 'Disconnect LINE_A',
            rho_before: null,
            rho_after: null,
            max_rho: null,
            max_rho_line: '',
            is_rho_reduction: false,
            action_topology: {
                lines_ex_bus: { LINE_A: -1 },
                lines_or_bus: { LINE_A: -1 },
                gens_bus: {},
                loads_bus: {},
            },
        };

        const result = getActionTargetLines(detail, 'disco_LINE_A', makeEdgeMap('LINE_A'));
        expect(result).toEqual(['LINE_A']);
    });

    it('returns lines when all topology values are -1 (disconnection)', () => {
        const detail: ActionDetail = {
            description_unitaire: 'Test',
            rho_before: null,
            rho_after: null,
            max_rho: null,
            max_rho_line: '',
            is_rho_reduction: false,
            action_topology: {
                lines_ex_bus: { LINE_A: -1, LINE_B: -1 },
                lines_or_bus: { LINE_A: -1 },
                gens_bus: { GEN1: -1 },
                loads_bus: { LOAD1: -1 },
            },
        };

        const result = getActionTargetLines(detail, null, makeEdgeMap('LINE_A', 'LINE_B'));
        expect(result).toContain('LINE_A');
        expect(result).toContain('LINE_B');
    });

    it('falls back to action ID suffix (last _ segment) when no topology', () => {
        const detail: ActionDetail = {
            description_unitaire: 'Test',
            rho_before: null,
            rho_after: null,
            max_rho: null,
            max_rho_line: '',
            is_rho_reduction: false,
        };

        // The function splits by '_' and takes the LAST segment
        // 'disco_LINE-X' → ['disco', 'LINE-X'] → candidate = 'LINE-X'
        const result = getActionTargetLines(detail, 'disco_LINE-X', makeEdgeMap('LINE-X'));
        expect(result).toEqual(['LINE-X']);
    });

    it('returns empty when action ID suffix not in edge map', () => {
        const detail: ActionDetail = {
            description_unitaire: 'Test',
            rho_before: null,
            rho_after: null,
            max_rho: null,
            max_rho_line: '',
            is_rho_reduction: false,
        };

        const result = getActionTargetLines(detail, 'disco_UNKNOWN', makeEdgeMap('LINE_A'));
        expect(result).toEqual([]);
    });

    it('returns empty for null action detail and null action id', () => {
        const result = getActionTargetLines(null, null, makeEdgeMap());
        expect(result).toEqual([]);
    });

    it('does not return lines when gens or loads are also affected', () => {
        const detail: ActionDetail = {
            description_unitaire: 'Complex action',
            rho_before: null,
            rho_after: null,
            max_rho: null,
            max_rho_line: '',
            is_rho_reduction: false,
            action_topology: {
                lines_ex_bus: { LINE_A: 1 },
                lines_or_bus: { LINE_A: 1 },
                gens_bus: { GEN_1: 1 },
                loads_bus: {},
            },
        };

        // With gens involved and values != -1, lines aren't pure line actions
        const result = getActionTargetLines(detail, null, makeEdgeMap('LINE_A'));
        expect(result).toEqual([]);
    });
});

describe('getActionTargetVoltageLevel', () => {
    const makeNodeMap = (...ids: string[]) => {
        const map = new Map<string, NodeMeta>();
        ids.forEach(id => map.set(id, { equipmentId: id, svgId: `svg-${id}`, x: 0, y: 0 }));
        return map;
    };

    it('extracts VL from quoted string in description', () => {
        const detail: ActionDetail = {
            description_unitaire: "Ouverture couplage dans le poste 'SUBSTATION_A'",
            rho_before: null,
            rho_after: null,
            max_rho: null,
            max_rho_line: '',
            is_rho_reduction: false,
        };

        const result = getActionTargetVoltageLevel(detail, null, makeNodeMap('SUBSTATION_A'));
        expect(result).toBe('SUBSTATION_A');
    });

    it('tries last quoted string first', () => {
        const detail: ActionDetail = {
            description_unitaire: "Action on 'IRRELEVANT' at poste 'VL_TARGET'",
            rho_before: null,
            rho_after: null,
            max_rho: null,
            max_rho_line: '',
            is_rho_reduction: false,
        };

        const result = getActionTargetVoltageLevel(detail, null, makeNodeMap('VL_TARGET'));
        expect(result).toBe('VL_TARGET');
    });

    it('falls back to action ID suffix', () => {
        const detail: ActionDetail = {
            description_unitaire: 'No description available',
            rho_before: null,
            rho_after: null,
            max_rho: null,
            max_rho_line: '',
            is_rho_reduction: false,
        };

        const result = getActionTargetVoltageLevel(detail, 'open_coupling_VL1', makeNodeMap('VL1'));
        expect(result).toBe('VL1');
    });

    it('returns null when no match found', () => {
        const detail: ActionDetail = {
            description_unitaire: 'Some generic action',
            rho_before: null,
            rho_after: null,
            max_rho: null,
            max_rho_line: '',
            is_rho_reduction: false,
        };

        const result = getActionTargetVoltageLevel(detail, 'action_UNKNOWN', makeNodeMap('VL1'));
        expect(result).toBeNull();
    });

    it('returns null for null detail', () => {
        const result = getActionTargetVoltageLevel(null, null, makeNodeMap('VL1'));
        expect(result).toBeNull();
    });

    it('skips action ID fallback for line reconnection actions', () => {
        const detail: ActionDetail = {
            description_unitaire: 'Reconnect line',
            rho_before: null,
            rho_after: null,
            max_rho: null,
            max_rho_line: '',
            is_rho_reduction: false,
            action_topology: {
                lines_ex_bus: { LINE_A: 1 },
                lines_or_bus: { LINE_A: 2 },
                gens_bus: {},
                loads_bus: {},
            },
        };

        // Even though action ID suffix matches a VL, should return null
        // because it's a line reconnection (lines with bus >= 0, no gen/load)
        const result = getActionTargetVoltageLevel(detail, 'reco_VL1', makeNodeMap('VL1'));
        expect(result).toBeNull();
    });
});
