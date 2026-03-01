import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import OverloadPanel from './OverloadPanel';

describe('OverloadPanel', () => {
    const defaultProps = {
        nOverloads: [] as string[],
        n1Overloads: [] as string[],
        onAssetClick: vi.fn(),
    };

    it('renders the Overloads heading', () => {
        render(<OverloadPanel {...defaultProps} />);
        expect(screen.getByText('Overloads')).toBeInTheDocument();
    });

    it('shows "None" when no overloads', () => {
        render(<OverloadPanel {...defaultProps} />);
        const noneElements = screen.getAllByText('None');
        expect(noneElements).toHaveLength(2);
    });

    it('renders N overload links', () => {
        render(
            <OverloadPanel
                {...defaultProps}
                nOverloads={['LINE_A', 'LINE_B']}
            />
        );
        expect(screen.getByText('LINE_A')).toBeInTheDocument();
        expect(screen.getByText('LINE_B')).toBeInTheDocument();
    });

    it('renders N-1 overload links', () => {
        render(
            <OverloadPanel
                {...defaultProps}
                n1Overloads={['TRAFO_1']}
            />
        );
        expect(screen.getByText('TRAFO_1')).toBeInTheDocument();
    });

    it('calls onAssetClick with correct tab for N overloads', async () => {
        const user = userEvent.setup();
        const onAssetClick = vi.fn();
        render(
            <OverloadPanel
                {...defaultProps}
                nOverloads={['LINE_A']}
                onAssetClick={onAssetClick}
            />
        );

        await user.click(screen.getByText('LINE_A'));
        expect(onAssetClick).toHaveBeenCalledWith('', 'LINE_A', 'n');
    });

    it('calls onAssetClick with correct tab for N-1 overloads', async () => {
        const user = userEvent.setup();
        const onAssetClick = vi.fn();
        render(
            <OverloadPanel
                {...defaultProps}
                n1Overloads={['LINE_B']}
                onAssetClick={onAssetClick}
            />
        );

        await user.click(screen.getByText('LINE_B'));
        expect(onAssetClick).toHaveBeenCalledWith('', 'LINE_B', 'n-1');
    });

    it('renders both N and N-1 overloads simultaneously', () => {
        render(
            <OverloadPanel
                {...defaultProps}
                nOverloads={['LINE_A']}
                n1Overloads={['LINE_B', 'LINE_C']}
            />
        );
        expect(screen.getByText('LINE_A')).toBeInTheDocument();
        expect(screen.getByText('LINE_B')).toBeInTheDocument();
        expect(screen.getByText('LINE_C')).toBeInTheDocument();
    });

    it('renders section labels', () => {
        render(<OverloadPanel {...defaultProps} />);
        expect(screen.getByText('N Overloads:')).toBeInTheDocument();
        expect(screen.getByText('N-1 Overloads:')).toBeInTheDocument();
    });
});
