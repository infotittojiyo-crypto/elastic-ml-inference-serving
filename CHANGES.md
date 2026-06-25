# CHANGES.md — All code modifications and rationale

This file documents every change made to the base code from the course handout
(`practical_HandsOn.md`), and **why**. It also provides ready-to-paste header comment
blocks for each source file so the reasoning lives alongside the code.

---

## Summary of changes vs. the handout base code

| File | Change from base | Why |
|------|------------------|-----|
| `model_server.py` | Added Prometheus `Histogram` (`inference_latency_seconds`) and `Counter` (`inference_requests_total`); added `/metrics` route | The autoscaler and the experiments need server-side p99 latency; Prometheus must be able to scrape it |
| `model_server.py` | Kept `torch.set_num_threads(1)` / `set_num_interop_threads(1)` | Required: each pod is limited to 1 CPU core |
| `model_server.py` | Final inference handler kept **synchronous** (base design) | After testing async variants (v5/v6) we reverted — the simple version gave the best latency+drops tradeoff |
| `dispatcher.py` | New component (not in handout) | Provides a single stable NodePort entry point in front of the scaling pod set |
| `dispatcher.py` | Final version is a simple pass-through forwarder | Queue/timeout/worker-count variants (v1–v6) did not reduce drops; reverted to simplest design |
| `autoscaler.py` | New component — custom latency-based controller | The contribution being evaluated |
| `load_test.py` | Reads workload from `workload_scaled.txt` | Scaled workload matches measured cluster capacity (instructor-approved) |
| `hpa.yaml` | `maxReplicas: 5`, target editable 70/90 | Matches the custom autoscaler's bound for a fair comparison |

---

## Why the workload was scaled (short version)

Single-threaded inference → ~4 req/s per pod at p99≈0.25s → ~36–38 req/s ceiling at 5
replicas. Original peak is 44 req/s, above the ceiling → unavoidable drops. Instructor
approved scaling the workload down to fit. Scale factor 0.818 (peak 44→36). See `REPORT.md`.

---

## Comment block to paste at the top of `model_server.py`

```python
# model_server.py — ResNet18 CPU inference service.
#
# Based on the course handout (practical_HandsOn.md), with these additions:
#   1. Prometheus instrumentation:
#        - Histogram inference_latency_seconds  (server-side latency; used for p99)
#        - Counter   inference_requests_total   (throughput / completion rate)
#        - a /metrics endpoint scraped by Prometheus via servicemonitor.yaml
#   2. torch.set_num_threads(1) and set_num_interop_threads(1) are REQUIRED:
#        each pod is limited to exactly 1 CPU core (assignment constraint).
#
# Design note: the inference handler is intentionally SYNCHRONOUS. We tested an
# async run_in_executor variant (image v5) and a single-worker executor (v6);
# both increased latency under load, so we reverted to this simple version (v7).
# Listens on port 8001 (/infer, /metrics).
```

## Comment block to paste at the top of `dispatcher.py`

```python
# dispatcher.py — stable NodePort entry point in front of the scaling pod set.
#
# Receives load from load_test.py and forwards each request to the internal
# ml-inference-service (ClusterIP), which load-balances across 1..5 pods.
#
# Design note: this is intentionally a SIMPLE pass-through. We tried queue-based
# variants (asyncio.Queue, backlog=2048, NUM_WORKERS tuning, longer ClientTimeout)
# in images v1..v6 to eliminate request drops. Instrumentation showed the queue
# absorbed bursts correctly (depth ~950) but drops persisted — they came from a
# genuine single-core compute ceiling, not the dispatcher. The simple version (v7)
# performed best and is the final one. Listens on port 8000.
```

## Comment block to paste at the top of `autoscaler.py`

```python
# autoscaler.py — custom latency-based autoscaler (the evaluated contribution).
#
# Every CHECK_INTERVAL (15s) it queries Prometheus for current p99 inference
# latency and adjusts the ml-inference Deployment's replica count between
# MIN_REPLICAS (1) and MAX_REPLICAS (5):
#   - latency is None (no traffic) -> scale down
#   - latency > SCALE_UP_LATENCY (0.05s) -> scale up by 1
#   - latency < SCALE_DOWN_LATENCY -> scale down by 1
#
# Rationale: the SLO is a LATENCY target (p99 < 0.5s), so we control on latency
# directly rather than on CPU (which HPA uses). This reacts faster and more
# appropriately — in our experiments it achieved 0 drops vs HPA's 1147 (70%) /
# 885 (90%) under the identical scaled workload.
#
# IMPORTANT: do not run this while an HPA controls the same Deployment — they will
# fight over the replica count. Run `kubectl delete hpa ml-inference-hpa` first.
```

## Comment block to paste near the workload load in `load_test.py`

```python
# Workload is read from workload_scaled.txt (peak 36 req/s), NOT the original
# workload.txt (peak 44 req/s). The original peak exceeds our cluster's measured
# throughput ceiling (~36-38 req/s at 5 single-core pods), which caused unavoidable
# drops. Per the instructor's guidance ("scale down the request workload to match
# your resources"), we scaled the trace by 0.818, preserving its shape. See REPORT.md.
with open("workload_scaled.txt") as f:
    workload = [int(x) for x in f.read().split()]
```
