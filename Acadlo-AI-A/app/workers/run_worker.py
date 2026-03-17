"""
ARQ Worker runner script.

This script properly handles the asyncio event loop for Python 3.10+
where asyncio.get_event_loop() behavior changed.

Run with:
    python -m app.workers.run_worker
"""
import asyncio
import sys
import logging

from arq import run_worker
from app.workers.main import WorkerSettings
from app.core.logging_config import setup_logging

logger = logging.getLogger(__name__)


def main():
    """Run the ARQ worker with proper event loop handling."""
    # Initialize logging system for worker process
    # Use "logs" for relative path (works in both Docker and local)
    setup_logging(
        log_dir="logs",
        retention_days=30,
        console_level="INFO",
        file_level="INFO"
    )
    logger.info("🚀 ARQ Worker starting with logging initialized")
    
    # For Python 3.10+, we need to create and set the event loop explicitly
    if sys.version_info >= (3, 10):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    
    # Run the worker
    run_worker(WorkerSettings)


if __name__ == "__main__":
    main()

