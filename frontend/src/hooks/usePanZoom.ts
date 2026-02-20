import { useState, useEffect, useLayoutEffect, useRef, type RefObject } from 'react';
import type { ViewBox } from '../types';

/**
 * Custom Hook for SVG Pan/Zoom via viewBox manipulation.
 * Performance: viewBox updates go directly to the DOM via refs,
 * bypassing React's render cycle during active interaction.
 * React state is only synced on interaction end / pause.
 */
export const usePanZoom = (
    svgRef: RefObject<HTMLDivElement | null>,
    initialViewBox: ViewBox | null | undefined,
    active: boolean,
) => {
    // React state: "settled" viewBox for downstream consumers
    const [viewBox, setViewBox] = useState<ViewBox | null>(null);
    // Mutable ref for the hot path — updated every frame, no React render
    const viewBoxRef = useRef<ViewBox | null>(null);
    const isDragging = useRef(false);
    const startPoint = useRef({ x: 0, y: 0, pendingX: 0, pendingY: 0 });
    const wheelTimerId = useRef<ReturnType<typeof setTimeout> | null>(null);
    const rafId = useRef<number | null>(null);
    // Cached SVG element ref — avoids querySelector on every event
    const svgElRef = useRef<SVGSVGElement | null>(null);
    const activeRef = useRef(active);
    activeRef.current = active;
    // Original viewBox max dimension — used for relative text visibility threshold
    const initialMaxDimRef = useRef<number | null>(null);

    // Direct DOM update — no React involved
    const applyViewBox = (vb: ViewBox | null) => {
        const svg = svgElRef.current;
        if (svg && vb) {
            svg.setAttribute('viewBox', `${vb.x} ${vb.y} ${vb.w} ${vb.h}`);
        }
        // Toggle text visibility based on zoom level (large grids only).
        // Show text when zoomed in to < 50% of original viewBox (2x+ zoom).
        const container = svgRef.current;
        if (container && vb && svg && svg.hasAttribute('data-large-grid')) {
            const origMax = initialMaxDimRef.current;
            const shouldHide = !origMax || Math.max(vb.w, vb.h) / origMax >= 0.5;
            container.classList.toggle('text-hidden', shouldHide);
        }
    };

    // Flush ref -> React state for downstream consumers
    const commitViewBox = () => {
        if (viewBoxRef.current) {
            setViewBox({ ...viewBoxRef.current });
        }
    };

    // Cache SVG element when container content changes.
    // Also hide text immediately on large grids to prevent a flash
    // of unreadable text before the first applyViewBox call.
    useLayoutEffect(() => {
        if (svgRef.current) {
            svgElRef.current = svgRef.current.querySelector('svg');
            if (svgElRef.current && svgElRef.current.hasAttribute('data-large-grid')) {
                const vb = viewBoxRef.current;
                const origMax = initialMaxDimRef.current;
                if (!vb || !origMax || Math.max(vb.w, vb.h) / origMax >= 0.5) {
                    svgRef.current.classList.add('text-hidden');
                }
            }
        } else {
            svgElRef.current = null;
        }
    });

    // Sync from initialViewBox (diagram load or programmatic reset)
    useEffect(() => {
        if (initialViewBox) {
            viewBoxRef.current = initialViewBox;
            initialMaxDimRef.current = Math.max(initialViewBox.w, initialViewBox.h);
            applyViewBox(initialViewBox);
            setViewBox(initialViewBox);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [initialViewBox]);

    // Stable event registration — re-registers when active tab changes
    // OR when the diagram loads (initialViewBox changes).
    useEffect(() => {
        const el = svgRef.current;
        if (!el || !active) return;

        // Re-apply saved viewBox to the DOM when becoming active again
        if (viewBoxRef.current) {
            applyViewBox(viewBoxRef.current);
        }

        const handleWheel = (e: WheelEvent) => {
            if (!activeRef.current || !viewBoxRef.current) return;
            e.preventDefault();
            const vb = viewBoxRef.current;
            const scaleFactor = e.deltaY > 0 ? 1.1 : 0.9;

            const svg = svgElRef.current;
            if (!svg) return;

            const pt = svg.createSVGPoint();
            pt.x = e.clientX;
            pt.y = e.clientY;
            const ctm = svg.getScreenCTM();
            if (!ctm) return;
            const svgP = pt.matrixTransform(ctm.inverse());

            const newVb: ViewBox = {
                x: vb.x + (svgP.x - vb.x) * (1 - scaleFactor),
                y: vb.y + (svgP.y - vb.y) * (1 - scaleFactor),
                w: vb.w * scaleFactor,
                h: vb.h * scaleFactor,
            };

            viewBoxRef.current = newVb;
            applyViewBox(newVb);

            // Debounced commit: sync to React after scrolling stops
            if (wheelTimerId.current) clearTimeout(wheelTimerId.current);
            wheelTimerId.current = setTimeout(commitViewBox, 150);
        };

        const handleMouseDown = (e: MouseEvent) => {
            if (!activeRef.current || !viewBoxRef.current) return;
            isDragging.current = true;
            startPoint.current = { x: e.clientX, y: e.clientY, pendingX: e.clientX, pendingY: e.clientY };
        };

        // rAF-throttled drag: at most one DOM update per display frame
        const handleMouseMove = (e: MouseEvent) => {
            if (!activeRef.current || !viewBoxRef.current || !isDragging.current) return;
            e.preventDefault();

            startPoint.current.pendingX = e.clientX;
            startPoint.current.pendingY = e.clientY;

            if (rafId.current) return; // frame already queued

            rafId.current = requestAnimationFrame(() => {
                rafId.current = null;
                const sp = startPoint.current;
                const dx = sp.pendingX - sp.x;
                const dy = sp.pendingY - sp.y;
                sp.x = sp.pendingX;
                sp.y = sp.pendingY;

                const svg = svgElRef.current;
                if (!svg) return;
                const screenW = svg.getBoundingClientRect().width;
                const vb = viewBoxRef.current!;
                const scale = vb.w / screenW;

                const newVb: ViewBox = {
                    ...vb,
                    x: vb.x - dx * scale,
                    y: vb.y - dy * scale,
                };
                viewBoxRef.current = newVb;
                applyViewBox(newVb);
            });
        };

        const handleMouseUp = () => {
            isDragging.current = false;
            if (rafId.current) {
                cancelAnimationFrame(rafId.current);
                rafId.current = null;
            }
            commitViewBox(); // Sync to React state on drag end
        };

        el.addEventListener('wheel', handleWheel, { passive: false });
        el.addEventListener('mousedown', handleMouseDown);
        window.addEventListener('mousemove', handleMouseMove);
        window.addEventListener('mouseup', handleMouseUp);

        return () => {
            el.removeEventListener('wheel', handleWheel);
            el.removeEventListener('mousedown', handleMouseDown);
            window.removeEventListener('mousemove', handleMouseMove);
            window.removeEventListener('mouseup', handleMouseUp);
            if (wheelTimerId.current) clearTimeout(wheelTimerId.current);
            if (rafId.current) cancelAnimationFrame(rafId.current);
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [active, initialViewBox]);

    // Public API: updates ref + DOM + React state immediately
    const setViewBoxPublic = (vb: ViewBox) => {
        viewBoxRef.current = vb;
        applyViewBox(vb);
        setViewBox(vb);
    };

    return { viewBox, setViewBox: setViewBoxPublic };
};
