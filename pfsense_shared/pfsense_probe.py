"""Shared pfSense HTTP probe primitives.

The actual I/O differs between worker (sync ``requests``) and web service
(async ``httpx``), but the detection signals — CSRF token extraction,
browser-like request headers, dashboard markers, and login-form
re-render markers — must agree across both so a synchronous preflight
from the web UI produces the same verdict as the scheduled backup run.
"""

from __future__ import annotations

import re

# pfSense renders the CSRF input with either attribute ordering depending
# on version and page; match both forms.
CSRF_RE_NAME_FIRST = re.compile(
    r"name=['\"]__csrf_magic['\"][^>]*value=['\"]([^'\"]*)['\"]"
)
CSRF_RE_VALUE_FIRST = re.compile(
    r"value=['\"]([^'\"]*)['\"][^>]*name=['\"]__csrf_magic['\"]"
)

# Some hardened pfSense builds reject requests without a sensible UA / Accept.
BROWSER_HEADERS: dict[str, str] = {
    "User-Agent": "Mozilla/5.0 (compatible; pfsense-backups/0.3)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# Positive: present only when the post-login response is the authenticated
# dashboard (or at least the authenticated chrome).
DASHBOARD_MARKERS: tuple[str, ...] = (
    "<title>Status: Dashboard",
    "widget-dashboard",
    'id="logout"',
    "index.php?logout",
)

# Negative: if any of these appear, the login form is still being rendered,
# which means auth failed regardless of the 200 status code. Reliable on
# themed / customized pfSense installs where the dashboard title is
# overridden.
LOGIN_FORM_MARKERS: tuple[str, ...] = (
    'name="passwordfld"',
    "name='passwordfld'",
    'name="usernamefld"',
    "name='usernamefld'",
)


def extract_csrf(html: str) -> str | None:
    m = CSRF_RE_NAME_FIRST.search(html) or CSRF_RE_VALUE_FIRST.search(html)
    return m.group(1) if m else None
