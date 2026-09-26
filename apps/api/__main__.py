"""Точка входа API: uvicorn apps.api.main:app."""

from __future__ import annotations

import uvicorn

from core.config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "apps.api.main:app",
        host=settings.app.host,
        port=settings.app.port,
        reload=settings.app.debug,
        log_config=None,
    )


if __name__ == "__main__":
    main()
