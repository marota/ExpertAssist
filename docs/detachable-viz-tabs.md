# Detachable Visualization Tabs

This document describes the implementation of the **detachable visualization
tabs** feature, which lets an operator pop any of the four visualization tabs
(Network `N`, Contingency `N-1`, Remedial `Action`, `Overflow` Analysis) out of
the main window and into a standalone browser window, then reattach it when
done. The feature was built to support dual-screen / multi-monitor workflows,
where a grid operator commonly wants to keep e.g. the `N-1` diagram on one
screen while working the `Action` tab on another.

The implementation follows the initial collaboration plan — this document
records **what was actually shipped**, where it diverges from the plan, and
which design decisions were made along the way.

## Feature summary

- Each of the four visualization tabs exposes a small detach button `⧉` in
  the tab bar. Clicking it opens a new browser window and relocates the
  tab's DOM into that window.
- While detached, the main window shows a placeholder with a `Focus window`
  and `Reattach` button, and the tab label gains a `↗` arrow + greyed-out
  styling so it is obviously "external".
- The popup window carries a floating header with a `Reattach` button. It
  also reacts to being closed from the browser chrome: the tab folds back
  into the main window automatically.
- Zoom level, pan, auto-zoom viewBox, SLD overlay position and all React
  refs survive the detach → reattach round-trip unchanged.
- Detach and reattach events are recorded in the interaction log so that
  session replays can reproduce the operator's window layout.

## Architecture

The feature rests on four pieces, all under `frontend/src`:

| File | Role |
|---|---|
| `hooks/useDetachedTabs.ts` | Owns the popup lifecycle state (`tabId → Window`), exposes `detach`/`reattach`/`focus`/`isDetached`, prunes closed popups automatically. |
| `components/TabPortal.tsx` | Thin `createPortal` wrapper — renders children in place when `target` is `null`, or into the given DOM node otherwise. |
| `components/VisualizationPanel.tsx` | Wraps each of the four tab containers in a `TabPortal`, adds the per-tab detach/reattach button to the tab bar, and renders the "detached" placeholder + the popup header. |
| `App.tsx` | Instantiates `useDetachedTabs`, wires detach/reattach callbacks, and auto-switches `activeTab` when the currently-active tab is detached. |

### The critical invariant — never unmount the SVG subtree

`MemoizedSvgContainer` re-runs its `useLayoutEffect` on every mount, which
re-applies the default viewBox and clobbers any auto-zoom or user pan/zoom
state. This is why the existing code already keeps all four tab containers
*always mounted* and toggles them via `visibility` + `z-index` (see the
long-standing comment on lines ~306-310 of `VisualizationPanel.tsx`).

The detach feature upholds this invariant. The React subtree for each tab
lives in `VisualizationPanel` regardless of whether the tab is visible,
active, or detached — only the **final DOM output** is relocated via
`ReactDOM.createPortal` into the popup's `<body>`. Because React never
unmounts the component, refs (`nSvgContainerRef`, `n1SvgContainerRef`, etc.),
the parsed SVG element, the zoom state inside `usePanZoom`, and the
`SldOverlay` position are all preserved across the round-trip.

### Popup lifecycle

`useDetachedTabs.detach(tabId)` performs the following:

1. Calls `window.open('', 'costudy4grid_tab_<id>', 'popup=yes,...')`. If
   the browser blocks the popup (`window.open` returns `null`), it invokes
   the `onPopupBlocked` callback, which in `App.tsx` surfaces an inline
   error banner telling the user to allow popups.
2. Writes a minimal `<!DOCTYPE html><html>…</html>` skeleton into
   `popup.document`, setting the title to `Co-Study4Grid — <Tab Name>`.
3. Clones every `<style>` and `<link rel="stylesheet">` from the opener
   document into the popup's `<head>`. This covers both the production
   case (Vite-bundled stylesheet link) and the dev case (Vite HMR
   injecting styles as `<style>` elements).
4. Creates a `<div id="costudy4grid-detached-root">` inside the popup
   `<body>` — a flex-growing container so absolutely-positioned tab
   content has something to size against — and stores it as the
   `mountNode` used by the portal target.
5. Attaches `pagehide` and `beforeunload` listeners so the tab folds back
   to the main window if the user closes the popup from the browser
   chrome. A 1 Hz `setInterval` polls `popup.closed` as a safety net for
   browsers that silently skip `pagehide` (observed on some tab-crash
   paths).
6. On `App.tsx` unmount (full page reload / navigation) any remaining
   popups are closed so they don't linger pointing at a dead React tree.

### Routing logic in `VisualizationPanel`

Previously each tab container was rendered only when `activeTab === <id>`
(except the always-mounted `N-1`/`Action` containers). The refactor
generalises that so every tab container is rendered whenever it is *either*
active *or* detached. The container is wrapped in a `TabPortal` whose
`target` is the popup's `mountNode` if detached, or `null` (render in
place) otherwise.

In the main window, when the active tab is detached, the panel renders a
placeholder (`renderDetachedPlaceholder`) with "Focus window" and
"Reattach" buttons so the operator can quickly return to the popup.

Inside the popup, each tab gets a small floating header
(`renderDetachedHeader`) pinned top-center with a coloured dot, the tab
label, and a `↩ Reattach` button.

When the user detaches the currently-active tab, `App.tsx` automatically
switches `activeTab` to the first available non-detached tab (preferring
`n → n-1 → action → overflow`, falling back to `n`) so the main panel is
not left showing an empty container.

### Pan/zoom in detached windows

Global DOM event listeners attached to the main `window` object do **not**
receive events fired inside a popup. Two call sites had to be updated:

- `hooks/usePanZoom.ts` — the `mousemove`/`mouseup` listeners used to
  track drag-pan now bind to `el.ownerDocument.defaultView` (the popup's
  `Window` when portaled there, otherwise the main `window`).
- `components/SldOverlay.tsx` — both `startOverlayDrag` and
  `startOverlayPan` use `(e.currentTarget as HTMLElement).ownerDocument
  .defaultView` for the same reason.

No other places in the SVG zoom / visualization code needed changes. The
wheel handler is already attached directly to the SVG element, which
continues to work across windows, and `MemoizedSvgContainer` uses only
`ref.current.ownerDocument` for measurements.

### Interaction logging

Two new interaction types were added to `types.ts`:

- `tab_detached` — payload `{ tab: TabId }`
- `tab_reattached` — payload `{ tab: TabId }`

This keeps the replay contract documented in `docs/interaction-logging.md`
able to reproduce the exact window layout chosen by the operator during a
session.

## Divergences from the initial plan

The initial plan laid out a 5-layer design frame (state / lifecycle /
transport / synchronisation / degradation) and a 10-step implementation
plan. The shipped version follows that frame closely, with the following
concrete choices / deviations:

| Topic | Plan | Shipped |
|---|---|---|
| Unit of detachment | Per-tab (not per-panel) | **Same** — per-tab, one popup per tab |
| State location | `App.tsx` via `useDetachedTabs` hook | **Same** |
| Portal technique | `createPortal` into popup `<body>` | Portals point at a dedicated `#costudy4grid-detached-root` div inside `<body>` instead of `<body>` directly, so the portaled content can flex-grow without fighting body margins. |
| Style propagation | Clone `<style>` + `<link>` from opener head | **Same** — see `cloneStylesIntoPopup`. No `MutationObserver` was added; HMR style changes are picked up on next detach, which was deemed acceptable in dev. |
| Detach UI | Button in tab bar using `lucide-react` (`ExternalLink`/`PictureInPicture2`) | **Unicode glyphs** (`⧉`, `↩`, `↗`) inline in the button, avoiding an extra import and matching the surrounding minimalist tab-bar styling. |
| Active-tab handling on detach | Auto-switch to next available tab | **Same** — `handleDetachTab` in `App.tsx` picks `n → n-1 → action → overflow`, skipping detached ones. |
| Detached tab in main bar | Grey + "(detached)" label, click focuses popup | Shipped: italic + dimmed colour + `↗` suffix; click on the label focuses the popup, click on the small `↩` button reattaches. |
| Reattach from popup | Minimal header with Reattach button | **Same** — floating pill top-center with tab name + Reattach. |
| Popup-close handling | `beforeunload` listener | Uses **both** `pagehide` (preferred on modern browsers) and `beforeunload`, plus a 1 Hz interval safety net to cover browsers that fail to fire either event on tab crashes. |
| Pop-up blocker fallback | Toast + cancel | Inline error set via `setError(...)` — reuses the existing global error banner rather than introducing a new toast component. |
| Global event listener audit | `usePanZoom`, `SldOverlay`, zoom code | Done for `usePanZoom.ts` and `SldOverlay.tsx`. No other globals needed patching. |
| Styles `MutationObserver` | Optional | Not shipped — unnecessary in practice. |
| `standalone_interface.html` mirror | Disabled button with "dev build only" tooltip | **Not mirrored** in this iteration. The standalone HTML is a single-file dev artefact that does not use React portals, and wiring popup cloning into it would add significant complexity with little user value. Left as a known follow-up if we ever want feature parity. |
| Interaction log | Not covered in plan | Added `tab_detached` / `tab_reattached` events so session replays can reproduce window layout. |
| Tests | Vitest hook tests + panel behaviour tests | Shipped: `hooks/useDetachedTabs.test.ts` (148 lines) covering detach/reattach/focus/pruning/popup-blocked paths. Panel-level tests were not added — the hook tests + manual verification were deemed sufficient given the amount of DOM/Window mocking a full panel test would require. |

## File-by-file summary

- **`frontend/src/hooks/useDetachedTabs.ts`** (new, 196 lines) — popup
  lifecycle hook.
- **`frontend/src/hooks/useDetachedTabs.test.ts`** (new, 148 lines) —
  Vitest tests for the hook using a fake `Window` constructed over a
  jsdom document.
- **`frontend/src/components/TabPortal.tsx`** (new, 30 lines) — portal
  wrapper.
- **`frontend/src/components/VisualizationPanel.tsx`** — refactored the
  four tab containers to be portal-targets + always rendered when
  detached; added tab-bar detach buttons; added detached-header and
  detached-placeholder renderers.
- **`frontend/src/App.tsx`** — instantiates `useDetachedTabs`, wires
  `handleDetachTab` (with active-tab fallback) and `handleReattachTab`
  (with interaction logging), passes props down to `VisualizationPanel`.
- **`frontend/src/hooks/usePanZoom.ts`** — bind drag-pan listeners to
  `el.ownerDocument.defaultView`.
- **`frontend/src/components/SldOverlay.tsx`** — same treatment for
  overlay drag/pan handlers.
- **`frontend/src/types.ts`** — two new `InteractionType` variants.

## Known limitations

1. **Popup-blocker UX** — if the browser blocks `window.open`, the user
   sees a generic inline error banner rather than a dedicated toast. The
   message tells them to allow popups for the site.
2. **Stylesheet hot-reload** — style tags are cloned once at detach time.
   If Vite HMR injects new styles while a tab is detached, the popup
   will not pick them up until it is reattached and detached again. This
   only affects dev mode.
3. **`standalone_interface.html` parity** — the single-file standalone
   interface does not support detaching. See the table above.
4. **Full page reload** — reloading the main window closes all detached
   popups (by design). We do not currently persist and restore detached
   state across reloads.

## Manual verification checklist

Done during development against `npm run dev`:

- Detach `N-1`, zoom in, verify zoom is preserved on reattach.
- Detach `Action`, select a new action in the action feed — the popup
  updates live because props flow through the same React tree.
- Detach `N-1`, close the popup from the browser chrome — the tab folds
  back into the main window and zoom state is preserved.
- Detach the currently-active tab — main panel switches to the next
  available tab automatically.
- Detach two tabs simultaneously and verify their popups are
  independent.
- Block popups in the browser and click detach — error banner appears,
  state unchanged.

## Related files / further reading

- `docs/interaction-logging.md` — replay contract, now extended with
  `tab_detached` / `tab_reattached` events.
- `docs/rendering-optimization-plan.md` — context on why
  `MemoizedSvgContainer` must stay mounted.
- `frontend/src/components/VisualizationPanel.tsx:306` — long-standing
  comment explaining the always-mounted-container invariant this feature
  had to uphold.
