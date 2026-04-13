// Copyright (c) 2025-2026, RTE (https://www.rte-france.com)
// This Source Code Form is subject to the terms of the Mozilla Public License, version 2.0.
// If a copy of the Mozilla Public License, version 2.0 was not distributed with this file,
// you can obtain one at http://mozilla.org/MPL/2.0/.
// SPDX-License-Identifier: MPL-2.0
// This file is part of Co-Study4Grid a Power Grid Study tool Assistant Interface to help solve contigencies for a grid state under study.

import React from 'react';
import { createPortal } from 'react-dom';

/**
 * Renders children either in-place (when `target` is null) or into the
 * given DOM node (typically the body of a secondary browser window).
 *
 * Using a portal is critical for preserving zoom/viewBox state across
 * detach and reattach: the React sub-tree is never unmounted, so
 * `MemoizedSvgContainer`'s useLayoutEffect does not re-run and the
 * already-parsed SVG element stays intact.
 */
interface TabPortalProps {
    target: HTMLElement | null;
    children: React.ReactNode;
}

const TabPortal: React.FC<TabPortalProps> = ({ target, children }) => {
    if (!target) return <>{children}</>;
    return createPortal(children, target);
};

export default TabPortal;
