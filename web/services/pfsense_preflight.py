"""Async pfSense connection probe used by the instance editor's
"Test connection" button.

Mirrors the worker's authenticate flow (GET login page → extract
__csrf_magic → POST credentials → inspect response for dashboard
markers / login-form re-render) but over ``httpx`` so it integrates
with the FastAPI event loop and returns synchronously to the browser.
Detection constants are shared via ``pfsense_shared.pfsense_probe`` so
a green preflight matches what the scheduled backup will see.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from urllib.parse import urljoin

import httpx

from pfsense_shared.pfsense_probe import (
    BROWSER_HEADERS,
    DASHBOARD_MARKERS,
    LOGIN_FORM_MARKERS,
    extract_csrf,
)

log = logging.getLogger(__name__)


@dataclass
class PreflightResult:
    ok: bool
    detail: str
    duration_ms: int


async def probe(
    *,
    url: str,
    username: str,
    password: str,
    verify_ssl: bool = False,
    timeout_seconds: float = 15.0,
) -> PreflightResult:
    """Attempt a full pfSense login and classify the result."""
    start = time.monotonic()
    login_url = urljoin(url, "/index.php")
    try:
        async with httpx.AsyncClient(
            timeout=timeout_seconds, verify=verify_ssl, follow_redirects=True
        ) as client:
            # GET the login page so we can grab __csrf_magic.
            resp = await client.get(login_url, headers=BROWSER_HEADERS)
            resp.raise_for_status()
            csrf_token = extract_csrf(resp.text)
            if not csrf_token:
                # Not fatal — some pfSense builds omit CSRF on plain HTTP,
                # but flag it so a failed login isn't mysterious.
                log.info("preflight: no __csrf_magic on login page for %s", url)

            data = {"login": "Login", "usernamefld": username, "passwordfld": password}
            if csrf_token:
                data["__csrf_magic"] = csrf_token
            post_headers = {**BROWSER_HEADERS, "Referer": login_url}
            resp = await client.post(login_url, data=data, headers=post_headers)
            body = resp.text
            has_dashboard = any(m in body for m in DASHBOARD_MARKERS)
            has_login_form = any(m in body for m in LOGIN_FORM_MARKERS)
            duration_ms = int((time.monotonic() - start) * 1000)

            if has_dashboard and not has_login_form:
                return PreflightResult(
                    ok=True,
                    detail=f"Dashboard reached (HTTP {resp.status_code}).",
                    duration_ms=duration_ms,
                )
            if has_login_form:
                return PreflightResult(
                    ok=False,
                    detail=(
                        "Login form re-rendered — credentials rejected or MFA required."
                    ),
                    duration_ms=duration_ms,
                )
            return PreflightResult(
                ok=False,
                detail=(
                    f"Unexpected response (HTTP {resp.status_code}, "
                    f"{len(body)} bytes): no dashboard markers found."
                ),
                duration_ms=duration_ms,
            )
    except httpx.ConnectError as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        return PreflightResult(
            ok=False, detail=f"Cannot connect: {exc}", duration_ms=duration_ms
        )
    except httpx.TimeoutException:
        duration_ms = int((time.monotonic() - start) * 1000)
        return PreflightResult(
            ok=False,
            detail=f"Timed out after {timeout_seconds:.0f}s.",
            duration_ms=duration_ms,
        )
    except httpx.HTTPStatusError as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        return PreflightResult(
            ok=False,
            detail=f"HTTP error on login page: {exc.response.status_code}",
            duration_ms=duration_ms,
        )
    except Exception as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        log.exception("preflight: unexpected error against %s", url)
        return PreflightResult(
            ok=False, detail=f"Unexpected error: {exc}", duration_ms=duration_ms
        )
