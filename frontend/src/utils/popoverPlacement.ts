// Copyright (c) 2025-2026, RTE (https://www.rte-france.com)
// This Source Code Form is subject to the terms of the Mozilla Public License, version 2.0.
// If a copy of the Mozilla Public License, version 2.0 was not distributed with this file,
// you can obtain one at http://mozilla.org/MPL/2.0/.
// SPDX-License-Identifier: MPL-2.0
// This file is part of Co-Study4Grid a Power Grid Study tool Assistant Interface to help solve contigencies for a grid state under study.

import type { CSSProperties } from 'react';

/**
 * Pin-anchored popover placement helpers used by
 * `ActionOverviewDiagram`.
 *
 * Extracted into its own module so the component file only
 * exports React components — `react-refresh/only-export-components`
 * would otherwise refuse to fast-refresh the diagram when these
 * pure helpers were colocated with the JSX.
 */

/** Approximate popover dimensions used by the placement heuristic. */
export const POPOVER_WIDTH = 340;
export const POPOVER_MAX_HEIGHT = 480;
/** Pixel offset between the pin and the popover so the pin tip stays visible. */
export const POPOVER_PIN_OFFSET = 28;
/** Safety margin from the viewport edge. */
export const POPOVER_VIEWPORT_MARGIN = 8;

export interface PopoverPlacement {
    placeAbove: boolean;
    horizontalAlign: 'start' | 'center' | 'end';
}

const defaultViewport = (): { width: number; height: number } => ({
    width: typeof window !== 'undefined' ? window.innerWidth : 1024,
    height: typeof window !== 'undefined' ? window.innerHeight : 768,
});

/**
 * Decide where to anchor the popover relative to the pin so it
 * stays inside the viewport.
 *
 * Rules:
 *  - Vertical: place ABOVE if there's not enough room below for
 *    the full popover; otherwise BELOW. Falls back to whichever
 *    side has more room when neither side fits the full max
 *    height.
 *  - Horizontal: align the popover's LEFT edge to the pin if the
 *    pin is in the left third of the viewport, RIGHT edge if the
 *    pin is in the right third, otherwise CENTRE the popover on
 *    the pin.
 */
export const decidePopoverPlacement = (
    pinScreenX: number,
    pinScreenY: number,
    viewport: { width: number; height: number } = defaultViewport(),
): PopoverPlacement => {
    const spaceBelow = viewport.height - pinScreenY - POPOVER_PIN_OFFSET - POPOVER_VIEWPORT_MARGIN;
    const spaceAbove = pinScreenY - POPOVER_PIN_OFFSET - POPOVER_VIEWPORT_MARGIN;
    let placeAbove: boolean;
    if (spaceBelow >= POPOVER_MAX_HEIGHT) {
        placeAbove = false;
    } else if (spaceAbove >= POPOVER_MAX_HEIGHT) {
        placeAbove = true;
    } else {
        placeAbove = spaceAbove > spaceBelow;
    }

    let horizontalAlign: 'start' | 'center' | 'end';
    if (pinScreenX < viewport.width / 3) {
        horizontalAlign = 'start';
    } else if (pinScreenX > (viewport.width * 2) / 3) {
        horizontalAlign = 'end';
    } else {
        horizontalAlign = 'center';
    }
    return { placeAbove, horizontalAlign };
};

/**
 * Translate a placement decision into concrete CSS positioning.
 * Uses `bottom` rather than `top` for above-placement so the
 * popover anchors its bottom edge at the pin regardless of its
 * actual rendered height (avoids the white-gap when the popover
 * is shorter than POPOVER_MAX_HEIGHT).
 */
export const computePopoverStyle = (
    pin: { screenX: number; screenY: number } & PopoverPlacement,
    viewport: { width: number; height: number } = defaultViewport(),
): CSSProperties => {
    let left: number;
    if (pin.horizontalAlign === 'start') {
        left = pin.screenX - POPOVER_PIN_OFFSET;
    } else if (pin.horizontalAlign === 'end') {
        left = pin.screenX - POPOVER_WIDTH + POPOVER_PIN_OFFSET;
    } else {
        left = pin.screenX - POPOVER_WIDTH / 2;
    }
    // Clamp to viewport with a small margin.
    left = Math.max(
        POPOVER_VIEWPORT_MARGIN,
        Math.min(left, viewport.width - POPOVER_WIDTH - POPOVER_VIEWPORT_MARGIN),
    );

    if (pin.placeAbove) {
        return {
            position: 'fixed',
            left,
            bottom: viewport.height - pin.screenY + POPOVER_PIN_OFFSET,
        };
    }
    return {
        position: 'fixed',
        left,
        top: pin.screenY + POPOVER_PIN_OFFSET,
    };
};
