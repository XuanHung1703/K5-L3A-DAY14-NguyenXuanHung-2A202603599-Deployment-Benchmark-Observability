"""
Production AI Agent — Part 6 Final Project.
"""
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import logging
import signal
import sys
import time

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import check_budget, record_cost
from app.rate_limiter import check_rate_limit
from app.redis_client import redis_healthy
from utils.mock_llm import ask as llm_ask


class JsonFormatter(logging.Formatter):
    """Format mọi log record thành 1 JSON object hợp lệ trên 1 dòng."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "lvl": record.levelname,
            "logger": record.name,
        }
        raw = record.getMessage()
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                payload.update(parsed)
            else:
                payload["msg"] = raw
        except (TypeError, ValueError):
            payload["msg"] = raw
        return json.dumps(payload, ensure_ascii=False)


handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JsonFormatter())
logger = logging.getLogger("production_agent")
logger.setLevel(logging.INFO)
logger.handlers = [handler]
logger.propagate = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    prev_sigterm = signal.getsignal(signal.SIGTERM)

    def _on_sigterm(signum, frame):
        logger.info(json.dumps({"event": "sigterm", "signal": signum}))
        if callable(prev_sigterm):
            prev_sigterm(signum, frame)

    signal.signal(signal.SIGTERM, _on_sigterm)
    logger.info(
        json.dumps({
            "event": "startup",
            "environment": settings.environment,
            "port": settings.port,
        })
    )
    yield
    logger.info(json.dumps({"event": "shutdown", "environment": settings.environment}))


app = FastAPI(title="Production AI Agent", lifespan=lifespan)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    user_id: str | None = Field(default=None, max_length=128)


@app.get("/health")
def health():
    """Liveness probe — luôn trả 200 khi process còn chạy."""
    return {"status": "ok", "environment": settings.environment}


@app.get("/ready")
def ready():
    """Readiness probe — 200 khi Redis sẵn sàng, 503 khi mất kết nối."""
    if not redis_healthy():
        raise HTTPException(status_code=503, detail="Redis unavailable")
    return {"status": "ready"}


@app.post("/ask")
def ask(body: AskRequest, api_key: str = Depends(verify_api_key)):
    start = time.perf_counter()
    check_rate_limit(api_key)
    check_budget()

    answer = llm_ask(body.question)
    in_tokens = max(1, len(body.question.split()) * 2)
    out_tokens = max(1, len(answer.split()) * 2)
    cost = record_cost(in_tokens, out_tokens)
    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)

    logger.info(
        json.dumps({
            "event": "request",
            "path": "/ask",
            "status": 200,
            "ms": elapsed_ms,
            "user_id": body.user_id,
            "cost_usd": cost,
        })
    )
    return {
        "question": body.question,
        "answer": answer,
        "user_id": body.user_id,
        "cost_usd": cost,
    }
