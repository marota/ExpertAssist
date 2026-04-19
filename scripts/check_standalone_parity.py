#!/usr/bin/env python3
# Copyright (c) 2025-2026, RTE (https://www.rte-france.com)
# SPDX-License-Identifier: MPL-2.0
"""Layer-1 static parity check: frontend/ vs standalone_interface.html.

Extracts canonical inventories from the React source (the source of
truth) and diffs them against the standalone HTML mirror. Emits a
CI-friendly report with file:line anchors on every failure.

Three inventories checked today:

1. ``InteractionType`` union (``frontend/src/types.ts``) — every event
   type the React app claims the standalone must support.
2. Backend API paths (``frontend/src/api.ts``) — every endpoint wired
   into the React HTTP client must also be wired into the standalone.
3. ``SettingsState`` interface (``frontend/src/hooks/useSettings.ts``)
   — every field the Settings modal exposes must be mirrored.

For each ``interactionLogger.record('TYPE', { key1, key2, ... })``
call site, we also collect the union of detail keys emitted per
event type in BOTH codebases and diff them — catches the
``voltage_range_changed { min_kv, max_kv }`` vs. spec
``{ min, max }`` class of regression.

Run::

    python scripts/check_standalone_parity.py            # human output
    python scripts/check_standalone_parity.py --json     # CI-friendly

Exits non-zero on any FAIL-level finding so the script can gate CI.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_SRC = REPO_ROOT / "frontend" / "src"
STANDALONE = REPO_ROOT / "standalone_interface.html"
TYPES_TS = FRONTEND_SRC / "types.ts"
API_TS = FRONTEND_SRC / "api.ts"
USE_SETTINGS_TS = FRONTEND_SRC / "hooks" / "useSettings.ts"


# ---------------------------------------------------------------------
# Extractors (React source → canonical sets)
# ---------------------------------------------------------------------

def extract_interaction_types(ts_path: Path) -> set[str]:
    """Parse the ``InteractionType`` union from types.ts.

    We only need the set of string literals between
    ``export type InteractionType =`` and the terminating ``;``.
    Comments, whitespace, and ``|`` separators are tolerated.
    """
    src = ts_path.read_text(encoding="utf-8")
    m = re.search(r"export type InteractionType\s*=\s*(.*?);", src, re.DOTALL)
    if not m:
        raise RuntimeError(f"InteractionType union not found in {ts_path}")
    body = m.group(1)
    # Drop line comments and block comments.
    body = re.sub(r"//[^\n]*", "", body)
    body = re.sub(r"/\*.*?\*/", "", body, flags=re.DOTALL)
    return set(re.findall(r"'([a-z0-9_]+)'", body))


def extract_api_paths(api_path: Path) -> set[str]:
    """Pull every ``/api/...`` path out of the axios client.

    Matches the template-literal form the repo uses throughout, e.g.
    ``${API_BASE_URL}/api/run-analysis-step1``.
    """
    src = api_path.read_text(encoding="utf-8")
    paths = set(re.findall(r"/api/[A-Za-z0-9_\-]+", src))
    return paths


def extract_settings_state_fields(hook_path: Path) -> set[str]:
    """Parse field names from the exported ``SettingsState`` interface.

    We only keep fields that have a paired ``set<Name>`` setter in the
    same interface — this is the useSettings convention and it filters
    out inline function-type signatures (e.g. ``buildConfigRequest:
    () => { network_path: string; ... }``) whose return-type body would
    otherwise leak snake-case identifiers into the extracted set.
    """
    src = hook_path.read_text(encoding="utf-8")
    m = re.search(r"export interface SettingsState\s*\{(.*?)^\}", src, re.DOTALL | re.MULTILINE)
    if not m:
        raise RuntimeError(f"SettingsState interface not found in {hook_path}")
    body = m.group(1)
    body = re.sub(r"//[^\n]*", "", body)
    body = re.sub(r"/\*.*?\*/", "", body, flags=re.DOTALL)
    # Pair-based extraction: a field ``foo: T;`` counts only if
    # ``setFoo: (v: T) => void;`` also appears in the body.
    setters = set(re.findall(r"\bset([A-Z][A-Za-z0-9_]*)\s*:\s*\(", body))
    setter_targets = {s[0].lower() + s[1:] for s in setters}
    fields: set[str] = set()
    for name in re.findall(r"^\s*([a-z][A-Za-z0-9_]*)\s*:\s*", body, re.MULTILINE):
        if name in setter_targets:
            fields.add(name)
    return fields


RECORD_CALL = re.compile(
    r"interactionLogger\.record\(\s*['\"]([a-z0-9_]+)['\"]\s*(?:,\s*(\{[^{}]*?\}|\w+))?",
    re.DOTALL,
)
RECORD_COMPLETION_CALL = re.compile(
    r"interactionLogger\.recordCompletion\(\s*['\"]([a-z0-9_]+)['\"]",
)
# Match only property-start positions inside an object literal so we
# capture keys (not value identifiers).  Both explicit and JS shorthand
# properties are supported:
#   { name: value, ... }   → name
#   { name, ... }          → name   (shorthand, followed by `,`)
#   { name }               → name   (shorthand, followed by `}`)
# The leading ``[{,]`` anchor forces "first token of a property".
DETAIL_KEY = re.compile(
    r"[{,]\s*"
    r"([a-zA-Z_][a-zA-Z0-9_]*)"
    r"\s*(?=[:,}]|$)"
)


def walk_record_calls(
    root: Path,
    patterns: Iterable[str],
    exclude: Iterable[str] = (),
) -> tuple[dict[str, set[str]], dict[str, list[tuple[str, int]]]]:
    """Collect ``{event_type: set(detail_keys)}`` + file:line anchors.

    For each ``interactionLogger.record('type', { a, b: 1, ... })``:
    - event_type → 'type'
    - detail_keys → {'a', 'b'} (keys of the object-literal argument
      when it is an object literal; if the argument is a bare
      identifier, the keys are skipped — the call still counts toward
      presence but not toward schema diffing).
    """
    keys_by_type: dict[str, set[str]] = defaultdict(set)
    sites_by_type: dict[str, list[tuple[str, int]]] = defaultdict(list)
    excluded = tuple(exclude)

    files: list[Path] = []
    for pattern in patterns:
        files.extend(root.rglob(pattern))
    for path in sorted(set(files)):
        rel = str(path.relative_to(REPO_ROOT))
        if any(ex in rel for ex in excluded):
            continue
        src = path.read_text(encoding="utf-8", errors="replace")
        # Use line-by-line search so we can cheaply attach line numbers.
        for m in RECORD_CALL.finditer(src):
            event_type = m.group(1)
            details_src = m.group(2) or ""
            line_no = src.count("\n", 0, m.start()) + 1
            sites_by_type[event_type].append((rel, line_no))
            if details_src.startswith("{"):
                # Pass the whole literal (outer braces included) so the
                # DETAIL_KEY anchor recognises the first property —
                # stripping the outer ``{`` would drop the leading key
                # of multi-property objects.
                for km in DETAIL_KEY.finditer(details_src):
                    keys_by_type[event_type].add(km.group(1))
    return keys_by_type, sites_by_type


def walk_record_completion_calls(
    root: Path,
    patterns: Iterable[str],
    exclude: Iterable[str] = (),
) -> set[str]:
    """Return the set of event types that appear in ``recordCompletion(...)``
    calls. The start side is already handled by :func:`walk_record_calls`.
    """
    seen: set[str] = set()
    excluded = tuple(exclude)
    for pattern in patterns:
        for path in root.rglob(pattern):
            rel = str(path.relative_to(REPO_ROOT))
            if any(ex in rel for ex in excluded):
                continue
            src = path.read_text(encoding="utf-8", errors="replace")
            for m in RECORD_COMPLETION_CALL.finditer(src):
                seen.add(m.group(1))
    return seen


# ---------------------------------------------------------------------
# Extractors (standalone HTML → standalone inventories)
# ---------------------------------------------------------------------

def walk_standalone_record_calls(
    html_path: Path,
) -> tuple[dict[str, set[str]], dict[str, list[tuple[str, int]]]]:
    """Same contract as :func:`walk_record_calls` but for the
    single-file standalone HTML. The standalone inlines React-like JSX
    + JS, so ``interactionLogger.record(...)`` literals look identical
    to the frontend ones. We re-use the same regex.
    """
    keys_by_type: dict[str, set[str]] = defaultdict(set)
    sites_by_type: dict[str, list[tuple[str, int]]] = defaultdict(list)
    src = html_path.read_text(encoding="utf-8", errors="replace")
    for m in RECORD_CALL.finditer(src):
        event_type = m.group(1)
        details_src = m.group(2) or ""
        line_no = src.count("\n", 0, m.start()) + 1
        sites_by_type[event_type].append((str(html_path.name), line_no))
        if details_src.startswith("{"):
            # Pass the whole literal, including outer braces. The
            # DETAIL_KEY anchor needs the leading ``{`` to recognise
            # the first property — stripping it would drop the first
            # key from multi-property objects.
            for km in DETAIL_KEY.finditer(details_src):
                keys_by_type[event_type].add(km.group(1))
    return keys_by_type, sites_by_type


def extract_standalone_api_paths(html_path: Path) -> set[str]:
    """Return ``/api/...`` paths referenced in the standalone HTML.

    The standalone uses both ``fetch`` and ``axios`` / string literals;
    grepping the literal path is enough.
    """
    src = html_path.read_text(encoding="utf-8", errors="replace")
    return set(re.findall(r"/api/[A-Za-z0-9_\-]+", src))


def extract_standalone_setting_fields(html_path: Path) -> set[str]:
    """Best-effort extraction of ``useState`` field identifiers in the
    standalone that plausibly correspond to Settings state.

    The standalone does not expose a ``SettingsState`` type, so we
    sniff for ``const [fieldName, setFieldName] = useState(...)`` and
    intersect with the canonical SettingsState field names. Fields
    the frontend exposes but that do not appear here are flagged as
    potentially missing.
    """
    src = html_path.read_text(encoding="utf-8", errors="replace")
    names = set(re.findall(r"const\s+\[\s*([A-Za-z][A-Za-z0-9_]*)\s*,\s*set", src))
    return names


# ---------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------

def fmt_sites(sites: list[tuple[str, int]], limit: int = 3) -> str:
    head = sites[:limit]
    rest = len(sites) - len(head)
    base = ", ".join(f"{p}:{ln}" for p, ln in head)
    return base + (f" (+{rest} more)" if rest > 0 else "")


def run_checks() -> dict:
    """Execute every check and return a structured dict of findings.

    Top-level keys::

        {
          "missing_event_types":   [...],
          "orphan_event_types":    [...],        # in HTML, not in union
          "missing_completion":    [...],        # in FE, not in HTML
          "detail_key_drift":      [{...}, ...], # per-event detail diff
          "missing_api_paths":     [...],
          "missing_settings":      [...],
        }
    """
    canonical_events = extract_interaction_types(TYPES_TS)
    canonical_api = extract_api_paths(API_TS)
    canonical_settings = extract_settings_state_fields(USE_SETTINGS_TS)

    # Exclude all test files so the inventories reflect production
    # call sites only — `*.test.ts` / `*.test.tsx` emit events with
    # placeholder shapes (`{ path: '/data' }`) that would pollute the
    # details-key diff.
    fe_keys, fe_sites = walk_record_calls(
        FRONTEND_SRC,
        ("*.ts", "*.tsx"),
        exclude=(".test.ts", ".test.tsx"),
    )
    fe_completion = walk_record_completion_calls(
        FRONTEND_SRC,
        ("*.ts", "*.tsx"),
        exclude=(".test.ts", ".test.tsx"),
    )

    sa_keys, sa_sites = walk_standalone_record_calls(STANDALONE)
    sa_completion = set()  # populated below if any recordCompletion calls present
    sa_src = STANDALONE.read_text(encoding="utf-8", errors="replace")
    for m in RECORD_COMPLETION_CALL.finditer(sa_src):
        sa_completion.add(m.group(1))

    fe_event_types = set(fe_sites.keys())
    sa_event_types = set(sa_sites.keys())

    # Union membership — a canonical type the frontend emits but the
    # standalone never does.
    missing_event_types = sorted(
        t for t in canonical_events
        if t in fe_event_types and t not in sa_event_types
    )

    # Standalone references a type the union has dropped or never had.
    orphan_event_types = sorted(t for t in sa_event_types if t not in canonical_events)

    # Async-completion gap — types where frontend calls
    # `recordCompletion(type)` but standalone never does.
    missing_completion = sorted(t for t in fe_completion if t not in sa_completion)

    # Per-event detail-key drift. Only compare events whose frontend
    # call site provides an object literal — when the React handler
    # passes a bare identifier (e.g. ``record('config_loaded',
    # buildConfigInteractionDetails())``) the regex cannot see into
    # the return value and the extracted key set would be empty,
    # producing false "drift" signals against a standalone that
    # correctly emits all documented keys.
    detail_key_drift: list[dict] = []
    for t in sorted(fe_event_types & sa_event_types & canonical_events):
        fe = fe_keys.get(t, set())
        sa = sa_keys.get(t, set())
        if not fe:
            continue  # frontend details are in a bare identifier
        if fe and sa and fe != sa:
            detail_key_drift.append({
                "event_type": t,
                "frontend_keys": sorted(fe),
                "standalone_keys": sorted(sa),
                "missing_in_standalone": sorted(fe - sa),
                "extra_in_standalone": sorted(sa - fe),
                "frontend_sites": fe_sites[t][:3],
                "standalone_sites": sa_sites[t][:3],
            })

    sa_api = extract_standalone_api_paths(STANDALONE)
    missing_api_paths = sorted(
        p for p in canonical_api
        if p not in sa_api
        # Filter picker / PDF static routes handled outside axios
        and p not in {"/api/pick-path"}
    )

    sa_settings = extract_standalone_setting_fields(STANDALONE)
    # The React side uses camelCase (``networkPath``); the standalone
    # historically mirrors the API payload (``network_path``) and uses
    # that as the useState key. Compare on a normalised form (lower +
    # underscores stripped) so we don't flag the convention drift as a
    # parity failure.

    def _norm(name: str) -> str:
        return re.sub(r"_", "", name).lower()

    sa_norm = {_norm(s) for s in sa_settings}
    missing_settings = sorted(
        s for s in canonical_settings
        if _norm(s) not in sa_norm
    )

    return {
        "canonical_event_count": len(canonical_events),
        "frontend_event_count": len(fe_event_types),
        "standalone_event_count": len(sa_event_types),
        "missing_event_types": [
            {"type": t, "frontend_sites": fe_sites[t][:3]}
            for t in missing_event_types
        ],
        "orphan_event_types": [
            {"type": t, "standalone_sites": sa_sites[t][:3]}
            for t in orphan_event_types
        ],
        "missing_completion": missing_completion,
        "detail_key_drift": detail_key_drift,
        "missing_api_paths": missing_api_paths,
        "missing_settings": missing_settings,
    }


def render_human(report: dict) -> str:
    out: list[str] = []
    out.append("STANDALONE PARITY REPORT")
    out.append("=" * 72)
    out.append(
        f"InteractionType union: {report['canonical_event_count']} types. "
        f"Frontend emits {report['frontend_event_count']}, "
        f"standalone emits {report['standalone_event_count']}."
    )
    out.append("")

    fail = False

    # ---- Missing event types
    m = report["missing_event_types"]
    if m:
        fail = True
        out.append(f"[FAIL] {len(m)} event types emitted by the frontend but "
                   f"not by the standalone:")
        for entry in m:
            out.append(f"   - {entry['type']:35s}  (fe: {fmt_sites(entry['frontend_sites'])})")
        out.append("")

    # ---- Orphan event types
    o = report["orphan_event_types"]
    if o:
        fail = True
        out.append(f"[FAIL] {len(o)} event types emitted by the standalone but "
                   f"not declared in InteractionType:")
        for entry in o:
            out.append(f"   - {entry['type']:35s}  (sa: {fmt_sites(entry['standalone_sites'])})")
        out.append("")

    # ---- recordCompletion gap
    mc = report["missing_completion"]
    if mc:
        fail = True
        out.append(f"[FAIL] {len(mc)} async wait-point *_completed events emitted "
                   f"by the frontend but never in the standalone:")
        for t in mc:
            out.append(f"   - {t}")
        out.append("")

    # ---- Detail-key drift
    d = report["detail_key_drift"]
    if d:
        fail = True
        out.append(f"[FAIL] {len(d)} events whose `details` object-literal keys "
                   f"diverge between frontend and standalone:")
        for entry in d:
            out.append(f"   - {entry['event_type']}")
            out.append(f"        frontend:   {{{', '.join(entry['frontend_keys'])}}}")
            out.append(f"        standalone: {{{', '.join(entry['standalone_keys'])}}}")
            if entry["missing_in_standalone"]:
                out.append(f"        missing:    {entry['missing_in_standalone']}")
            if entry["extra_in_standalone"]:
                out.append(f"        extra:      {entry['extra_in_standalone']}")
        out.append("")

    # ---- API-path gap
    ma = report["missing_api_paths"]
    if ma:
        fail = True
        out.append(f"[FAIL] {len(ma)} API paths referenced by the frontend but "
                   f"not by the standalone:")
        for p in ma:
            out.append(f"   - {p}")
        out.append("")

    # ---- Settings-field gap
    ms = report["missing_settings"]
    if ms:
        fail = True
        out.append(f"[WARN] {len(ms)} SettingsState fields whose identifier was "
                   f"not found in the standalone (best-effort grep):")
        for s in ms:
            out.append(f"   - {s}")
        out.append("")

    if not fail:
        out.append("[OK] standalone_interface.html is in full Layer-1 parity with frontend/.")
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    parser.add_argument(
        "--allow-warn", action="store_true",
        help="exit 0 even if there are [WARN] findings (FAILs still exit 1)",
    )
    args = parser.parse_args()

    report = run_checks()
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_human(report))

    hard_fail = (
        report["missing_event_types"]
        or report["orphan_event_types"]
        or report["missing_completion"]
        or report["detail_key_drift"]
        or report["missing_api_paths"]
    )
    return 1 if hard_fail else 0


if __name__ == "__main__":
    sys.exit(main())
