# Code Quality & Maintainability Analysis

**Date:** 2026-04-11
**Scope:** Full repository diagnostic — backend, frontend, repo structure, security, testing

---

## Executive Summary

| Dimension | Grade | Notes |
|-----------|-------|-------|
| **TypeScript correctness** | **A** | Zero compiler errors, zero lint warnings, strict mode |
| **Test suite** | **A-** | 435 tests, all passing, 28 test files |
| **Documentation** | **A** | Excellent CLAUDE.md, 16 docs/, proper README |
| **Frontend architecture** | **B-** | Good hooks, but oversized components |
| **Backend architecture** | **C** | One 3,151-line monolith with a 583-line function |
| **Security posture** | **C-** | Path traversal risks, wildcard CORS, no input bounds |
| **Type safety (Python)** | **C-** | 98 functions missing type hints |
| **Error handling (Python)** | **D+** | 80+ silent exception handlers, debug prints over logging |

---

## 1. What's Working Well

### Frontend Tooling

- `tsc --noEmit` passes with **zero errors** under `strict: true`
- ESLint passes with **zero warnings**
- All **435 unit tests pass** across 28 test files (Vitest + React Testing Library)
- No `any` types in source code, no `@ts-ignore`
- Well-structured custom hooks: `useSettings`, `useAnalysis`, `useDiagrams`, `useSession`, `usePanZoom`

### Documentation

- CLAUDE.md (250+ lines) provides comprehensive project context
- 16 architecture/design docs in `docs/`
- Consistent copyright headers (MPL-2.0)

### Git Hygiene

- Conventional commit prefixes (`feat:`, `fix:`, `debug:`, `test:`)
- PR-based workflow with descriptive merge commits
- Dual CI: CircleCI + GitHub Actions running pytest, Vitest, and ESLint

### Backend Test Coverage

- 37 test files in `expert_backend/tests/`
- Covers sanitization, overload filtering, combined actions, regression scenarios

---

## 2. Critical Issues

### 2.1 Security: Path Traversal Vulnerabilities

`expert_backend/main.py:334` — Session save accepts user-controlled paths with no sanitization:

```python
session_dir = os.path.join(request.output_folder_path, request.session_name)
```

A malicious `session_name = "../../etc"` would write outside the intended directory. Same issue at:
- `main.py:398` (load session)
- `main.py:351` (`shutil.copy2` with user-supplied `pdf_path`)

**Recommendation:** Use `pathlib.Path.resolve()` and verify the resolved path is within the allowed directory before any file operation.

### 2.2 Security: Wildcard CORS

`expert_backend/main.py:80` — `allow_origins=["*"]` with `allow_credentials=True`. This combination is a known anti-pattern that browsers may reject, and any origin can make authenticated requests.

**Recommendation:** Configure CORS origins via environment variable; restrict to known frontend origins.

### 2.3 Backend God Object: `recommender_service.py` (3,151 lines)

This single file contains the entire analysis engine. Key offenders:

| Function | Lines | Location |
|----------|-------|----------|
| `simulate_manual_action()` | **583** | lines 2284–2866 |
| `compute_superposition()` | **282** | lines 2868–3149 |
| `run_analysis()` | **157** | lines 1089–1245 |
| `update_config()` | **126** | lines 827–952 |

`simulate_manual_action()` alone handles: parameter normalization, dynamic action creation (3 prefixes), observation caching, simulation execution, result formatting, and topology building — 6+ distinct responsibilities in one function.

**Recommendation:** Split into focused modules (simulation, diagrams, config, enrichment) with single-responsibility functions.

### 2.4 Silent Exception Swallowing

`recommender_service.py` contains **80+ `except Exception` blocks**, many with `pass` or only a `print()`. Examples at lines 280, 348, 386, 441, 1701, 1819, 2412, 2658. Failures in voltage-level lookups, diagram generation, and environment setup are silently ignored, making debugging extremely difficult.

**Recommendation:** Replace with `logging.warning()`/`logging.error()` calls; only suppress exceptions where failure is truly expected and harmless.

### 2.5 Debug Prints Instead of Logging

The backend uses **80+ bare `print()` calls** for debugging output rather than Python's `logging` module. No log levels, no structured output, no ability to filter or route messages.

**Recommendation:** Adopt Python's `logging` module with structured log levels throughout the backend.

---

## 3. High-Priority Issues

### 3.1 Frontend: Oversized Components

| File | Lines | Issue |
|------|-------|-------|
| `ActionFeed.tsx` | **1,406** | 15+ useState hooks, 43-prop interface, mixed filtering/rendering |
| `VisualizationPanel.tsx` | **1,285** | Embeds `SldOverlay` + `MemoizedSvgContainer` inline |
| `CombinedActionsModal.tsx` | **777** | Could be split into subcomponents |
| `App.tsx` | **758** | Orchestration hub — acceptable but at the boundary |
| `useDiagrams.ts` | **767** | Large hook with many handlers |

`ActionFeed.tsx` is the worst offender — it receives **43 props**, manages 15+ pieces of local state, and contains filtering, simulation, and rendering logic all inline.

**Recommendation:** Extract into `ActionCard`, `ActionSearch`, `ActionFilters` subcomponents. Consider Context API for metadata distribution to reduce prop drilling.

### 3.2 Missing React Error Boundary

No `ErrorBoundary` component exists. An unhandled exception in any component will crash the entire application with a white screen.

**Recommendation:** Add an Error Boundary wrapping the app root with a fallback UI.

### 3.3 Python Type Hint Coverage

**98 functions** lack complete type annotations. Every route handler in `main.py` is missing return type annotations (30 functions). The `sanitize_for_json()` utility at `recommender_service.py:30` — called 30+ times — has no parameter or return types.

**Recommendation:** Add return type annotations to all FastAPI route handlers (also enables better auto-generated OpenAPI docs).

### 3.4 Weak TypeScript Typing Patterns

65 occurrences of `Record<string, unknown>` and `as unknown as` double-casts across the frontend, indicating the API response types aren't fully modeled:

- `ActionFeed.tsx`: 7 occurrences
- `api.ts`, `useDiagrams.ts`, `useSession.ts`: scattered throughout

These bypass TypeScript's type checking at integration boundaries.

**Recommendation:** Define typed API response interfaces in `types.ts` to replace `Record<string, unknown>` casts.

### 3.5 Accessibility Gaps

- No `aria-label` on icon/emoji buttons (ActionFeed, Header, OverloadPanel)
- No `aria-selected`/`aria-controls` on tab buttons (SettingsModal)
- No focus trapping in modals
- No semantic list markup (`<ul>`/`<li>`) for action lists
- No screen reader announcements for async operations

**Recommendation:** Audit against WCAG 2.1 AA; add aria attributes, semantic HTML, and focus management to modals.

---

## 4. Medium-Priority Issues

### 4.1 Standalone HTML Maintenance Burden

`standalone_interface.html` is **7,178 lines** — a complete duplicate of the React frontend in a single file. Every UI change must be manually mirrored. This is a significant ongoing maintenance cost and drift risk.

**Recommendation:** Consider deprecating or auto-generating from the React build.

### 4.2 Inconsistent API Response Formats

- Some endpoints: `{"status": "success", ...}`
- Others: direct data `{"branches": [...]}`
- Streaming endpoints: custom NDJSON error format
- Error responses: `HTTPException(detail=str(e))` leaks internal stack details

**Recommendation:** Standardize on a response envelope format and error schema across all endpoints.

### 4.3 Hardcoded Configuration

| Value | Location | Should Be |
|-------|----------|-----------|
| Port 8000, host 0.0.0.0 | `main.py:691` | Environment variable |
| `"Overflow_Graph"` directory | 5 locations in main.py | Config constant |
| CORS origins `["*"]` | `main.py:80` | Environment variable |
| Worsening thresholds | `recommender_service.py:486,1134` | Config parameter |

**Recommendation:** Parameterize via environment variables or a central config object.

### 4.4 Unused Dependencies

- `framer-motion` — installed in `package.json` but not imported in any source file
- `lucide-react` — installed but emoji characters used instead of icon components
- `GZipMiddleware` — imported but commented out at `main.py:85`

**Recommendation:** Remove unused packages to reduce bundle size and maintenance surface.

### 4.5 Incomplete Function

`network_service.py:171–180` — `get_load_voltage_levels_bulk()` initializes a `result = {}` dict and then returns without any loop body. The function is incomplete.

**Recommendation:** Either implement the function body or remove it.

### 4.6 Code Duplication in Backend

- Voltage-level resolution logic repeated 4 times across `network_service.py`
- Action detail computation (`_compute_load_shedding_details`, `_compute_curtailment_details`, `_compute_pst_details`) share near-identical structure
- Try/except blocks for element voltage-level access repeated 5+ times in `recommender_service.py`

**Recommendation:** Extract shared patterns into helper functions.

### 4.7 Frontend: Swallowed Errors in Async Code

- `SettingsModal.tsx:125,130` — `.catch(() => { })` swallows errors silently
- `useSettings.ts:174,220` — `.catch()` with empty handler
- `useAnalysis.ts:142` — Non-null assertion `lines.pop()!` without validation

**Recommendation:** At minimum, log caught errors to console; add null-checks before assertions.

---

## 5. Low-Priority / Housekeeping

| Item | Details |
|------|---------|
| Empty doc file | `docs/network_rendering_profiling_recommendations.md` (0 bytes) |
| Stale lockfile | `.~lock.Cases_Defauts_10032026.odt#` tracked in repo root |
| Redundant CI | Both CircleCI and GitHub Actions do the same work — consolidate |
| No `.env.example` | No template for environment variables |
| No Dockerfile | No containerization for reproducible deployment |
| CLAUDE.md drift | References root-level `test_*.py` scripts that no longer exist |
| Missing `.editorconfig` | No cross-editor formatting consistency |
| Missing `CONTRIBUTING.md` | No contribution guidelines for new developers |

---

## 6. Metrics Summary

```
Backend (expert_backend/)
  Source files (non-test):  4
  Total lines:              4,064
  Largest file:             recommender_service.py (3,151 lines)
  Longest function:         simulate_manual_action() (583 lines)
  Functions without types:  98
  Silent exceptions:        80+
  Debug prints:             80+
  Test files:               37

Frontend (frontend/src/)
  Source files (non-test):  21
  Total lines:              ~10,200
  Test files:               28
  Tests passing:            435/435
  TypeScript errors:        0
  Lint warnings:            0
  `any` types in source:    0
  Weak casts:               65 occurrences

Repository
  Standalone HTML:          7,178 lines
  Documentation files:      16 in docs/
  CI pipelines:             2 (CircleCI + GitHub Actions)
```

---

## 7. Prioritized Recommendations

### Immediate (High Risk)

1. **Fix path traversal** in session save/load endpoints — validate resolved paths are within allowed directories
2. **Refactor `recommender_service.py`** — extract `simulate_manual_action()` into focused functions; split the 3,151-line file into modules
3. **Replace silent exceptions** with `logging.warning()`/`logging.error()` — adopt Python `logging` throughout
4. **Add a React Error Boundary** wrapping the app root

### Short-Term (High Value)

5. **Split `ActionFeed.tsx`** into subcomponents (ActionCard, ActionSearch, ActionFilters)
6. **Add return type annotations** to all FastAPI route handlers
7. **Define typed API response interfaces** in `types.ts` to eliminate `Record<string, unknown>` casts
8. **Remove unused deps** (`framer-motion`, `lucide-react`) and dead imports (`GZipMiddleware`)

### Medium-Term (Improvement)

9. **Parameterize hardcoded values** (port, CORS origins, output directory) via environment variables
10. **Standardize API response formats** across all endpoints
11. **Add accessibility attributes** (aria-labels, semantic HTML, focus trapping)
12. **Consolidate CI** to a single pipeline (CircleCI or GitHub Actions)

### Long-Term (Strategic)

13. **Deprecate or auto-generate `standalone_interface.html`** from the React build
14. **Add Python dependency lockfile** (Poetry or uv) for reproducible builds
15. **Add accessibility testing** (jest-axe or similar)
