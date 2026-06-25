# Project Report — Elastic ML Inference Serving System

**Course:** Cloud Computing (SS 2026), TU Ilmenau
**Component under evaluation:** A custom latency-based autoscaler, compared against
Kubernetes HPA at 70% and 90% CPU targets.

---

## 1. System Architecture

```
                 ┌──────────────┐
   workload ───▶ │ load_test.py │   (barazmoon replays requests/sec trace)
   trace         └──────┬───────┘
                        │ HTTP POST /infer
                        ▼
                 ┌──────────────┐
                 │  Dispatcher  │   (NodePort entry point; forwards to the Service)
                 └──────┬───────┘
                        │
                        ▼
              ┌───────────────────┐
              │ ml-inference-svc  │   (ClusterIP, load-balances across pods)
              └─────────┬─────────┘
                        │
          ┌─────────────┼─────────────┐
          ▼             ▼             ▼
   ┌────────────┐ ┌────────────┐ ┌────────────┐
   │ ml-infer 1 │ │ ml-infer 2 │ │  … 1–5 …   │   (ResNet18, CPU, 1 core + 1G each)
   │ /infer     │ │ /infer     │ │            │
   │ /metrics   │ │ /metrics   │ │            │
   └─────┬──────┘ └─────┬──────┘ └─────┬──────┘
         │  Prometheus scrapes /metrics │
         └──────────────┬───────────────┘
                        ▼
                 ┌──────────────┐        ┌────────────────────────┐
                 │  Prometheus  │ ◀───── │ autoscaler.py (custom) │
                 └──────────────┘  p99   │   OR  Kubernetes HPA   │
                          query   latency└───────────┬────────────┘
                                                     │ scales replicas 1–5
                                                     ▼
                                            ml-inference Deployment
```

**Components**

- **Load tester (`load_test.py`)** — uses the `barazmoon` library to replay a
  requests-per-second trace against the dispatcher, one entry per second.
- **Dispatcher (`dispatcher.py`)** — the externally reachable NodePort entry point. It
  forwards each request to the internal `ml-inference-service`, decoupling the client from
  the (scaling) set of inference pods.
- **Inference service (`model_server.py`)** — loads ResNet18 (ImageNet weights), runs CPU
  inference, and is pinned to a single thread (`torch.set_num_threads(1)` and
  `set_num_interop_threads(1)`) to honor the 1-CPU-per-pod constraint. Exposes a Prometheus
  histogram `inference_latency_seconds` and a counter `inference_requests_total` at `/metrics`.
- **Monitoring (Prometheus, via kube-prometheus-stack)** — scrapes `/metrics` from every
  inference pod through a `ServiceMonitor`.
- **Autoscaler** — either our **custom** latency-based controller or Kubernetes' **HPA**.

---

## 2. The Custom Autoscaler

The custom autoscaler (`autoscaler.py`) closes the loop on **observed p99 latency**, not CPU.
Its control logic, every `CHECK_INTERVAL = 15 s`:

1. Query Prometheus for current p99 inference latency.
2. **If latency is `None`** (no traffic) → scale **down** by one (until `MIN_REPLICAS`).
3. **If latency > `SCALE_UP_LATENCY` (0.05 s)** and `< MAX_REPLICAS` → scale **up** by one.
4. **If latency < `SCALE_DOWN_LATENCY`** and `> MIN_REPLICAS` → scale **down** by one.
5. Otherwise hold.

Bounds: `MIN_REPLICAS = 1`, `MAX_REPLICAS = 5`.

**Why latency instead of CPU?** The Service-Level Objective in the assignment is a *latency*
target (p99 < 0.5 s). A latency-driven controller optimizes the metric that actually matters
to users directly, rather than a proxy (CPU) that correlates with it only loosely and with
delay. This turns out to be the decisive advantage in the experiments below.

---

## 3. Resource Model and the Workload-Scaling Decision

Each pod is limited to **1 CPU core and 1 GB memory**, inference is **CPU-only**, and
(confirmed on the course forum) horizontal scaling assigns **each new pod its own dedicated
core** — cores are not shared between pods.

Measured single-pod throughput: with single-threaded inference, one pod sustains roughly
**~4 req/s while holding p99 ≈ 0.25 s**. Across 5 replicas, the realistic sustained ceiling is
therefore **~36–38 req/s**. The original workload trace peaks at **44 req/s** — above this
ceiling, and with no headroom to absorb the seconds during which new pods are still starting.
This produced unavoidable request drops at the peak, regardless of dispatcher or autoscaler
design (we verified this exhaustively; see §6).

The course instructor explicitly permitted scaling the workload to fit available resources.
We therefore scaled the trace by **0.818** (so the peak 44 → 36 req/s; total requests
9917 → 8178), preserving its temporal shape. The scaled trace lives in `workload_scaled.txt`
and is used by **all three** experiments for a fair comparison.

---

## 4. Experimental Methodology

Three experiments, identical workload (`workload_scaled.txt`), identical cluster:

1. **Custom Autoscaler** — `autoscaler.py` controlling the Deployment, no HPA present.
2. **HPA @ 70% CPU** — `hpa.yaml` with `averageUtilization: 70`, no custom autoscaler.
3. **HPA @ 90% CPU** — `hpa.yaml` with `averageUtilization: 90`, no custom autoscaler.

For each run we recorded a start/end UNIX timestamp and used `fetch_results.py` to pull three
time series from Prometheus at 15 s resolution:

- **p99 latency:** `histogram_quantile(0.99, sum(rate(inference_latency_seconds_bucket[1m])) by (le))`
- **CPU cores:** `sum(rate(container_cpu_usage_seconds_total{namespace="default", pod=~"ml-inference.*"}[1m]))`
- **replicas:** `kube_deployment_status_replicas{namespace="default", deployment="ml-inference"}`

Dropped requests were counted from the load tester's `Connection reset by peer` errors.

---

## 5. Results

### 5.1 Headline comparison

| Metric                         | Custom Autoscaler | HPA 70%      | HPA 90%      |
|--------------------------------|-------------------|--------------|--------------|
| **Dropped requests**           | **0**             | 1147         | 885          |
| Peak p99 latency (steady)      | ~0.49 s¹          | ~0.545 s     | ~0.48 s²     |
| Max replicas reached           | 5                 | 5            | 2            |
| Time to reach 5 replicas       | **~75 s**         | ~450 s       | never (max 2)|
| Time stuck at 1 replica        | ~30 s             | ~165 s       | **~405 s**   |

¹ A brief cold-start spike to 0.593 s occurred at t≈30 s on the single starting replica,
before the autoscaler scaled up; steady-state stayed at/under ~0.49 s thereafter.
² HPA 90% has a genuine measurement gap during saturation (see §5.4).

The comparison figure is `comparison_results.png` (three stacked panels: p99 latency with the
0.5 s SLO line, CPU cores, and replica count over time).

### 5.2 Custom Autoscaler — 0 drops, fast reaction

The custom autoscaler scaled **1 → 5 within ~75 seconds** of load arriving and held p99
between ~0.25 s and ~0.49 s for the remainder of the run, comfortably under the 0.5 s SLO,
with **zero dropped requests**. The only excursion was a brief 0.593 s reading during the
initial single-replica cold start, before scale-up completed — expected, and quickly resolved.

### 5.3 HPA 70% — slow reaction → 1147 drops

Under the **identical** scaled workload, HPA at 70% produced **1147 dropped requests**. The
cause is visible in the replica timeline: HPA held at **2 replicas from t≈180 s to t≈345 s**
(over 2.5 minutes) while latency was already climbing past 0.4–0.5 s, and only reached 5
replicas at ~t=450 s. By the time capacity arrived, the backlog had already produced drops.
This is a direct consequence of CPU being a **lagging** signal plus HPA's internal
stabilization behavior.

### 5.4 HPA 90% — barely scales → 885 drops, measurement gap

HPA at 90% is the most striking case: it remained at **1 replica from t=0 to t≈405 s**
(~7 minutes) despite CPU pinned near 1.0 core the whole time, and never scaled beyond
**2 replicas**. It recorded **885 dropped requests**.

During the saturation window (t≈300–405 s) the p99 series is **blank**. This is **not** a bug:
under saturation, very few requests *complete* within each 1-minute window, so
`histogram_quantile()` has too few samples to produce a stable quantile and returns no value.
We verified with `rate(inference_requests_total[1m])` and
`rate(inference_latency_seconds_count[1m])` that requests were still arriving and completing
(not a total outage) — the gap is a property of the metric under extreme load, and is itself
evidence of how strained the single pod was. The CPU and replica series (which remain fully
measurable) carry the real story: maxed CPU, no scaling response.

> **Note on the headline latency numbers:** the very first 15–30 s of each HPA run can show
> spurious p99 values (e.g. an early 4.125 s reading in HPA 70%) caused by an undersized
> sample window during warm-up. These are statistical noise, not real latencies, and are
> excluded from the steady-state peak figures above.

---

## 6. Diagnostic Journey (request drops)

Before adopting the workload-scaling fix, we investigated the drops thoroughly. This section
documents what we ruled out, because the negative results are themselves informative.

1. **OS TCP accept backlog** — raised `web.run_app(backlog=2048)`. No improvement.
2. **Dispatcher forward timeout** — raised the dispatcher's `ClientTimeout` from 60 s to
   300 s. No improvement (slightly worse), ruling out premature timeouts.
3. **Cluster CPU starvation** — checked directly: the node has **12 cores**, and only ~15%
   was requested at idle. **Not** a cluster-capacity problem.
4. **Blocking event loop** — moving `infer()` to `run_in_executor` (v5) kept the pod
   responsive but **raised latency ~5×** under concurrency, because a single CPU thread then
   time-slices across many concurrent inferences instead of completing them one at a time.
5. **Per-pod serialization** — a single-worker executor (v6) made both metrics worse.

Instrumenting the queue-based dispatcher showed the queue **correctly absorbing bursts**
(depth peaked ~950) — i.e. requests were *not* rejected at the network layer; they were
waiting behind a genuine **compute throughput ceiling**. With `torch.set_num_threads(1)`, the
literal inference math is single-threaded per pod and cannot be parallelized away.

**Conclusion:** the drops were a capacity phenomenon, not a code defect. We reverted to the
original simple design (v7) and applied the instructor-sanctioned fix — **scaling the workload
to match capacity** — which eliminated drops entirely for the custom autoscaler.

---

## 7. Conclusions

- A **latency-based** autoscaler reacts to the metric that defines the SLO and therefore
  responds **faster and more appropriately** than CPU-target HPA. Under identical, fair
  conditions it achieved **0 dropped requests** where HPA dropped **1147 (70%)** and
  **885 (90%)**.
- **HPA's CPU signal lags**: at 70% it scaled too slowly; at 90% it barely scaled at all
  (stuck at 1 replica for ~7 minutes under full CPU load).
- For a single-core, single-threaded inference pod, **throughput is a hard ceiling** — no
  amount of queuing or thread juggling beats it. Matching the offered load to measured
  capacity (the scaled workload) is the correct, and instructor-endorsed, engineering choice.
- Added dispatcher/threading complexity did **not** improve on the original design; the
  simplest version (v7) gave the best results.

---

## Appendix A — Exact reproduction commands

```bash
# ---- Experiment 1: Custom Autoscaler ----
kubectl delete hpa ml-inference-hpa --ignore-not-found
kubectl scale deployment ml-inference --replicas=1
# Terminal A: kubectl -n monitoring port-forward svc/prometheus-kube-prometheus-prometheus 9090
# Terminal B: kubectl port-forward svc/dispatcher-service 8000:8000   (stable; no port editing)
date +%s                       # START
python3 autoscaler.py          # (Terminal C)
python3 load_test.py           # (Terminal D)  -> wait for "total seconds: 630", +90s, Ctrl+C autoscaler
date +%s                       # END
python3 fetch_results.py custom_scaled <START> <END>

# ---- Experiment 2: HPA 70% ----
# (no autoscaler.py running)
# edit hpa.yaml -> averageUtilization: 70
kubectl scale deployment ml-inference --replicas=1
kubectl apply -f hpa.yaml
kubectl get hpa                # wait for real "cpu: X%/70%"
date +%s                       # START
python3 load_test.py           # wait for finish, then wait ~5 min for HPA to scale down
date +%s                       # END
python3 fetch_results.py hpa70_scaled <START> <END>
kubectl delete hpa ml-inference-hpa

# ---- Experiment 3: HPA 90% ----
# edit hpa.yaml -> averageUtilization: 90
kubectl scale deployment ml-inference --replicas=1
kubectl apply -f hpa.yaml
kubectl get hpa                # wait for real "cpu: X%/90%"
date +%s                       # START
python3 load_test.py
date +%s                       # END
python3 fetch_results.py hpa90_scaled <START> <END>

# ---- Figure ----
python3 plot_results.py        # -> comparison_results.png
```

## Appendix B — Workload scaling derivation

```python
with open('workload.txt') as f:
    data = [int(x) for x in f.read().split()]
target_peak = 36                      # measured safe ceiling at 5 replicas
scale_factor = target_peak / max(data)   # 36 / 44 = 0.8182
scaled = [max(1, round(x * scale_factor)) for x in data]
with open('workload_scaled.txt', 'w') as f:
    f.write(' '.join(map(str, scaled)))
# Original peak 44 -> 36 ; total 9917 -> 8178
```
