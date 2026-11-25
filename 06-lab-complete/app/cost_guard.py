"""
Cost guard (tiêu chí 8) — Theo dõi chi phí LLM theo ngày trong Redis.
"""
from datetime import datetime, timezone

from fastapi import HTTPException
import redis

from app.config import settings
from app.redis_client import r

# Giá USD / 1K tokens (tham khảo gpt-4o-mini)
PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006


def _budget_key() -> str:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"budget:daily:{day}"


def check_budget() -> None:
    """Gọi TRƯỚC khi gọi LLM. Hết budget -> raise HTTPException(status_code=402)."""
    if r is None:
        raise HTTPException(status_code=503, detail="Redis unavailable")
    try:
        spent = float(r.get(_budget_key()) or 0.0)
    except redis.RedisError as exc:
        raise HTTPException(status_code=503, detail="Redis unavailable") from exc

    if spent >= settings.daily_budget_usd:
        raise HTTPException(status_code=402, detail="Daily budget exceeded")


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Gọi SAU khi gọi LLM. Cộng chi phí vào tổng ngày trong Redis."""
    cost = (input_tokens / 1000.0) * PRICE_INPUT_PER_1K + (
        output_tokens / 1000.0
    ) * PRICE_OUTPUT_PER_1K
    if r is not None:
        key = _budget_key()
        try:
            pipe = r.pipeline()
            pipe.incrbyfloat(key, cost)
            pipe.expire(key, 172800)
            pipe.execute()
        except redis.RedisError:
            pass
    return round(cost, 8)
