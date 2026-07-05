"""
Application entry point.

Run directly:
    python main.py

Or via uvicorn (recommended for production):
    uvicorn main:app --host 0.0.0.0 --port 8000

Or via Docker:
    docker-compose up
"""

import uvicorn

from app.core.application import create_app
from app.core.config import get_config

# Create the FastAPI application instance
# Using the factory pattern allows tests to call create_app() independently
app = create_app()


if __name__ == "__main__":
    import platform
    config = get_config()

    # uvloop is only available on Linux/macOS — fall back to asyncio on Windows
    loop = "uvloop" if platform.system() != "Windows" else "asyncio"
    http_parser = "httptools" if platform.system() != "Windows" else "h11"

    uvicorn.run(
        "main:app",
        host=config.host,
        port=config.port,
        reload=config.is_development,
        log_level=config.log_level.lower(),
        access_log=False,
        workers=1 if config.is_development else 4,
        loop=loop,
        http=http_parser,
    )
