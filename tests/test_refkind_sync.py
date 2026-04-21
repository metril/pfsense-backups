"""Pytest gate that fails CI if frontend ``RefKind`` / backend
``_KIND_ANCHORS`` / ``_ROW_SCOPES`` drift apart.

Thin wrapper around ``scripts/check_refkind_sync.py`` — the real
logic lives in the script so operators can run it standalone
(``python scripts/check_refkind_sync.py``) without pytest. This
test just pins the checker's exit code into the normal test run
so a missing RefKind / SCOPE_TO_SECTION_ID addition never lands
without CI surfacing it.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "check_refkind_sync.py"


def test_refkind_sync() -> None:
    """Frontend RefKind table and backend anchor tables must stay in
    sync. Drift means silent tab-switch misses or blame-drawer None —
    user-visible regressions we've hit before (v0.26.0, v0.31.0)."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"RefKind sync checker failed:\nstdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
