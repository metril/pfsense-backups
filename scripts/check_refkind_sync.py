"""Drift detector for the frontend ``RefKind`` union vs the backend
``_ROW_SCOPES`` / ``_KIND_ANCHORS`` tables.

Three places must stay in sync when a new kind of cross-reference is
added:

- ``frontend/src/lib/xref.ts``  — ``RefKind`` union, ``SCOPE_TO_SECTION_ID``
- ``pfsense_shared/pfsense_positions.py``    — ``_KIND_ANCHORS``
- ``pfsense_shared/pfsense_anchor_values.py`` — ``_ROW_SCOPES``

Existing Python-side drift is caught by the bidirectional assertion in
``tests/pfsense_shared/test_v022_positions.py``. Frontend-side drift
(new kind on the backend that the frontend never emits, or vice versa)
has no test. This script parses the TypeScript source with a couple
of narrow regexes, imports the Python tables, and prints a diff; the
companion pytest gate (``tests/test_refkind_sync.py``) fails CI if
any skew appears.

Run directly:  ``python scripts/check_refkind_sync.py``
Exits non-zero + prints the delta when the three tables disagree.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
XREF_TS = ROOT / "frontend" / "src" / "lib" / "xref.ts"

# Kinds that live on ONE side only by explicit design.
# ``interface`` is emitted by ``_interface_anchors`` (element-tag keyed,
# not xpath-keyed) so it isn't in ``_KIND_ANCHORS`` but IS in
# ``_ROW_SCOPES`` + the frontend ``RefKind``.
# ``rule`` / ``nat`` go through ``_firewall_and_nat_anchors`` on the
# positions side and through ``rowAnchorId`` on the frontend (not
# ``itemId`` / ``RefKind``) — they're scopes, not kinds.
_EXPECTED_ASYMMETRY_FRONTEND_ONLY: frozenset[str] = frozenset()
_EXPECTED_ASYMMETRY_BACKEND_ONLY: frozenset[str] = frozenset()


def parse_ts_refkind_union(source: str) -> set[str]:
    """Extract the quoted string literals that make up the ``RefKind``
    union. Stops at the closing semicolon so the comment-block VLAN
    entry at the end is captured correctly."""
    m = re.search(
        r"export\s+type\s+RefKind\s*=\s*([^;]+);",
        source,
    )
    if not m:
        raise RuntimeError("RefKind union not found in xref.ts")
    body = m.group(1)
    return set(re.findall(r'"([a-z0-9_]+)"', body))


def parse_ts_scope_to_section_keys(source: str) -> set[str]:
    """Extract the keys of the ``SCOPE_TO_SECTION_ID`` object literal.
    These are scopes (RefKinds plus ``rule`` / ``nat``); we surface the
    full key set so callers can check superset relationships."""
    m = re.search(
        r"SCOPE_TO_SECTION_ID\s*:\s*Record<[^>]+>\s*=\s*\{([^}]+)\}",
        source,
    )
    if not m:
        raise RuntimeError("SCOPE_TO_SECTION_ID not found in xref.ts")
    body = m.group(1)
    # Keys are bare identifiers before a colon (TS object-literal
    # shorthand), not quoted strings.
    return set(re.findall(r"(?m)^\s*([a-z_][a-z0-9_]*)\s*:", body))


def parse_backend_kinds() -> tuple[set[str], set[str]]:
    """Import the Python tables at runtime and return
    ``(positions_kinds, resolver_scopes)``. Positions gets the
    ``_KIND_ANCHORS`` kinds PLUS ``interface`` (handled by
    ``_interface_anchors``) and ``rule`` / ``nat`` (handled by
    ``_firewall_and_nat_anchors``). Resolver gets ``_ROW_SCOPES`` keys
    verbatim."""
    # Import here (not at module top) so a bare ``python scripts/
    # check_refkind_sync.py`` invocation works from a fresh checkout
    # without the web / worker extras installed.
    sys.path.insert(0, str(ROOT))
    from pfsense_shared import pfsense_anchor_values as av
    from pfsense_shared import pfsense_positions as pp

    positions = {kind for kind, _, _ in pp._KIND_ANCHORS}
    positions.add("interface")
    positions.update({"rule", "nat"})

    return positions, set(av._ROW_SCOPES.keys())


def main() -> int:
    ts_source = XREF_TS.read_text()
    ts_refkinds = parse_ts_refkind_union(ts_source)
    ts_scopes = parse_ts_scope_to_section_keys(ts_source)

    positions, scopes = parse_backend_kinds()

    errors: list[str] = []

    # Frontend RefKind ≡ backend positions kinds (minus rule/nat which
    # are scopes on the frontend, not kinds).
    expected_refkinds = positions - {"rule", "nat"} - _EXPECTED_ASYMMETRY_BACKEND_ONLY
    missing_in_frontend = expected_refkinds - ts_refkinds
    extra_in_frontend = ts_refkinds - expected_refkinds - _EXPECTED_ASYMMETRY_FRONTEND_ONLY
    if missing_in_frontend:
        errors.append(
            f"backend emits kinds not in frontend RefKind: "
            f"{sorted(missing_in_frontend)}"
        )
    if extra_in_frontend:
        errors.append(
            f"frontend RefKind has kinds with no backend position: "
            f"{sorted(extra_in_frontend)}"
        )

    # Frontend SCOPE_TO_SECTION_ID ≡ backend scopes (resolver sees
    # the ``rule`` / ``nat`` scopes too, so include them).
    expected_scopes = scopes
    missing_in_frontend_scopes = expected_scopes - ts_scopes
    extra_in_frontend_scopes = ts_scopes - expected_scopes
    if missing_in_frontend_scopes:
        errors.append(
            f"backend has scopes not mapped in frontend "
            f"SCOPE_TO_SECTION_ID: {sorted(missing_in_frontend_scopes)}"
        )
    if extra_in_frontend_scopes:
        errors.append(
            f"frontend SCOPE_TO_SECTION_ID has scopes with no backend "
            f"_ROW_SCOPES entry: {sorted(extra_in_frontend_scopes)}"
        )

    if errors:
        print("RefKind sync drift detected:")
        for e in errors:
            print(f"  - {e}")
        print(
            "\nUpdate RefKind union + KIND_TO_GROUP + emptyByKind + "
            "SCOPE_TO_SECTION_ID in frontend/src/lib/xref.ts to match "
            "backend, or remove the backend entry if the frontend "
            "never emits chips for that kind."
        )
        return 1

    print(
        f"RefKind sync OK: {len(ts_refkinds)} kinds, "
        f"{len(ts_scopes)} scopes"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
