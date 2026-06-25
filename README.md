# Elastic ML Inference Serving System

A Kubernetes-based, horizontally auto-scaling inference service for ResNet18 (CPU-only),
with a **custom latency-based autoscaler** benchmarked against Kubernetes' built-in
Horizontal Pod Autoscaler (HPA) at 70% and 90% CPU targets.

---

## ⚠️ READ THIS FIRST — Environment Requirements (non-negotiable)

This project was developed and tested **only** on the environment below. The load-testing
dependency (`barazmoon`) and the async networking stack are **Linux-only** and break on
Windows/PowerShell. **Do not attempt to run this on Windows directly.** If you are on
Windows, use **WSL2 + Ubuntu**, not PowerShell or CMD.

| Component            | Exact version used                          | Why it matters |
|----------------------|---------------------------------------------|----------------|
| OS                   | **Ubuntu 24.04** (under WSL2 on Windows 11) | `barazmoon` and `uvloop`-style async behavior are Linux-only |
| Python               | **3.11** (via a dedicated `venv`)           | `torch==2.3.0` wheels target 3.11; 3.12+ caused dependency conflicts for us |
| Docker               | Docker Desktop / Docker Engine 27+          | Image build + Minikube docker driver |
| Minikube             | **v1.38.1**                                 | Local single-node Kubernetes |
| Kubernetes           | **v1.35.1** (provisioned by Minikube)       | — |
| kubectl              | matching cluster version                    | — |
| Helm                 | v3.x                                        | Installs the Prometheus monitoring stack |
| Hardware (reference) | Intel i5-13420H (12 logical cores), 16 GB RAM | See "Hardware & Resource Configuration" below |

> **The #1 cause of "it doesn't run on my machine" is Python version + OS.**
> Use Ubuntu (or WSL2-Ubuntu) and Python 3.11 in a fresh virtual environment.
> Do **not** use the system Python, and do **not** use Windows PowerShell.

---

## Exact Python dependencies

Install these **exact** versions inside a Python 3.11 virtual environment. The
`torch`/`torchvision` packages **must** come from the PyTorch CPU index URL — the default
PyPI wheels pull CUDA builds that are large and will not work as intended on a CPU-only node.

```bash
python3.11 -m venv venv
source venv/bin/activate

pip install torch==2.3.0 torchvision==0.18.0 --index-url https://download.pytorch.org/whl/cpu
pip install aiohttp==3.9.5
pip install opencv-python-headless==4.10.0.84
pip install requests==2.32.3
pip install pillow==10.2.0
pip install numpy
pip install prometheus-client==0.21.0
pip install kubernetes

# Load tester (Linux only — this is the package that fails on Windows):
pip install git+https://github.com/reconfigurable-ml-pipeline/load_tester
```

A `requirements.txt` is included for convenience, but the `torch` CPU index URL and the
git-based `barazmoon` install must still be run manually as shown above (pip cannot encode
the custom index URL reliably for all setups).

> **Note on `opencv`:** we use `opencv-python-headless` (not `opencv-python`). The headless
> build avoids GUI/X11 system libraries that are absent on a server/WSL environment and were
> a source of import errors.

---

## Repository contents

| File | Role |
|------|------|
| `model_server.py`            | ML inference service (ResNet18, CPU). Exposes `/infer` and `/metrics`. |
| `dispatcher.py`              | Entry point that receives client load and forwards to the inference Service. |
| `client.py`                  | Single-request sanity-check client. |
| `load_test.py`               | Replays the workload trace against the dispatcher using `barazmoon`. |
| `autoscaler.py`              | **Custom** latency-based autoscaler (the contribution being evaluated). |
| `fetch_results.py`           | Pulls time-series (p99 latency, CPU cores, replicas) from Prometheus into CSV. |
| `plot_results.py`            | Produces `comparison_results.png` (the 3-panel comparison figure). |
| `Dockerfile`                 | Builds the `ml-inference` image. |
| `Dockerfile.dispatcher`      | Builds the `dispatcher` image. |
| `requirements.txt`           | Python dependency list (see caveats above). |
| `deployment.yaml`            | `ml-inference` Deployment (1 CPU + 1G memory request/limit per pod). |
| `service.yaml`               | `ml-inference-service` (ClusterIP) in front of the inference pods. |
| `dispatcher-deployment.yaml` | Dispatcher Deployment. |
| `dispatcher-service.yaml`    | Dispatcher Service (NodePort, the entry point for the load test). |
| `servicemonitor.yaml`        | Prometheus ServiceMonitor to scrape `/metrics`. |
| `hpa.yaml`                   | HorizontalPodAutoscaler definition (target editable: 70 / 90). |
| `workload.txt`               | Original professor-provided workload trace (requests/second per second). |
| `workload_scaled.txt`        | Workload scaled to 0.818× to match our cluster capacity (see report). |
| `results_*_scaled.csv`       | Final experiment data (custom / hpa70 / hpa90). |
| `comparison_results.png`     | Final comparison figure. |
| `REPORT.md`                  | Full write-up: design, experiments, analysis, and findings. |

---

## How to run — step by step

> Every command below assumes you are inside the activated `venv` and inside the project
> directory. **`eval $(minikube docker-env)` must be re-run in every new terminal** before
> building or referencing images, otherwise the build lands in the wrong Docker daemon and
> Kubernetes reports `ErrImageNeverPull`.

### 1. Start the cluster

```bash
minikube start --driver=docker
eval $(minikube docker-env)
```

### 2. Install the Prometheus monitoring stack (one-time)

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
helm install prometheus prometheus-community/kube-prometheus-stack --namespace monitoring --create-namespace
```

### 3. Build the images **inside Minikube's Docker**

```bash
eval $(minikube docker-env)      # REQUIRED in this terminal
docker build -t ml-inference:v7 -f Dockerfile .
docker build -t dispatcher:v7 -f Dockerfile.dispatcher .
```

> Image tags `:v7` are the **final** versions used for all reported results. See
> "Image Version History" below for what each prior tag changed and why.

### 4. Deploy everything

```bash
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml
kubectl apply -f dispatcher-deployment.yaml
kubectl apply -f dispatcher-service.yaml
kubectl apply -f servicemonitor.yaml
kubectl get pods            # wait until ml-inference + dispatcher are Running
```

### 5. Expose the dispatcher on a stable local port

The dispatcher Service is reached via a **fixed** `kubectl port-forward` so that
`client.py` and `load_test.py` never need editing. Run this in its own terminal and
**leave it running** for the whole session:

```bash
kubectl port-forward svc/dispatcher-service 8000:8000
```

`client.py` and `load_test.py` are hard-coded to `http://localhost:8000/infer`, which
this command always maps to the dispatcher — regardless of cluster restarts. No port
editing is ever required.

### 5b. Sanity check (single request)

```bash
python client.py
# Expected: a list of 5 ImageNet labels and a latency (~0.1s once warm,
#           the first request is slower due to cold start)
```

> **Why port-forward instead of `minikube service --url`?** On the Docker driver,
> `minikube service --url` opens a *new random* local port each time, which would force
> editing the endpoint in the code every session. The fixed `port-forward svc/dispatcher-service
> 8000:8000` gives a stable `localhost:8000` every time — the same pattern used for Prometheus
> (9090). This is the single most important step for painless reproduction.

### 6. Run an experiment

Open four terminals (all in the venv + project dir; run `eval $(minikube docker-env)` in each).

```bash
# Terminal A — Prometheus access (leave running)
kubectl --namespace monitoring port-forward svc/prometheus-kube-prometheus-prometheus 9090

# Terminal B — stable dispatcher access (leave running); no port editing needed
kubectl port-forward svc/dispatcher-service 8000:8000

# Terminal C — start the autoscaler under test, and record the start time
date +%s                # <-- note this as START
python3 autoscaler.py

# Terminal D — run the load test
python3 load_test.py
```

When the load test prints `total seconds: 630`, wait ~90 s for the system to scale back
down, then `Ctrl+C` the autoscaler and record the end time:

```bash
date +%s                # <-- note this as END
```

### 7. Collect results and plot

```bash
python3 fetch_results.py custom_scaled <START> <END>
# repeat for the HPA runs (see REPORT.md for the exact procedure)
python3 plot_results.py     # writes comparison_results.png
```

---

## Reproducing the HPA comparison runs

The custom autoscaler (`autoscaler.py`) and the HPA are **mutually exclusive** — only one may
control the `ml-inference` Deployment at a time. Always remove one before starting the other:

```bash
# For a custom-autoscaler run: ensure NO HPA exists
kubectl delete hpa ml-inference-hpa --ignore-not-found

# For an HPA run: do NOT run autoscaler.py; instead apply the HPA
#   (edit hpa.yaml: averageUtilization: 70  or  90)
kubectl apply -f hpa.yaml
kubectl get hpa            # wait until TARGETS shows a real "cpu: X%/70%" (not <unknown>)
```

Full step-by-step for all three experiments is in **`REPORT.md`**.

---

## Hardware & Resource Configuration (important context)

Per the assignment, **each inference pod requests and is limited to exactly 1 CPU core and
1 GB memory**, and inference runs on **CPU only**. We confirmed via the course forum that
this means horizontal scaling gives **each new pod its own separate, dedicated CPU core**
(cores are *not* shared between pods), and that memory similarly bounds how many pods can be
scheduled.

Our reference cluster (Minikube) was allocated:

- **CPU:** 12 cores (`kubectl describe node minikube` → `Capacity: cpu: 12`)
- **Memory:** ~7.8 GB (`memory: 7990364Ki`)

With `MAX_REPLICAS = 5`, peak demand is `5 × 1 CPU = 5 cores` plus the dispatcher and the
Prometheus stack — comfortably within 12 cores and ~7.8 GB.

### Why we scaled the workload (and why this is allowed)

The original trace peaks at **44 requests/second**. With single-threaded inference
(`torch.set_num_threads(1)`), each pod sustains roughly **~4 req/s at a p99 of ~0.25 s**, so
5 replicas give a real throughput ceiling near **36–38 req/s** — *below* the original 44 r/s
peak, with no margin for scale-up latency. This caused unavoidable request drops at peak.

The course instructor explicitly advised:

> *"If you face limitations with the number of pods, the best option is to scale down the
> request workload to a meaningful extent to match your resources, or you can also cluster
> your machines."*

Following this guidance, we generated **`workload_scaled.txt`** at scale factor **0.818**
(peak 44 → 36, total requests 9917 → 8178), which preserves the original trace's shape while
matching our measured capacity. With the scaled workload, the **custom autoscaler achieves
0 dropped requests**. All three reported experiments use this same scaled workload so the
comparison is fair.

---

## Image Version History (what changed and why)

We iterated through several image versions while diagnosing request-drop behavior. The
**final, reported configuration is `ml-inference:v7` + `dispatcher:v7`**, which corresponds to
the original, simplest design. Intermediate versions are documented here for transparency
(full reasoning in `REPORT.md`):

| Tag | Component | Change | Outcome |
|-----|-----------|--------|---------|
| v1–v4 | dispatcher | Added `asyncio.Queue`, raised OS `backlog`, tuned `NUM_WORKERS`, raised forward timeout | Queue absorbed bursts but did **not** reduce client-side drops; added complexity |
| v5 | ml-inference | `infer()` moved to `run_in_executor` (non-blocking event loop) | Reduced drops in isolation but **raised latency 5×** under concurrency |
| v6 | ml-inference | Single-worker `ThreadPoolExecutor` | Made both metrics worse |
| **v7** | **both** | **Reverted to the original simple design** | **Best result; chosen for final runs** |

**Key finding:** the added engineering did not beat the original design. The real fix was
**matching the workload to capacity** (the scaled workload), per the instructor's guidance —
not more dispatcher/threading machinery.

---

## Troubleshooting (lessons learned the hard way)

| Symptom | Cause | Fix |
|---------|-------|-----|
| `ErrImageNeverPull` | Image built in the host Docker, not Minikube's | Run `eval $(minikube docker-env)` **in that terminal**, rebuild |
| `Connection refused` to `localhost:9090` | Prometheus port-forward not running | Start the `kubectl port-forward` in a dedicated terminal |
| Load test all `Connection refused` | Dispatcher port-forward not running | Start `kubectl port-forward svc/dispatcher-service 8000:8000` in its own terminal |
| Autoscaler replicas flickering (3→2→3→2) | An HPA is also controlling the Deployment | `kubectl delete hpa ml-inference-hpa` before running `autoscaler.py` |
| `apiserver: Stopped` / `TLS handshake timeout` | Long heavy session exhausted the cluster | `minikube stop && minikube start --driver=docker` |
| Corrupted/short experiment data | Laptop went to **sleep** mid-run | Disable sleep before any 10-minute run |
| `barazmoon` won't install / import | Running on Windows/PowerShell or wrong Python | Use **WSL2-Ubuntu + Python 3.11**; install via the git URL above |

---

See **`REPORT.md`** for the full system design, experiment methodology, results, and analysis.
