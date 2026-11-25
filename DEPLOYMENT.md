# Deployment Information

## Public URL
https://k5-l3a-day14-nguyenxuanhung-2a202603599.onrender.com

## Platform
Render (Docker Web Service + Key Value / Valkey Redis, Region `oregon`)

## Test Commands

### Health & Readiness Check
```bash
curl https://k5-l3a-day14-nguyenxuanhung-2a202603599.onrender.com/health
# Expected: {"status":"ok","environment":"production"}

curl https://k5-l3a-day14-nguyenxuanhung-2a202603599.onrender.com/ready
# Expected: {"status":"ready"}
```

### API Test (without key -> 401, with key -> 200)
```bash
curl -i -X POST https://k5-l3a-day14-nguyenxuanhung-2a202603599.onrender.com/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello"}'
# Expected: HTTP 401

curl -i -X POST https://k5-l3a-day14-nguyenxuanhung-2a202603599.onrender.com/ask \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test", "question": "Hello"}'
# Expected: HTTP 200
```

## Environment Variables Set
- `PORT` (injected by Render)
- `REDIS_URL` (Internal Key Value URL from Render Redis/Valkey service)
- `AGENT_API_KEY` (configured securely in Render dashboard)
- `ENVIRONMENT=production`
- `RATE_LIMIT_PER_MINUTE=10`
- `DAILY_BUDGET_USD=1.0`

## Screenshots
- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
