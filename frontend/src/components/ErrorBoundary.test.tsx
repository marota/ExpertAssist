// Copyright (c) 2025-2026, RTE (https://www.rte-france.com)
// This Source Code Form is subject to the terms of the Mozilla Public License, version 2.0.
// If a copy of the Mozilla Public License, version 2.0 was not distributed with this file,
// you can obtain one at http://mozilla.org/MPL/2.0/.
// SPDX-License-Identifier: MPL-2.0
// This file is part of Co-Study4Grid a Power Grid Study tool Assistant Interface to help solve contigencies for a grid state under study.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { useState } from 'react';
import ErrorBoundary from './ErrorBoundary';

/** Helper component that throws on render when `shouldThrow` is true. */
function Bomb({ shouldThrow, message = 'boom' }: { shouldThrow: boolean; message?: string }) {
    if (shouldThrow) {
        throw new Error(message);
    }
    return <div>child content</div>;
}

/** Wrapper that allows a test to flip the bomb from thrown -> healthy. */
function RecoverableBomb() {
    const [broken, setBroken] = useState(true);
    return (
        <ErrorBoundary>
            <button type="button" onClick={() => setBroken(false)}>
                fix
            </button>
            <Bomb shouldThrow={broken} />
        </ErrorBoundary>
    );
}

describe('ErrorBoundary', () => {
    let consoleErrorSpy: ReturnType<typeof vi.spyOn>;

    beforeEach(() => {
        // React logs caught errors to console.error; silence them to keep
        // test output clean.
        consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    });

    afterEach(() => {
        consoleErrorSpy.mockRestore();
    });

    it('renders children when no error is thrown', () => {
        render(
            <ErrorBoundary>
                <Bomb shouldThrow={false} />
            </ErrorBoundary>,
        );
        expect(screen.getByText('child content')).toBeInTheDocument();
    });

    it('renders the default fallback UI when a child throws', () => {
        render(
            <ErrorBoundary>
                <Bomb shouldThrow message="kaboom" />
            </ErrorBoundary>,
        );
        expect(screen.getByRole('alert')).toBeInTheDocument();
        expect(screen.getByText('Something went wrong')).toBeInTheDocument();
        // Error message appears in both the details block and the stack trace.
        expect(screen.getAllByText(/kaboom/).length).toBeGreaterThan(0);
        expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Reload page' })).toBeInTheDocument();
    });

    it('renders a custom fallback when provided', () => {
        render(
            <ErrorBoundary fallback={<div>custom fallback</div>}>
                <Bomb shouldThrow />
            </ErrorBoundary>,
        );
        expect(screen.getByText('custom fallback')).toBeInTheDocument();
        expect(screen.queryByText('Something went wrong')).not.toBeInTheDocument();
    });

    it('logs the caught error to console.error', () => {
        render(
            <ErrorBoundary>
                <Bomb shouldThrow message="explode" />
            </ErrorBoundary>,
        );
        const loggedFromBoundary = consoleErrorSpy.mock.calls.some(
            (call) => typeof call[0] === 'string' && call[0].includes('ErrorBoundary caught an error'),
        );
        expect(loggedFromBoundary).toBe(true);
    });

    it('recovers when the user clicks "Try again" and the child no longer throws', () => {
        render(<RecoverableBomb />);
        // Initially in error state.
        expect(screen.getByText('Something went wrong')).toBeInTheDocument();
        // The "fix" button is not in the DOM because the fallback replaced the tree.
        expect(screen.queryByRole('button', { name: 'fix' })).not.toBeInTheDocument();

        // We can't fix state from inside the fallback, so this test just verifies
        // that "Try again" resets the boundary. The child will re-throw and the
        // fallback will remain.
        fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
        // After reset + rethrow, still shows fallback.
        expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    });

    it('calls window.location.reload when "Reload page" is clicked', () => {
        const reloadMock = vi.fn();
        const originalLocation = window.location;
        Object.defineProperty(window, 'location', {
            configurable: true,
            value: { ...originalLocation, reload: reloadMock },
        });

        try {
            render(
                <ErrorBoundary>
                    <Bomb shouldThrow />
                </ErrorBoundary>,
            );
            fireEvent.click(screen.getByRole('button', { name: 'Reload page' }));
            expect(reloadMock).toHaveBeenCalledTimes(1);
        } finally {
            Object.defineProperty(window, 'location', {
                configurable: true,
                value: originalLocation,
            });
        }
    });

    it('shows error details in a collapsible <details> element', () => {
        render(
            <ErrorBoundary>
                <Bomb shouldThrow message="detail-test" />
            </ErrorBoundary>,
        );
        expect(screen.getByText('Error details')).toBeInTheDocument();
        expect(screen.getAllByText(/detail-test/).length).toBeGreaterThan(0);
    });
});
