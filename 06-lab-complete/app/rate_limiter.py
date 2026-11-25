"""
Rate limiting (tiêu chí 7) — Sliding window 60s lưu trên Redis Sorted Set.
"""
import time
import uuid

from fastapi import HTTPException
import redis

from app.config import settings
from app.redis_client import r

WINDOW_SECONDS = 60


def check_rate_limit(key: str) -> None:
    """Giới hạn RATE_LIMIT_PER_MINUTE request / 60s cho mỗi API key."""
    if r is None:
        raise HTTPException(status_code=503, detail="Redis unavailable")

    redis_key = f"ratelimit:{key}"
    now = time.time()
    cutoff = now - WINDOW_SECONDS

    try:
        pipe = r.pipeline()
        pipe.zremrangebyscore(redis_key, 0, cutoff)
        pipe.zcard(redis_key)
        _, current_count = pipe.execute()

        if current_count >= settings.rate_limit_per_minute:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(WINDOW_SECONDS)},
            )

        member = f"{now}:{uuid.uuid4().hex}"
        pipe = r.pipeline()
        pipe.zadd(redis_key, {member: now})
        pipe.expire(redis_key, WINDOW_SECONDS)
        pipe.execute()
    except redis.RedisError as exc:
        raise HTTPException(status_code=503, detail="Redis unavailable") from exc
