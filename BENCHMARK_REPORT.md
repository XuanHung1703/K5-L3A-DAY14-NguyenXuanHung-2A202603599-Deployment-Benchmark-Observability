# Benchmark & Observability Report — Day 14

> Mọi con số dưới đây được trích trực tiếp từ các file trong `reports/`, `benchmark-results/` và Prometheus/Jaeger/Grafana thật.

**Họ tên:** Nguyễn Xuân Hùng (MSSV: 2A202603599)
**Ngày chạy:** 2026-11-25
**Môi trường:** Windows WSL2 Ubuntu (Python 3.14.4, Docker Desktop 29.9.3 / Compose v5.7.0)

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
| --- | --- | --- |
| p95 latency `/ask` | `< 500 ms` | Đảm bảo 95% người dùng nhận phản hồi dưới nửa giây; phù hợp với mock LLM base latency (~120–200ms) và giúp phát hiện sớm khi tail latency hoặc hàng đợi quá tải |
| Error rate `/ask` | `< 2.0 %` | Error budget 2% đủ chịu được nhiễu upstream ngẫu nhiên (~1% trong mock LLM) nhưng bắt được sự cố thật khi lỗi tăng bất thường |
| Accuracy trên golden dataset | `≥ 85 %` (mục tiêu `100 %` sau fix KB) | Ngăn regression về chất lượng câu trả lời trước khi merge code mới |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 (`reports/load_v2_c1.json`) | 4.59 | 191.7 | 221.1 | 1682.8 | 3.00% | FAIL (Error rate > 2.0%) |
| 10 (`reports/load_v2_c10.json`) | 34.30 | 192.5 | 223.6 | 1703.0 | 1.00% | PASS |
| 50 (`reports/load_v2_c50.json`) | 103.90 | 200.2 | 279.8 | 1715.1 | 1.33% | PASS |
| 100 (`reports/load_v2_c100.json`) | 72.87 | 354.5 | 2879.8 | 3071.3 | 0.67% | FAIL (p95 > 500ms) |

**Nhận xét:** RPS **không** tăng tuyến tính theo concurrency. Từ `c=1 → c=10 → c=50`, RPS tăng mạnh (`4.59 → 34.30 → 103.90 req/s`) nhờ xử lý async song song thời gian chờ I/O của mock LLM; nhưng khi lên `c=100` trên 1 worker Python, event loop / connection queue bắt đầu nghẽn khiến throughput tụt xuống `72.87 req/s` và p95 vọt từ `279.8 ms` lên `2879.8 ms`.

### 2.2 Tail latency (`--requests 300 --concurrency 20`)

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
| --- | ---: | ---: | ---: |
| `0` (`reports/load_v2_slow_0.json`) | 189.5 | 218.4 | 224.5 |
| `0.03` (mặc định, `reports/load_v2_slow_0.03.json`) | 235.7 | 220.9 | 1690.1 |
| `0.1` (`reports/load_v2_slow_0.1.json`) | 392.5 | 1694.6 | 1710.7 |

**Nhận xét:** `p99` (và `p95` khi tỉ lệ request chậm vượt 5%) nhạy nhất với tail latency: khi `MOCK_SLOW_RATE=0.03`, `avg` chỉ tăng `46.2 ms` (`189.5 → 235.7 ms`) nhưng `p99` nhảy vọt hơn 7 lần lên `1690.1 ms`; đến `MOCK_SLOW_RATE=0.1`, `avg` mới `392.5 ms` (trông vẫn < 500ms) nhưng `p95` đã vọt lên `1694.6 ms`. Vì **average che giấu nhóm user bị chậm**, SLO bắt buộc phải đặt theo percentile (`p95`/`p99`).

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

| Chỉ số | Agent v1 (`eval_v1.json`) | Agent v2 (`eval_v2.json`) | Agent v2 sau sửa KB (`eval_v2_fixed.json`) |
| --- | --- | --- | --- |
| Accuracy | 4.3% (1/23) | 91.3% (21/23) | 100.0% (23/23) |
| Avg tokens / câu | 56.7 | 109.1 | 113.7 |
| Tổng cost (USD) | $0.000398 | $0.000762 | $0.000790 |
| Cost / câu đúng (USD) | $0.00039795 | $0.00003627 | $0.00003436 |
| Quality gate | FAIL | PASS (`≥ 80%`, 0 regression) | PASS (`100%`, 0 regression) |

**Những câu v2 trả lời sai ban đầu và cách sửa:**

| ID | Keyword bị thiếu | Đã sửa gì |
| --- | --- | --- |
| `security-02` | `token`, `hết hạn`, `chữ ký` | Thêm entry `(["jwt"], ...)` vào `KNOWLEDGE_BASE` trong `develop/utils/mock_llm.py` (và đồng bộ sang `production/utils/mock_llm.py`) |
| `scaling-03` | `cpu`, `memory`, `custom metrics` | Thêm entry `(["hpa", "kubernetes", "autoscal"], ...)` vào `KNOWLEDGE_BASE` |

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2 & CI Quality Gate:**
- **Trade-off:** v2 thêm bước retrieval (RAG) nên prompt dài hơn — tốn gần gấp đôi token mỗi câu (`109.1–113.7` vs `56.7`) và latency cơ bản tăng nhẹ (~20ms retrieval), nhưng Accuracy tăng vọt từ `4.3% → 100%` và **cost / câu trả lời đúng rẻ hơn > 11 lần** (`$0.00003436` so với `$0.00039795`).
- **CI Quality Gate:** Đã tạo [.github/workflows/eval.yml](.github/workflows/eval.yml) chạy `python eval/run_eval.py --url http://localhost:8000 --min-accuracy 0.85` trên mỗi PR; khi test chạy `v1` với `--baseline reports/eval_v2.json`, lệnh trả **exit code `1`**, giúp GitHub Actions chặn merge tự động khi có regression.

---

## 4. Observability stack (production)

### 4.1 Screenshot
- [x] `screenshots/grafana-dashboard.png` (Dashboard Grafana khi đang có tải, thấy rõ 4 Golden Signals)
- [x] `screenshots/jaeger-slow-trace.png` (Trace chậm `1.7s`, span `chat mock-llm-small` chiếm 1.7s)
- [x] `screenshots/jaeger-error-trace.png` (Trace lỗi `503` với `error.type=upstream_unavailable` và event `exception`)
- [x] `screenshots/prometheus-alert-firing.png` (Trang `:9090/alerts` thấy 2 alert `LLMCostBurnRateHigh` và `AgentHighErrorRate` đang **FIRING**)

**Quan sát Dashboard & Prometheus (Exercise 7.4):**
- Lúc đang chạy tải trên stack: `p95 ≈ 741.7 ms`, `avg ≈ 286.0 ms` (chênh lệch ~2.6× phản ánh tail latency từ 3% request chậm).
- Lưu lượng `POST /ask` chia đều qua 2 instance từ Nginx round-robin (`22.47 req/s` và `21.06 req/s`).
- `input tokens/s` (`3335.8 tok/s`) lớn hơn `output tokens/s` (`1741.8 tok/s`) vì v2 nhúng thêm system prompt + tài liệu retrieval (RAG context) vào input prompt.
- `curl -i http://localhost:8080/metrics` trả **`404`**: trong `nginx/nginx.conf` có `location = /metrics { return 404; }` để chặn truy cập công khai, chỉ cho phép Prometheus scrape qua mạng nội bộ Docker.

### 4.2 Thí nghiệm "phá hệ thống" (Exercise 7.6)

*(Đơn vị test rule: `promtool test rules /p/alert_rules_test.yml` → **SUCCESS**).*

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
| --- | --- | --- | --- | --- |
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` | `70.1 s` | `Errors (5xx Rate)` & `LLM Calls OK vs Error` |
| B | `MOCK_SLOW_RATE=0.3` | `AgentHighLatencyP95` | `140.1 s` | `Latency (p50/p95/p99/avg)` |
| C | `LLM_MODEL=mock-llm-large` | `LLMCostBurnRateHigh` | `135.1 s` | `LLM Cost Burn Rate ($/h)` & `LLM p95` |
| D | `docker pause` 1 instance | `AgentInstanceDown` | `40.1 s` | `Instances UP` & `Requests/s theo instance` |
| E | `AGENT_VERSION=v1` | Không có alert mới nào từ v1 *(chỉ còn `LLMCostBurnRateHigh` tồn dư từ cửa sổ 5m của thí nghiệm C)* | N/A | `Retrieval Hit Ratio` tụt về 0% & bảng `Agent Info` |

**Thí nghiệm E không làm alert nào firing. Phát hiện sự cố chất lượng này trong production bằng cách nào?**
- Lỗi chất lượng (`v1` bỏ qua RAG hoặc prompt bị lỗi) không làm tăng `5xx`, không làm tăng latency hay chết container nên mọi alert hạ tầng đều xanh. Cần kết hợp: (1) chạy **eval CI quality gate** (`run_eval.py`) trước mỗi lần deploy, (2) giám sát các **domain metrics** như `retrieval_hit_ratio` (đặt alert nếu tụt dưới ngưỡng), và (3) thu thập feedback người dùng + chạy **LLM-as-a-judge / online eval** định kỳ trên mẫu traffic thật.
- *Ghi chú thí nghiệm D:* dùng `docker pause` giữ container trong DNS nhưng treo kết nối nên Prometheus thấy `up == 0` (`AgentInstanceDown`); trong lúc agent bị treo trước timeout, lỗi `504` phát sinh ở Nginx nên không lọt vào metric của agent — cần giám sát thêm ở tầng load balancer/synthetic check ngoài.

### 4.3 Debug bằng trace (Exercise 7.5)

Chọn 1 trace chậm điển hình từ Jaeger & log thật:

- `trace_id`: `3e3506905f2daa396ecd058f497ec03d`
- Tổng thời gian (`POST /ask`): `1719.03 ms` (`agent.run`: `1715.64 ms`, `agent.retrieve_context`: `15.18 ms`)
- Span chiếm nhiều thời gian nhất: `chat mock-llm-small` (`1700.09 ms`, chiếm **`98.9%`** tổng thời gian)
- Dòng log tương ứng (từ `docker compose -p k5-day14-observability logs agent`):

```json
{"ts": "2026-11-25T10:39:46.748854+00:00", "level": "INFO", "service": "observable-agent", "instance": "b4f68ec3dcf0", "event": "llm_call", "trace_id": "3e3506905f2daa396ecd058f497ec03d", "span_id": "01f75534387ba7ad", "request_id": "42b9009b1568", "model": "mock-llm-small", "agent_version": "v2", "input_tokens": 95, "output_tokens": 55, "cost_usd": 4.7e-05, "llm_ms": 1698.7}
```

*(Trace lỗi tham khảo trong Jaeger với tag `error=true`: `trace_id` = `975ee2b5da73f4caa65e95cb879922e1`, event `llm_error`: `Upstream LLM error: 503 Service Unavailable (mock)`).*

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

Số liệu `Aggregated` trích trực tiếp từ `benchmark-results/scale_1_stats.csv` và `benchmark-results/scale_3_stats.csv`:

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 (`scale_1_stats.csv`) | 60.53 *(POST /ask: 55.20)* | 200 | 1600 *(POST /ask: 1700)* | 2300 *(POST /ask: 2400)* | 66 / 7138 (0.92%) |
| 3 (`scale_3_stats.csv`) | 60.26 *(POST /ask: 54.88)* | 200 | 1600 *(POST /ask: 1700)* | 2200 *(POST /ask: 2300)* | 67 / 7156 (0.94%) |

**Giải thích kết quả:** Scale từ 1 lên 3 instance **không** làm giảm p95 (`~1600–1700 ms`) và RPS giữ nguyên (`~60 req/s`) vì hai nguyên nhân: (1) workload 100 Locust user có `wait_time = between(0.5, 2)` tạo ra ~60 req/s chưa chạm ngưỡng bão hòa của 1 async FastAPI worker, và (2) **nút thắt cổ chai nằm ở thời gian gọi LLM upstream** (`MOCK_SLOW_RATE=0.03` cộng thêm `1500 ms` vào các request đuôi chậm) — thêm replica chỉ tăng công suất xử lý đồng thời chứ không thể rút ngắn latency của từng lời gọi LLM.

---

## 6. Kết luận

- 3 điều học được về benchmark & observability:
  1. **Average đánh lừa, percentile (`p95`/`p99`) nói thật:** chỉ cần 3–10% request chậm là trải nghiệm tail user đã tệ gấp ~8 lần dù average vẫn trông bình thường.
  2. **Chất lượng ≠ Hạ tầng:** Prometheus/Grafana/Jaeger theo dõi sức khỏe hệ thống rất tốt nhưng không bắt được lỗi suy giảm trí tuệ/RAG của agent (`v1` vẫn toàn màu xanh) — bắt buộc phải có Eval + Quality Gate trong CI.
  3. **3 trụ cột liên kết qua `trace_id`:** Metrics báo có bất thường → Traces trong Jaeger chỉ đích danh span nghẽn (`chat mock-llm-small` chiếm 98.9%) → Log JSON theo `trace_id` cho biết payload và lỗi cụ thể.
- Nếu đưa agent lên production thật, sẽ bổ sung thêm:
  - Alert cho **Retrieval Hit Ratio thấp** và **Nginx 5xx / 504 rate** (để không bỏ sót lỗi timeout ngoài tầng proxy).
  - **Semantic / LLM-as-a-judge online eval** chạy mẫu trên traffic thật để phát hiện model drift/prompt regression.
