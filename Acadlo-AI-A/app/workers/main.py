"""ARQ Worker entry point"""
from arq import func

from app.core.config import settings
from app.workers.settings import WorkerSettings as BaseWorkerSettings, redis_settings
from app.workers.tasks import process_ingestion_job


class WorkerSettings(BaseWorkerSettings):
    """
    Worker settings with registered task functions.
    
    Run the worker with:
        arq app.workers.main.WorkerSettings
        
    Or in development:
        python -m arq app.workers.main.WorkerSettings
    """
    
    # Explicitly set redis_settings to ensure it's not lost in inheritance
    redis_settings = redis_settings
    
    # Register task functions
    functions = [
        func(
            process_ingestion_job,
            timeout=settings.WORKER_JOB_TIMEOUT_SECONDS,
            max_tries=settings.WORKER_MAX_TRIES,
        ),
    ]
    
    # Startup handler
    @staticmethod
    async def on_startup(ctx):
        """Called when worker starts"""
        print("🚀 Acadlo AI Worker starting...")
        print("📋 Registered tasks: ['process_ingestion_job']")
        print(
            "⚙️ Worker runtime: "
            f"timeout={settings.WORKER_JOB_TIMEOUT_SECONDS}s, "
            f"max_jobs={settings.WORKER_MAX_JOBS}, "
            f"max_tries={settings.WORKER_MAX_TRIES}"
        )
    
    # Shutdown handler
    @staticmethod
    async def on_shutdown(ctx):
        """Called when worker shuts down"""
        print("👋 Acadlo AI Worker shutting down...")


# For direct execution
if __name__ == "__main__":
    import asyncio
    from arq import run_worker
    
    asyncio.run(run_worker(WorkerSettings))
