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
SCALE_UP_LATENCY = 0.05   # scale up if latency > 50ms
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
            # No requests coming in - scale down
            if replicas > MIN_REPLICAS:
                print(f"No traffic. Scaling down...")
                scale(replicas - 1)
        elif latency > SCALE_UP_LATENCY and replicas < MAX_REPLICAS:
            print(f"High latency! Scaling up...")
            scale(replicas + 1)
        elif latency < SCALE_DOWN_LATENCY and replicas > MIN_REPLICAS:
            print(f"Low latency. Scaling down...")
            scale(replicas - 1)
        else:
            print("Latency OK, no scaling needed")
            
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    print("Autoscaler started!")
    autoscale()