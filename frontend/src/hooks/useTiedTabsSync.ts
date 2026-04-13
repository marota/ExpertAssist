// Copyright (c) 2025-2026, RTE (https://www.rte-france.com)
// This Source Code Form is subject to the terms of the Mozilla Public License, version 2.0.
// If a copy of the Mozilla Public License, version 2.0 was not distributed with this file,
// you can obtain one at http://mozilla.org/MPL/2.0/.
// SPDX-License-Identifier: MPL-2.0
// This file is part of Co-Study4Grid a Power Grid Study tool Assistant Interface to help solve contigencies for a grid state under study.

import { useCallback, useEffect, useRef, useState } from 'react';
import type { TabId, ViewBox } from '../types';
import type { usePanZoom } from './usePanZoom';
import { interactionLogger } from '../utils/interactionLogger';

/**
 * "Tied" detached tabs feature.
 *
 * When a detached tab is "tied", the operator wants its pan/zoom
 * region to stay synchronized with the main window's active tab —
 * useful for side-by-side comparison (e.g., comparing the Network (N)
 * view in one window with the Remedial Action variant in the main
 * window, keeping both views focused on the same substation).
 *
 * Sync is **one-way**, from the detached popup to the main window.
 * Zooming or panning in the popup mirrors the viewBox into the main
 * window's active tab. Zooming in the main window does NOT push back
 * into the popup. This deliberate asymmetry prevents ping-pong loops
 * and gives the operator a predictable mental model: "the popup is
 * the driver, the main follows".
 *
 * Implementation detail: the effect uses a ref-based guard
 * (`lastMirroredRef`) to skip no-op applies — the underlying
 * `setViewBox` already bails on equality, but the guard keeps the
 * interaction log clean and avoids useless DOM attribute writes.
 */
export type PZInstance = ReturnType<typeof usePanZoom>;

export interface PZMap {
    'n': PZInstance;
    'n-1': PZInstance;
    'action': PZInstance;
}

export interface UseTiedTabsSyncResult {
    /** Which detached tabs are currently tied to the main window. */
    tiedTabs: Set<TabId>;
    /** True iff tabId is currently in the tied set. */
    isTied: (tabId: TabId) => boolean;
    /** Add tabId to the tied set. */
    tie: (tabId: TabId) => void;
    /** Remove tabId from the tied set. */
    untie: (tabId: TabId) => void;
    /** Toggle tabId membership in the tied set. */
    toggleTie: (tabId: TabId) => void;
}

/**
 * @param pzMap           the pan/zoom instances for the three tabs
 *                         that support it (n / n-1 / action).
 * @param activeTab       the currently visible tab in the main window.
 * @param detachedTabs    the set of currently-detached tab IDs
 *                         (tying an undetached tab is a no-op).
 */
export function useTiedTabsSync(
    pzMap: PZMap,
    activeTab: TabId,
    detachedTabs: Partial<Record<TabId, unknown>>,
): UseTiedTabsSyncResult {
    const [tiedTabs, setTiedTabs] = useState<Set<TabId>>(() => new Set());
    const lastMirroredRef = useRef<ViewBox | null>(null);

    const tie = useCallback((tabId: TabId) => {
        setTiedTabs(prev => {
            if (prev.has(tabId)) return prev;
            const next = new Set(prev);
            next.add(tabId);
            interactionLogger.record('tab_tied', { tab: tabId });
            return next;
        });
    }, []);

    const untie = useCallback((tabId: TabId) => {
        setTiedTabs(prev => {
            if (!prev.has(tabId)) return prev;
            const next = new Set(prev);
            next.delete(tabId);
            interactionLogger.record('tab_untied', { tab: tabId });
            return next;
        });
    }, []);

    const toggleTie = useCallback((tabId: TabId) => {
        setTiedTabs(prev => {
            const next = new Set(prev);
            if (next.has(tabId)) {
                next.delete(tabId);
                interactionLogger.record('tab_untied', { tab: tabId });
            } else {
                next.add(tabId);
                interactionLogger.record('tab_tied', { tab: tabId });
            }
            return next;
        });
    }, []);

    const isTied = useCallback((tabId: TabId) => tiedTabs.has(tabId), [tiedTabs]);

    // Extract viewBoxes into locals so the effect deps list remains
    // shallow and ESLint-friendly.
    const nVb = pzMap['n'].viewBox;
    const n1Vb = pzMap['n-1'].viewBox;
    const actionVb = pzMap['action'].viewBox;

    useEffect(() => {
        if (tiedTabs.size === 0 || activeTab === 'overflow') return;
        // Target = the main window's currently-active PZ.
        const targetPZ = activeTab === 'n' ? pzMap['n']
            : activeTab === 'n-1' ? pzMap['n-1']
                : activeTab === 'action' ? pzMap['action']
                    : null;
        if (!targetPZ) return;

        // Find a tied-AND-detached tab to mirror from. If multiple are
        // tied we just pick the first — simultaneous multi-source sync
        // is not a useful workflow and would fight itself.
        let sourceVB: ViewBox | null = null;
        for (const tabId of tiedTabs) {
            if (!detachedTabs[tabId]) continue;
            if (tabId === activeTab) continue; // same PZ, pointless
            const sourcePZ = tabId === 'n' ? pzMap['n']
                : tabId === 'n-1' ? pzMap['n-1']
                    : tabId === 'action' ? pzMap['action']
                        : null;
            if (sourcePZ?.viewBox) {
                sourceVB = sourcePZ.viewBox;
                break;
            }
        }
        if (!sourceVB) return;

        // Guard: skip if we already mirrored this exact viewBox into
        // the target.
        const last = lastMirroredRef.current;
        if (last && last.x === sourceVB.x && last.y === sourceVB.y
            && last.w === sourceVB.w && last.h === sourceVB.h) {
            return;
        }
        lastMirroredRef.current = sourceVB;
        targetPZ.setViewBox(sourceVB);
    }, [tiedTabs, activeTab, detachedTabs, pzMap, nVb, n1Vb, actionVb]);

    return { tiedTabs, isTied, tie, untie, toggleTie };
}
