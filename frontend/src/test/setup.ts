import '@testing-library/jest-dom/vitest';

// @ts-expect-error: IS_REACT_ACT_ENVIRONMENT is not in the global type definitions
global.IS_REACT_ACT_ENVIRONMENT = true;

// Mock SVG getScreenCTM and related methods which are not implemented in JSDOM
if (typeof window !== 'undefined') {
    const mockMatrix = {
        a: 1, b: 0, c: 0, d: 1, e: 0, f: 0,
        multiply: () => mockMatrix,
        inverse: () => mockMatrix,
    };

    // @ts-expect-error: mocking internal SVG methods
    window.SVGElement.prototype.getScreenCTM = function() {
        return mockMatrix;
    };

    // @ts-expect-error: mocking internal SVG methods
    window.SVGSVGElement.prototype.createSVGMatrix = function() {
        return mockMatrix;
    };
    
    // @ts-expect-error: mocking internal SVG methods
    window.SVGSVGElement.prototype.getScreenCTM = function() {
        return mockMatrix;
    };
}
