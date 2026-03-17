"""ARQ Worker settings and configuration"""
from arq.connections import RedisSettings
from app.core.config import settings


def parse_redis_url(url: str) -> RedisSettings:
    """
    Parse a Redis URL into ARQ RedisSettings.
    
    Supports formats:
    - redis://host:port
    - redis://host:port/db
    - redis://:password@host:port/db
    
    Also accepts scheme-less values like "redis:6379" by normalising them.
    Raises ValueError when no hostname can be resolved instead of silently
    falling back to localhost (which masks misconfiguration).
    """
    from urllib.parse import urlparse
    
    # Normalise missing scheme for values such as "redis:6379" or "redis:6379/0"
    normalised_url = url if "://" in url else f"redis://{url}"
    parsed = urlparse(normalised_url)
    
    if not parsed.hostname:
        raise ValueError(f"Invalid REDIS_URL '{url}': hostname is missing")
    
    return RedisSettings(
        host=parsed.hostname,
        port=parsed.port or 6379,
        password=parsed.password,
        database=int(parsed.path.lstrip("/") or 0) if parsed.path else 0,
    )


# Redis connection settings for ARQ
redis_settings = parse_redis_url(settings.REDIS_URL)


class WorkerSettings:
    """
    ARQ Worker settings class.
    
    This is imported by the arq CLI:
        arq app.workers.main.WorkerSettings
    """
    # Redis connection
    redis_settings = redis_settings
    
    # Worker configuration
    max_jobs = settings.WORKER_MAX_JOBS
    job_timeout = settings.WORKER_JOB_TIMEOUT_SECONDS
    max_tries = settings.WORKER_MAX_TRIES
    
    # Health check interval
    health_check_interval = 10
    
    # Queue name
    queue_name = "acadlo:queue"
    
    # Functions to register (will be set in main.py)
    functions = []
