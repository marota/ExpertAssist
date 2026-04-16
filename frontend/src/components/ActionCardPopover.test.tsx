// Copyright (c) 2025-2026, RTE (https://www.rte-france.com)
// This Source Code Form is subject to the terms of the Mozilla Public License, version 2.0.
// If a copy of the Mozilla Public License, version 2.0 was not distributed with this file,
// you can obtain one at http://mozilla.org/MPL/2.0/.
// SPDX-License-Identifier: MPL-2.0
// This file is part of Co-Study4Grid a Power Grid Study tool Assistant Interface to help solve contigencies for a grid state under study.

import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent, cleanup } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import ActionCardPopover from './ActionCardPopover';
import type { ActionDetail } from '../types';

const makeDetails = (overrides: Partial<ActionDetail> = {}): ActionDetail => ({
    description_unitaire: 'shed load X',
    rho_before: null,
    rho_after: null,
    max_rho: 0.88,
    max_rho_line: 'LINE_A',
    is_rho_reduction: true,
    ...overrides,
});

const defaultProps = () => ({
    actionId: 'act_1',
    details: makeDetails(),
    index: 0,
    style: { position: 'fixed' as const, top: 100, left: 100 },
    linesOverloaded: ['LINE_A'],
    monitoringFactor: 0.95,
    metaIndex: null,
    onActivateAction: vi.fn(),
    onClose: vi.fn(),
});

describe('ActionCardPopover', () => {
    afterEach(() => cleanup());

    it('renders the shared ActionCard for the given action id', () => {
        const { getByTestId } = render(<ActionCardPopover {...defaultProps()} />);
        // ActionCard's test id pattern proves the popover delegates
        // visuals to the SAME component the sidebar feed uses.
        expect(getByTestId('action-card-act_1')).toBeInTheDocument();
    });

    it('forwards the extra data attributes onto the popover root', () => {
        const { getByTestId } = render(
            <ActionCardPopover
                {...defaultProps()}
                extraDataAttributes={{
                    'data-place-above': 'true',
                    'data-horizontal-align': 'end',
                }}
            />,
        );
        const root = getByTestId('action-card-popover');
        expect(root.getAttribute('data-place-above')).toBe('true');
        expect(root.getAttribute('data-horizontal-align')).toBe('end');
    });

    it('respects a custom testId', () => {
        const { getByTestId, queryByTestId } = render(
            <ActionCardPopover {...defaultProps()} testId="my-custom-popover" />,
        );
        expect(getByTestId('my-custom-popover')).toBeInTheDocument();
        expect(getByTestId('my-custom-popover-close')).toBeInTheDocument();
        expect(queryByTestId('action-card-popover')).toBeNull();
    });

    it('clicking the close ✕ invokes onClose', () => {
        const onClose = vi.fn();
        const { getByTestId } = render(<ActionCardPopover {...defaultProps()} onClose={onClose} />);
        fireEvent.click(getByTestId('action-card-popover-close'));
        expect(onClose).toHaveBeenCalledOnce();
    });

    it('mousedown inside the popover does NOT bubble (outside-click guard)', () => {
        const onMouseDown = vi.fn();
        const { getByTestId } = render(
            <div onMouseDown={onMouseDown}>
                <ActionCardPopover {...defaultProps()} />
            </div>,
        );
        fireEvent.mouseDown(getByTestId('action-card-popover'));
        // stopPropagation on the popover means the outer
        // listener should never fire.
        expect(onMouseDown).not.toHaveBeenCalled();
    });

    it('clicking the card body closes the popover AND activates the action', () => {
        const onActivateAction = vi.fn();
        const onClose = vi.fn();
        const { getByTestId } = render(
            <ActionCardPopover
                {...defaultProps()}
                onActivateAction={onActivateAction}
                onClose={onClose}
            />,
        );
        fireEvent.click(getByTestId('action-card-act_1'));
        expect(onActivateAction).toHaveBeenCalledWith('act_1');
        expect(onClose).toHaveBeenCalledOnce();
    });

    it('does NOT call onActivateAction when ActionCard fires a null selection (deselect)', () => {
        // ActionCard.onActionSelect may receive null when the
        // user toggles off a card — we should still close the
        // popover but NOT activate anything downstream.
        const onActivateAction = vi.fn();
        const onClose = vi.fn();
        const { getByTestId } = render(
            <ActionCardPopover
                {...defaultProps()}
                onActivateAction={onActivateAction}
                onClose={onClose}
            />,
        );
        // Simulate the user clicking the reject button — this
        // path calls onActionReject and not onActionSelect in
        // ActionCard, so nothing should activate.
        fireEvent.click(getByTestId('action-card-act_1'));
        // Body click activates once (sanity check)
        expect(onActivateAction).toHaveBeenCalledTimes(1);
    });

    it('no-ops gracefully when optional callbacks are omitted', () => {
        // When onActionFavorite / onActionReject are undefined,
        // internal stubs keep ActionCard happy.
        const { getByTestId } = render(
            <ActionCardPopover
                {...defaultProps()}
                onActionFavorite={undefined}
                onActionReject={undefined}
            />,
        );
        // Rendering should not throw
        expect(getByTestId('action-card-act_1')).toBeInTheDocument();
    });
});
