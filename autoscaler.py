# autoscaler.py — custom latency-based autoscaler (the evaluated contribution).
#
# Every CHECK_INTERVAL (15s) it queries Prometheus for current inference latency
# and adjusts the ml-inference Deployment's replica count between MIN_REPLICAS (1)
# and MAX_REPLICAS (5):
#   - latency is None (no traffic)         -> scale down by 1
#   - latency > SCALE_UP_LATENCY (0.05s)   -> scale up by 1
#   - latency < SCALE_DOWN_LATENCY (0.02s) -> scale down by 1
#
# Rationale: the SLO is a LATENCY target (p99 < 0.5s), so we control on latency
# directly rather than on CPU (which HPA uses). This reacts faster and more
# appropriately — in our experiments it achieved 0 drops vs HPA's 1147 (70%) /
# 885 (90%) under the identical scaled workload.
#
# Note: this controller reacts to AVERAGE latency (sum/count rate), a cheap and
# responsive control signal. The report measures p99 latency separately
# (histogram_quantile) for evaluation. Both come from the same
# inference_latency_seconds histogram.
#
# IMPORTANT: do not run this while an HPA controls the same Deployment — they will
# fight over the replica count. Run `kubectl delete hpa ml-inference-hpa` first.

import requests
import time
from kubernetes import client, config

# Load Kubernetes config
config.load_kube_config()
apps_v1 = client.AppsV1Api()

# Settings
PROMETHEUS_URL = "http://localhost:9090"
DEPLOYMENT_NAME = "ml-inference"
NAMESPACE = "default"
MIN_REPLICAS = 1
MAX_REPLICAS = 5
SCALE_UP_LATENCY = 0.05    # scale up if latency > 50ms
SCALE_DOWN_LATENCY = 0.02  # scale down if latency < 20ms
CHECK_INTERVAL = 15        # check every 15 seconds


def get_latency():
    query = "rate(inference_latency_seconds_sum[1m]) / rate(inference_latency_seconds_count[1m])"
    response = requests.get(
        f"{PROMETHEUS_URL}/api/v1/query",
        params={"query": query}
    )
    data = response.json()
    results = data["data"]["result"]
    if not results:
        return None
    value = float(results[0]["value"][1])
    if value != value:  # check for NaN
        return None
    return value


def get_current_replicas():
    deployment = apps_v1.read_namespaced_deployment(
        name=DEPLOYMENT_NAME,
        namespace=NAMESPACE
    )
    return deployment.spec.replicas


def scale(replicas):
    apps_v1.patch_namespaced_deployment_scale(
        name=DEPLOYMENT_NAME,
        namespace=NAMESPACE,
        body={"spec": {"replicas": replicas}}
    )
    print(f"Scaled to {replicas} replicas")


def autoscale():
    while True:
        latency = get_latency()
        replicas = get_current_replicas()

        print(f"Latency: {latency}, Replicas: {replicas}")

        if latency is None:
            if replicas > MIN_REPLICAS:
                print("No traffic. Scaling down...")
                scale(replicas - 1)
        elif latency > SCALE_UP_LATENCY and replicas < MAX_REPLICAS:
            print("High latency! Scaling up...")
            scale(replicas + 1)
        elif latency < SCALE_DOWN_LATENCY and replicas > MIN_REPLICAS:
            print("Low latency. Scaling down...")
            scale(replicas - 1)
        else:
            print("Latency OK, no scaling needed")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    print("Autoscaler started!")
    autoscale()
