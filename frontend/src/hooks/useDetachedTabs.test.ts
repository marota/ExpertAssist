// Copyright (c) 2025-2026, RTE (https://www.rte-france.com)
// This Source Code Form is subject to the terms of the Mozilla Public License, version 2.0.
// If a copy of the Mozilla Public License, version 2.0 was not distributed with this file,
// you can obtain one at http://mozilla.org/MPL/2.0/.
// SPDX-License-Identifier: MPL-2.0
// This file is part of Co-Study4Grid a Power Grid Study tool Assistant Interface to help solve contigencies for a grid state under study.

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useDetachedTabs } from './useDetachedTabs';

interface FakePopup {
    document: Document;
    closed: boolean;
    listeners: Record<string, Array<() => void>>;
    close: () => void;
    focus: () => void;
    addEventListener: (event: string, handler: () => void) => void;
    removeEventListener: (event: string, handler: () => void) => void;
    dispatch: (event: string) => void;
}

function createFakePopup(): FakePopup {
    // Build a fresh DOM via the main jsdom `document` — we simply use the
    // same document object for body/head since jsdom cannot spawn a second
    // one, but the hook only needs `.document.body`, `.document.head`, and
    // `createElement`, all of which this supports.
    const popupDoc = document.implementation.createHTMLDocument('popup');
    const listeners: Record<string, Array<() => void>> = {};
    const popup: FakePopup = {
        document: popupDoc,
        closed: false,
        listeners,
        close: () => { popup.closed = true; popup.dispatch('pagehide'); },
        focus: vi.fn(),
        addEventListener: (event, handler) => {
            (listeners[event] ||= []).push(handler);
        },
        removeEventListener: (event, handler) => {
            const arr = listeners[event];
            if (!arr) return;
            const idx = arr.indexOf(handler);
            if (idx >= 0) arr.splice(idx, 1);
        },
        dispatch: (event) => {
            (listeners[event] || []).slice().forEach(fn => fn());
        },
    };
    return popup;
}

describe('useDetachedTabs', () => {
    let fakePopups: FakePopup[];
    let openSpy: ReturnType<typeof vi.spyOn>;

    beforeEach(() => {
        fakePopups = [];
        openSpy = vi.spyOn(window, 'open').mockImplementation(() => {
            const popup = createFakePopup();
            fakePopups.push(popup);
            return popup as unknown as Window;
        });
    });

    afterEach(() => {
        openSpy.mockRestore();
    });

    it('starts with an empty detached map', () => {
        const { result } = renderHook(() => useDetachedTabs());
        expect(result.current.detachedTabs).toEqual({});
        expect(result.current.isDetached('n-1')).toBe(false);
    });

    it('detach opens a popup and records the tab', () => {
        const { result } = renderHook(() => useDetachedTabs());
        act(() => {
            result.current.detach('n-1');
        });
        expect(fakePopups).toHaveLength(1);
        expect(result.current.detachedTabs['n-1']).toBeDefined();
        expect(result.current.isDetached('n-1')).toBe(true);
        expect(result.current.detachedTabs['n-1']!.mountNode.id).toBe('costudy4grid-detached-root');
    });

    it('detaching the same tab twice focuses the existing popup', () => {
        const { result } = renderHook(() => useDetachedTabs());
        act(() => { result.current.detach('n-1'); });
        act(() => { result.current.detach('n-1'); });
        expect(fakePopups).toHaveLength(1);
        expect(fakePopups[0].focus).toHaveBeenCalled();
    });

    it('calls onPopupBlocked when window.open returns null', () => {
        openSpy.mockImplementation(() => null);
        const onPopupBlocked = vi.fn();
        const { result } = renderHook(() => useDetachedTabs({ onPopupBlocked }));
        let entry;
        act(() => {
            entry = result.current.detach('action');
        });
        expect(entry).toBeNull();
        expect(onPopupBlocked).toHaveBeenCalledTimes(1);
        expect(result.current.detachedTabs['action']).toBeUndefined();
    });

    it('reattach closes the popup and removes the entry', () => {
        const { result } = renderHook(() => useDetachedTabs());
        act(() => { result.current.detach('overflow'); });
        expect(result.current.isDetached('overflow')).toBe(true);
        act(() => { result.current.reattach('overflow'); });
        expect(result.current.detachedTabs['overflow']).toBeUndefined();
        expect(fakePopups[0].closed).toBe(true);
    });

    it('prunes a tab automatically when the popup fires pagehide', () => {
        const { result } = renderHook(() => useDetachedTabs());
        act(() => { result.current.detach('n'); });
        expect(result.current.isDetached('n')).toBe(true);
        act(() => {
            fakePopups[0].dispatch('pagehide');
        });
        expect(result.current.detachedTabs['n']).toBeUndefined();
    });

    it('different tabs can be detached independently', () => {
        const { result } = renderHook(() => useDetachedTabs());
        act(() => {
            result.current.detach('n-1');
            result.current.detach('action');
        });
        expect(fakePopups).toHaveLength(2);
        expect(result.current.isDetached('n-1')).toBe(true);
        expect(result.current.isDetached('action')).toBe(true);
        act(() => { result.current.reattach('n-1'); });
        expect(result.current.isDetached('n-1')).toBe(false);
        expect(result.current.isDetached('action')).toBe(true);
    });

    it('cleans up popups on hook unmount', () => {
        const { result, unmount } = renderHook(() => useDetachedTabs());
        act(() => { result.current.detach('n'); });
        const popup = fakePopups[0];
        expect(popup.closed).toBe(false);
        unmount();
        expect(popup.closed).toBe(true);
    });
});
