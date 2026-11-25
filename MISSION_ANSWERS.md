# Day 14 Lab — Mission Answers

## Part 1: Localhost vs Production (CP1)

### Exercise 1.1: Anti-patterns phát hiện trong `01-localhost-vs-production/develop/app.py`
1. **Hardcode secrets (dòng 17–18):** `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` và `DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"` nằm thẳng trong mã nguồn — lộ ngay khi push lên Git.
2. **Hardcode cấu hình (dòng 21–22):** `DEBUG = True`, `MAX_TOKENS = 500` không đọc từ biến môi trường, không linh hoạt giữa `development` / `staging` / `production`.
3. **Logging bằng `print()` và làm lộ secret (dòng 33–34, 38):** dùng `print()` khó parse trên hệ thống tập trung và in thẳng `OPENAI_API_KEY` ra stdout (`[DEBUG] Using key: sk-hardcoded-fake-key-never-do-this`).
4. **Thiếu health check endpoints (`/health`, `/ready`):** platform (Railway/Render/Docker/K8s) không biết khi nào container sống hoặc sẵn sàng nhận traffic để restart hoặc route request.
5. **Bind `host="localhost"`, cố định `port=8000` và bật `reload=True` (dòng 51–53):** chạy trong container sẽ không nhận được kết nối từ bên ngoài, không dùng được biến `PORT` do cloud cấp, và `reload=True` gây tốn tài nguyên/rủi ro ở production.
6. **Không xử lý Graceful Shutdown:** thiếu `lifespan` hoặc xử lý `SIGTERM` để hoàn thành request đang chạy trước khi tắt.

### Exercise 1.2: Kết quả chạy bản `develop`
- Log server:
```text
[DEBUG] Got question: Hello
[DEBUG] Using key: sk-hardcoded-fake-key-never-do-this
[DEBUG] Response: Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.
INFO:     127.0.0.1:59556 - "POST /ask?question=Hello HTTP/1.1" 200 OK
```
- Kết quả `curl -i -X POST "http://localhost:8000/ask?question=Hello"`:
```http
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 08:37:39 GMT
server: uvicorn
content-length: 103
content-type: application/json

{"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
```

### Exercise 1.3: So sánh `develop/app.py` vs `production/app.py`
- Kết quả test bản `production`:
```json
{"status":"ok","uptime_seconds":19.1,"version":"1.0.0","environment":"development","timestamp":"2026-11-25T08:41:43.452600+00:00"}
{"ready":true}
{"question":"Hello","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.","model":"gpt-4o-mini"}
```

| Feature | Develop (`develop/app.py`) | Production (`production/app.py`) | Tại sao quan trọng? |
| --- | --- | --- | --- |
| **Config & Secrets** | Hardcode `OPENAI_API_KEY`, `port=8000`, `host="localhost"` (dòng 17, 51–52) | Đọc qua `settings` từ env vars (`config.py`, dòng 24, 196–198) | Đổi cấu hình theo môi trường không cần sửa code; không commit secret lên Git |
| **Health & Readiness** | Không có `/health`, `/ready` | Có `GET /health` (dòng 135) và `GET /ready` (dòng 152, trả `503` nếu `!is_ready`) | Platform/LB biết khi nào container chết để restart và khi nào sẵn sàng nhận traffic |
| **Logging** | `print("[DEBUG] ...")`, in cả API key (dòng 33–34) | Structured JSON logging (`logging.basicConfig` JSON format + `json.dumps`, dòng 28–31, 111–122), không log secret | Dễ thu thập, tìm kiếm và cảnh báo trên log aggregator mà không lộ thông tin nhạy cảm |
| **Shutdown & Lifecycle** | Không có xử lý tắt tiến trình | Dùng `lifespan` (dòng 40–67) + `signal.signal(signal.SIGTERM, handle_sigterm)` (dòng 180–189) | Tránh ngắt đột ngột request đang xử lý khi deploy lại hoặc scale down |

---

## Part 2: Docker (CP2)

### Exercise 2.1: Trả lời câu hỏi về `02-docker/develop/Dockerfile`
1. **Base image:** `python:3.11` (bản đầy đủ OS + Python runtime + công cụ build, dung lượng lớn ~1 GB).
2. **Working directory:** `/app` (`WORKDIR /app`).
3. **Tại sao `COPY requirements.txt` trước `COPY . .`:** Tận dụng cơ chế Docker layer cache. Khi chỉ sửa code ứng dụng mà `requirements.txt` không đổi, Docker dùng lại layer `pip install` đã cache thay vì cài lại từ đầu.
4. **`CMD` vs `ENTRYPOINT`:** `CMD` định nghĩa lệnh/tham số mặc định và có thể bị ghi đè dễ dàng ở cuối lệnh `docker run`; `ENTRYPOINT` cố định tiến trình thực thi chính của container (các tham số truyền thêm hoặc `CMD` sẽ được nối làm đối số cho `ENTRYPOINT`).

### Exercise 2.2: Build và chạy container `my-agent:develop`
```http
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 08:45:53 GMT
server: uvicorn
content-length: 103
content-type: application/json
```

### Exercise 2.3: Multi-stage build & So sánh kích thước image
- **Stage 1 (`builder`):** dùng `python:3.11-slim`, cài `gcc`, `libpq-dev` và `pip install --no-cache-dir --user -r requirements.txt` vào `/root/.local`.
- **Stage 2 (`runtime`):** khởi tạo mới từ `python:3.11-slim`, tạo non-root user `appuser`, chỉ `COPY --from=builder /root/.local` cùng mã nguồn vào `/app` nên loại bỏ toàn bộ compiler (`gcc`), `libpq-dev` và apt cache, giúp image nhẹ và an toàn hơn.
- **Số đo thực tế (`docker images | grep my-agent`):**
  - `my-agent:develop`: `1.15 GB` (~1150 MB)
  - `my-agent:advanced`: `163 MB`
  - Chênh lệch: giảm **~85.8%** (từ `1150 MB` xuống `163 MB`)

### Exercise 2.4: Docker Compose stack (`02-docker/production/docker-compose.yml`)
- **Kiến trúc:**
```text
Client ──▶ Nginx (:80/:443) ──▶ Agent (:8000) ──┬──▶ Redis (:6379)
                                                └──▶ Qdrant (:6333)
                (mạng nội bộ: internal)
```
- **Kết quả test qua Nginx (`http://localhost`):**
```http
# GET /health
HTTP/1.1 200 OK
Server: nginx
Date: Wed, 25 Nov 2026 09:42:04 GMT
Content-Type: application/json
Content-Length: 95
Connection: keep-alive
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block

{"status":"ok","uptime_seconds":0.6,"version":"2.0.0","timestamp":"2026-11-25T09:42:04.701784"}

# POST /ask
HTTP/1.1 200 OK
Server: nginx
Date: Wed, 25 Nov 2026 09:42:04 GMT
Content-Type: application/json
Content-Length: 126
Connection: keep-alive
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block

{"answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}
```

---

## Part 3: Cloud Deployment (CP6)

*(Làm sau Part 6 — deploy trực tiếp `06-lab-complete/`)*

- **Public URL:** `[TODO: điền URL sau khi deploy lên Railway hoặc Render]`
- **Screenshot:** `[TODO: screenshots/dashboard.png, screenshots/running.png, screenshots/test.png]`
- **So sánh `railway.toml` vs `render.yaml`:**
  - **`06-lab-complete/railway.toml` (TOML):** cấu hình ngắn gọn theo từng block `[build]` (`builder = "DOCKERFILE"`, `dockerfilePath = "Dockerfile"`) và `[deploy]` (`healthcheckPath = "/health"`, `restartPolicyType`). Biến môi trường và secret (`AGENT_API_KEY`, `REDIS_URL`) không khai báo trong `railway.toml` mà đặt trực tiếp trên Railway Dashboard hoặc bằng CLI `railway variables set`; `PORT` do Railway tự inject lúc chạy.
  - **`06-lab-complete/render.yaml` (YAML Blueprint):** khai báo đầy đủ Infrastructure-as-Code cho cả danh sách `services` (`type: web`, `runtime: docker`, `healthCheckPath: /health`), có thể định nghĩa luôn `envVars` ngay trong file (biến thường ghi `value`, còn secret như `AGENT_API_KEY`, `REDIS_URL` bắt buộc dùng `sync: false` hoặc `generateValue: true` để tránh hardcode).
  - **Lý do khác nhau:** Railway ưu tiên CLI/Dashboard và giữ file config tối giản chỉ phục vụ build/healthcheck, còn Render Blueprint (`render.yaml`) thiết kế để đồng bộ toàn bộ thông số service và schema biến môi trường ngay từ Git repo.
- **Exercise 3.3 — GCP Cloud Run (`03-cloud-deployment/production-cloud-run/`):**
  - Đọc `cloudbuild.yaml` và `service.yaml`: Pipeline CI/CD Cloud Build tự động chạy 4 bước tuần tự khi push lên `main`: (1) chạy `pytest tests/` trong container `python:3.11-slim` (`test`), (2) build Docker image gắn tag `$COMMIT_SHA` và `latest` tận dụng `--cache-from` (`build`), (3) đẩy các tag lên Container Registry (`push`), và (4) deploy lên Cloud Run vùng `asia-southeast1` với `min-instances=1`, `max-instances=10`, memory `512Mi`, gắn secret từ Google Secret Manager (`deploy`). File `service.yaml` (Knative) đặc tả thêm cấu hình production như `containerConcurrency: 80`, resource requests/limits, `livenessProbe` (`/health`) và `startupProbe` (`/ready`).

---

## Part 4: API Security (CP3)

### Exercise 4.1: API Key Authentication (`04-api-gateway/develop/app.py`)
- **Vị trí kiểm tra key:** trong dependency `verify_api_key` (đọc header `X-API-Key` bằng `APIKeyHeader(name="X-API-Key", auto_error=False)`), được inject vào `POST /ask` qua `_key: str = Depends(verify_api_key)`.
- **Khi thiếu hoặc sai key:**
  - Thiếu header `X-API-Key` → trả `HTTP 401 Unauthorized`.
  - Sai giá trị key so với `AGENT_API_KEY` → trả `HTTP 403 Forbidden` (`Invalid API key.`).
- **Cách rotate key:** không hardcode key trong code mà đọc từ biến môi trường `AGENT_API_KEY`; khi rotate chỉ cần cập nhật biến môi trường trên server/cloud và restart/reload service (hoặc hỗ trợ danh sách gồm key cũ + key mới trong giai đoạn chuyển tiếp để không làm gián đoạn client).

- **Kết quả test thực tế (`curl -i`):**
```http
# 1. Không có X-API-Key → 401
HTTP/1.1 401 Unauthorized
date: Wed, 25 Nov 2026 08:55:26 GMT
server: uvicorn
content-length: 67
content-type: application/json

{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}

# 2. Có X-API-Key đúng → 200
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 08:55:26 GMT
server: uvicorn
content-length: 145
content-type: application/json

{"question":"Hello","answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}
```

### Exercise 4.2 & 4.3: JWT Authentication & Rate Limiting (`04-api-gateway/production/`)
- **JWT Flow (`auth.py`):**
  1. Client gửi `POST /auth/token` với `username` / `password` (`student` / `demo123`).
  2. Server xác thực bằng `authenticate_user()`, tạo JWT ký bằng thuật toán `HS256` chứa `sub` (username), `role` (`user`/`admin`), `iat`, `exp` (60 phút).
  3. Các request tới `POST /ask` gửi kèm `Authorization: Bearer <token>`; `verify_token()` giải mã và kiểm tra chữ ký + hạn dùng (stateless, không cần query DB mỗi request).
- **Rate Limiter (`rate_limiter.py`):**
  - **Thuật toán:** **Sliding Window Counter** (mỗi `user_id` có một `deque` lưu các timestamp request trong cửa sổ `window_seconds = 60`; mỗi lần kiểm tra sẽ pop các timestamp cũ hơn `now - 60` rồi đếm số phần tử còn lại).
  - **Giới hạn:** `10 requests/phút` cho role `user` (`rate_limiter_user`), `100 requests/phút` cho role `admin` (`rate_limiter_admin`).
  - **Bypass / phân tầng cho admin:** trong `app.py` (dòng 141), kiểm tra `user["role"] == "admin"` để chọn `rate_limiter_admin` (hoặc bỏ qua bước `limiter.check()` nếu muốn admin bypass hoàn toàn).

- **Kết quả test thực tế (`curl -i`, đã che JWT token):**
```http
# Đăng nhập POST /auth/token (student / demo123) → nhận Bearer token (đã che):
# {"access_token":"<REDACTED_JWT_TOKEN>","token_type":"bearer","expires_in_minutes":60}

# 1. Request hợp lệ với Bearer token → 200 OK
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 08:57:51 GMT
server: uvicorn
content-length: 192
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"question":"Explain JWT","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.","usage":{"requests_remaining":9,"budget_remaining_usd":1.9e-05}}

# 2. Chạy vòng lặp 12 requests liên tiếp (requests 1..9 trả 200, requests_remaining giảm từ 8 về 0):
=== Request 9 ===
HTTP/1.1 200 OK
...
{"question":"Test 9","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.","usage":{"requests_remaining":0,"budget_remaining_usd":0.000186}}

# 3. Từ Request 10 trở đi vượt ngưỡng 10 req/phút → 429 Too Many Requests (output đầy đủ ở Request 11):
Request 11: HTTP/1.1 429 Too Many Requests
date: Wed, 25 Nov 2026 09:41:23 GMT
server: uvicorn
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
x-ratelimit-reset: 1795599743
retry-after: 59
content-length: 98
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin
connection: close

{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
```

### Exercise 4.4: Cost Guard (`04-api-gateway/production/cost_guard.py`)
- **Cách hoạt động:**
  1. **Trước khi gọi LLM (`check_budget`):** kiểm tra tổng chi tiêu toàn hệ thống (`global_daily_budget_usd = $10/ngày` → vượt trả `503`) và chi tiêu theo ngày của từng user (`daily_budget_usd = $1/ngày` → vượt trả `402 Payment Required`). Nếu đạt ngưỡng cảnh báo (`warn_at_pct = 0.8`, tức 80%) thì ghi log warning.
  2. **Sau khi gọi LLM (`record_usage`):** tính chi phí dựa trên số `input_tokens` và `output_tokens` nhân với đơn giá (`PRICE_PER_1K_INPUT_TOKENS = 0.00015`, `PRICE_PER_1K_OUTPUT_TOKENS = 0.0006`) rồi cộng dồn vào usage của user và tổng hệ thống.
  3. **Production với Redis:** thay vì lưu `_records` trong RAM (bị mất khi restart và không đồng bộ giữa nhiều instance), dùng Redis key theo ngày/tháng (ví dụ `budget:{user_id}:{YYYY-MM-DD}`) với `INCRBYFLOAT` và đặt `EXPIRE` tự reset sau hết kỳ.
- **Vì sao cần cả Rate Limiting lẫn Cost Guard:**
  - **Rate Limiting** bảo vệ **tốc độ và hạ tầng** (ngăn spam burst gây quá tải CPU/worker/upstream trong ngắn hạn, giới hạn số request/phút).
  - **Cost Guard** bảo vệ **tài chính/ngân sách** (vì một request hợp lệ với prompt hoặc output rất dài vẫn có thể đốt nhiều token và tốn tiền, nên cần trần chi phí theo USD/ngày hoặc tháng ngay cả khi client không vượt rate limit).

### Thảo luận thêm (`04-api-gateway/README.md`)
1. **API Key vs JWT vs OAuth2:** API Key phù hợp cho giao tiếp server-to-server / internal API hoặc MVP đơn giản; JWT phù hợp cho auth stateless theo user/role có thời hạn (`exp`); OAuth2 dùng khi cần ủy quyền cho ứng dụng bên thứ 3 hoặc đăng nhập qua IdP (Google/GitHub).
2. **Mức rate limit cho AI agent:** thường đặt thấp hơn web API truyền thống (ví dụ `10–30 req/phút` cho user thường, cao hơn cho admin/paid tier) vì mỗi request LLM tốn nhiều thời gian và chi phí token, kết hợp giới hạn đồng thời theo token/cost.
3. **Khi API key bị lộ:** phát hiện qua log bất thường (tăng đột biến request, chi phí hoặc IP lạ), lập tức thu hồi (revoke) key cũ, tạo key mới qua biến môi trường/secret manager và xóa sạch khỏi git history nếu lỡ commit.

---

## Part 5: Scaling & Reliability (CP4)

### Exercise 5.1 & 5.2: Health Check, Readiness & Graceful Shutdown (`05-scaling-reliability/develop/app.py`)
- **Phân biệt `/health` (Liveness) vs `/ready` (Readiness):**
  - `GET /health` kiểm tra process còn sống không (nếu lỗi/timeout, orchestrator sẽ restart container).
  - `GET /ready` kiểm tra instance đã sẵn sàng nhận traffic chưa (nếu chưa khởi tạo xong, đang shutdown hoặc mất kết nối Redis/DB thì trả `HTTP 503` để load balancer ngừng route traffic tới instance đó mà không cần restart oan).
- **Kết quả test `develop/app.py` với `SIGTERM`:**
```text
--- GET /health ---
{"status":"ok","uptime_seconds":0.5,"version":"1.0.0","environment":"development","timestamp":"2026-11-25T10:18:30.730890+00:00","checks":{"memory":{"status":"ok","note":"psutil not installed"}}}
--- GET /ready ---
{"ready":true,"in_flight_requests":1}
--- SIGTERM log ---
INFO:     Shutting down
INFO:     Waiting for application shutdown.
2026-11-25 17:18:30,940 INFO 🔄 Graceful shutdown initiated...
2026-11-25 17:18:30,940 INFO ✅ Shutdown complete
INFO:     Application shutdown complete.
INFO:     Finished server process [3584]
2026-11-25 17:18:30,941 INFO Received signal 15 — uvicorn will handle graceful shutdown
```

### Exercise 5.3–5.5: Stateless Design & Load Balancing (`05-scaling-reliability/production/`)
- **Lệnh chạy:** `docker compose -p k5-day14-scaling up -d --build --scale agent=3` và `python3 test_stateless.py` (cổng `8080`, endpoint `POST /chat`).
- **Kết quả thực tế (`test_stateless.py`):**
```text
============================================================
Stateless Scaling Demo
============================================================

Session ID: 17efcc06-06b3-4f56-8cce-69b1c6e0b00b

Request 1: [instance-8fa560]
  Q: What is Docker?
  A: Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!...

Request 2: [instance-dcef12]
  Q: Why do we need containers?
  A: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé....

Request 3: [instance-8fa560]
  Q: What is Kubernetes?
  A: Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ O...

Request 4: [instance-9c1e1f]
  Q: How does load balancing work?
  A: Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ O...

Request 5: [instance-dcef12]
  Q: What is Redis used for?
  A: Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận....

------------------------------------------------------------
Total requests: 5
Instances used: {'instance-8fa560', 'instance-9c1e1f', 'instance-dcef12'}
✅ All requests served despite different instances!

--- Conversation History ---
Total messages: 10
  [user]: What is Docker?...
  [assistant]: Container là cách đóng gói app để chạy ở mọi nơi. Build once...
  [user]: Why do we need containers?...
  [assistant]: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đ...
  [user]: What is Kubernetes?...
  [assistant]: Đây là câu trả lời từ AI agent (mock). Trong production, đây...
  [user]: How does load balancing work?...
  [assistant]: Đây là câu trả lời từ AI agent (mock). Trong production, đây...
  [user]: What is Redis used for?...
  [assistant]: Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã đư...

✅ Session history preserved across all instances via Redis!
```
- **Giải thích:** Nginx phân phối 5 request qua cả 3 container (`instance-8fa560`, `instance-dcef12`, `instance-9c1e1f`). Nếu lưu `conversation_history` trong RAM của từng instance thì mỗi instance chỉ thấy phần lịch sử của riêng nó và làm đứt ngữ cảnh hội thoại; nhờ lưu tập trung trong **Redis** (`session:{session_id}`), mọi instance đều đọc/ghi chung một state và `GET /chat/{session_id}/history` trả đủ toàn bộ 10 messages.

---

## Part 6: Final Project — Output `check_production_ready.py` (CP5)

Chạy `python check_production_ready.py` (đầy đủ với Docker trong WSL2) tại `06-lab-complete/`:

```text
================================================================
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 43/43 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
================================================================
```
*(Docker image size đo được: **160 MB**; `docker stop` exit code **0** trong **0.7s**).*

---

## AI Log

- **Công cụ sử dụng:** Antigravity (AI assistant).
- **Nội dung hỗ trợ:**
  1. Phân tích yêu cầu đề bài Day 14 theo quy định lớp K5 và lập kế hoạch theo từng Checkpoint (`CP0`–`CP8`).
  2. Hướng dẫn thiết lập môi trường WSL2 Ubuntu + tích hợp Docker Desktop và Python virtual environment (`~/.venv-day14`).
  3. Hướng dẫn và hỗ trợ chạy kiểm thử Part 1, Part 2 (`my-agent:develop` vs `my-agent:advanced`, Compose Nginx), Part 4 (`401` / `200` / `429`), Part 5 (`test_stateless.py`), hoàn thiện mã nguồn `06-lab-complete/` đạt `PASS 12/12`, bổ sung metric + `KNOWLEDGE_BASE` và chạy toàn bộ benchmark/observability Part 7 (CP7–CP8). Mọi số liệu, output và báo cáo trong `MISSION_ANSWERS.md` và `BENCHMARK_REPORT.md` đều trích trực tiếp từ các lệnh đã chạy trên máy; JWT token được che trước khi lưu.
