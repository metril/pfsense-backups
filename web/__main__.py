"""Uvicorn entrypoint for the web service."""

from __future__ import annotations

import logging

import uvicorn

from pfsense_shared.settings import WebSettings


def main() -> None:
    settings = WebSettings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    # Forward uvicorn's own proxy-header handling through the SAME
    # allowlist we enforce in ``web.middleware``. Uvicorn's
    # ``ProxyHeadersMiddleware`` runs BEFORE ours and rewrites
    # ``request.client`` from ``X-Forwarded-For``; if we left
    # ``forwarded_allow_ips="*"`` any caller could spoof their
    # source IP via the header and defeat rate-limiting + audit-log
    # client-IP correlation, regardless of what ``TRUSTED_PROXIES``
    # is set to. Pass the same allowlist so the two layers agree.
    trusted = settings.trusted_proxies_list
    forwarded_allow_ips: str | list[str]
    if trusted == "*":
        forwarded_allow_ips = "*"
    else:
        forwarded_allow_ips = trusted or ["127.0.0.1", "::1"]

    uvicorn.run(
        "web.app:create_app",
        host="0.0.0.0",
        port=settings.web_port,
        factory=True,
        forwarded_allow_ips=forwarded_allow_ips,
        proxy_headers=True,
        log_level=settings.log_level.lower(),
        # Drop uvicorn's default log config so its loggers propagate to the
        # root logger configured by basicConfig above — uvicorn access lines
        # and exception tracebacks then share our ISO-timestamped format and
        # land in `docker logs` alongside the app's own output.
        log_config=None,
        access_log=True,
    )


if __name__ == "__main__":
    main()
