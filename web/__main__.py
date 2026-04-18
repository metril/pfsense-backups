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
    uvicorn.run(
        "web.app:create_app",
        host="0.0.0.0",
        port=settings.web_port,
        factory=True,
        forwarded_allow_ips="*",
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
