// Copyright (c) 2025-2026, RTE (https://www.rte-france.com)
// This Source Code Form is subject to the terms of the Mozilla Public License, version 2.0.
// If a copy of the Mozilla Public License, version 2.0 was not distributed with this file,
// you can obtain one at http://mozilla.org/MPL/2.0/.
// SPDX-License-Identifier: MPL-2.0
// This file is part of Co-Study4Grid a Power Grid Study tool Assistant Interface to help solve contigencies for a grid state under study.

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useTiedTabsSync, type PZMap, type PZInstance } from './useTiedTabsSync';
import type { ViewBox, TabId } from '../types';
import { interactionLogger } from '../utils/interactionLogger';

/**
 * Tests for the "tied detached tabs" feature (see
 * docs/detachable-viz-tabs.md#tied-detached-tabs).
 *
 * The hook mirrors a tied detached tab's viewBox one-way into the
 * main window's active tab. These tests verify:
 *
 *   1. The hook starts with no tied tabs.
 *   2. `tie`/`untie`/`toggleTie` update the set and log events.
 *   3. When a tab is tied AND detached, its viewBox is mirrored
 *      into the active tab's PZ.
 *   4. When the tab is tied but NOT detached, no mirroring happens
 *      (tying only makes sense in combination with detach).
 *   5. When activeTab equals the tied tab, mirroring is a no-op
 *      (same PZ — avoid pointless writes).
 */

// Each mock PZ exposes the real PZInstance shape (viewBox +
// setViewBox) so the hook accepts it unchanged. We cast through
// `unknown` instead of `any` so the file stays lint-clean.
interface MockPZ extends PZInstance {
    _state: { vb: ViewBox | null };
}

function makePZ(initial: ViewBox | null = null): MockPZ {
    const state = { vb: initial };
    const setViewBox = vi.fn((vb: ViewBox) => { state.vb = vb; });
    return {
        _state: state,
        setViewBox: setViewBox as unknown as PZInstance['setViewBox'],
        get viewBox() { return state.vb; },
    } as unknown as MockPZ;
}

function makePZMap(
    nVb: ViewBox | null = null,
    n1Vb: ViewBox | null = null,
    actionVb: ViewBox | null = null,
): PZMap {
    return {
        'n': makePZ(nVb),
        'n-1': makePZ(n1Vb),
        'action': makePZ(actionVb),
    };
}

// Helper: read the setViewBox spy from a PZ instance without
// sprinkling `as any` at each callsite.
function setViewBoxSpy(pz: PZInstance): ReturnType<typeof vi.fn> {
    return pz.setViewBox as unknown as ReturnType<typeof vi.fn>;
}

describe('useTiedTabsSync', () => {
    beforeEach(() => {
        interactionLogger.clear();
    });

    it('starts with an empty tied set', () => {
        const pz = makePZMap();
        const { result } = renderHook(() =>
            useTiedTabsSync(pz, 'n', {}),
        );
        expect(result.current.tiedTabs.size).toBe(0);
        expect(result.current.isTied('n')).toBe(false);
        expect(result.current.isTied('n-1')).toBe(false);
        expect(result.current.isTied('action')).toBe(false);
    });

    it('tie/untie add and remove tab ids from the set and log events', () => {
        const pz = makePZMap();
        const { result } = renderHook(() =>
            useTiedTabsSync(pz, 'n', {}),
        );

        act(() => { result.current.tie('n-1'); });
        expect(result.current.isTied('n-1')).toBe(true);
        expect(interactionLogger.getLog().some(e => e.type === 'tab_tied')).toBe(true);

        act(() => { result.current.untie('n-1'); });
        expect(result.current.isTied('n-1')).toBe(false);
        expect(interactionLogger.getLog().some(e => e.type === 'tab_untied')).toBe(true);
    });

    it('toggleTie flips membership and logs the appropriate event', () => {
        const pz = makePZMap();
        const { result } = renderHook(() =>
            useTiedTabsSync(pz, 'n', {}),
        );

        act(() => { result.current.toggleTie('action'); });
        expect(result.current.isTied('action')).toBe(true);

        act(() => { result.current.toggleTie('action'); });
        expect(result.current.isTied('action')).toBe(false);

        const events = interactionLogger.getLog().map(e => e.type);
        expect(events).toContain('tab_tied');
        expect(events).toContain('tab_untied');
    });

    it('does not mirror anything when no tabs are tied', () => {
        const pz = makePZMap({ x: 0, y: 0, w: 100, h: 100 });
        renderHook(() =>
            useTiedTabsSync(pz, 'action', {}),
        );
        // Only the target PZ — no tied tabs means no mirroring call.
        expect(setViewBoxSpy(pz['action'])).not.toHaveBeenCalled();
    });

    it('does not mirror when the tab is tied but NOT detached', () => {
        const pz = makePZMap(
            { x: 0, y: 0, w: 100, h: 100 }, // n
            null,                           // n-1
            null,                           // action
        );
        const { result } = renderHook(
            ({ dt }: { dt: Partial<Record<TabId, unknown>> }) =>
                useTiedTabsSync(pz, 'action', dt),
            { initialProps: { dt: {} as Partial<Record<TabId, unknown>> } },
        );

        act(() => { result.current.tie('n'); });

        // No detachedTabs['n'] → no mirror, even though 'n' is tied.
        expect(setViewBoxSpy(pz['action'])).not.toHaveBeenCalled();
    });

    it('mirrors a tied+detached tab\'s viewBox into the main window\'s active PZ', () => {
        const nVb: ViewBox = { x: 10, y: 20, w: 100, h: 100 };
        const pz = makePZMap(nVb, null, null);
        const detachedTabs = { n: { mountNode: document.createElement('div') } };

        const { result } = renderHook(() =>
            useTiedTabsSync(pz, 'action', detachedTabs),
        );
        // Tie 'n' and trigger a re-run of the effect.
        act(() => { result.current.tie('n'); });

        // The main window's active tab is 'action', so the mirror
        // target is actionPZ. Its setViewBox should have been called
        // with the source viewBox.
        const actionSet = setViewBoxSpy(pz['action']);
        expect(actionSet).toHaveBeenCalledWith(nVb);
    });

    it('does NOT mirror when activeTab equals the tied tab (same PZ, pointless)', () => {
        const nVb: ViewBox = { x: 0, y: 0, w: 50, h: 50 };
        const pz = makePZMap(nVb, null, null);
        const detachedTabs = { n: { mountNode: document.createElement('div') } };

        const { result } = renderHook(() =>
            useTiedTabsSync(pz, 'n', detachedTabs),
        );
        act(() => { result.current.tie('n'); });

        // activeTab === 'n' === tied tab → no mirroring.
        const nSet = setViewBoxSpy(pz['n']);
        expect(nSet).not.toHaveBeenCalled();
    });

    it('is a no-op on the overflow tab', () => {
        const pz = makePZMap({ x: 0, y: 0, w: 100, h: 100 });
        const detachedTabs = { n: { mountNode: document.createElement('div') } };
        const { result } = renderHook(() =>
            useTiedTabsSync(pz, 'overflow', detachedTabs),
        );
        act(() => { result.current.tie('n'); });
        // None of the PZs should have been written.
        expect(setViewBoxSpy(pz['n'])).not.toHaveBeenCalled();
        expect(setViewBoxSpy(pz['n-1'])).not.toHaveBeenCalled();
        expect(setViewBoxSpy(pz['action'])).not.toHaveBeenCalled();
    });
});
