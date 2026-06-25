import requests
import sys
import csv

PROM_URL = "http://localhost:9090"

def query_range(query, start, end, step=15):
    resp = requests.get(f"{PROM_URL}/api/v1/query_range", params={
        "query": query, "start": start, "end": end, "step": step
    })
    data = resp.json()
    if data["status"] != "success":
        print("Query failed:", data)
        return []
    result = data["data"]["result"]
    if not result:
        return []
    return result[0]["values"]

def main():
    name = sys.argv[1]      # e.g. "custom_scaled", "hpa70_scaled", "hpa90_scaled"
    start = int(sys.argv[2])
    end = int(sys.argv[3])

    p99_query = 'histogram_quantile(0.99, sum(rate(inference_latency_seconds_bucket[1m])) by (le))'
    cpu_query = 'sum(rate(container_cpu_usage_seconds_total{namespace="default", pod=~"ml-inference.*"}[1m]))'
    replica_query = 'kube_deployment_status_replicas{namespace="default", deployment="ml-inference"}'

    p99_data = query_range(p99_query, start, end)
    cpu_data = query_range(cpu_query, start, end)
    replica_data = query_range(replica_query, start, end)

    p99_dict = {int(float(t)): float(v) for t, v in p99_data}
    cpu_dict = {int(float(t)): float(v) for t, v in cpu_data}
    replica_dict = {int(float(t)): float(v) for t, v in replica_data}

    all_ts = sorted(set(p99_dict) | set(cpu_dict) | set(replica_dict))
    if not all_ts:
        print("No data found! Check your time range and that Prometheus has data.")
        return

    filename = f"results_{name}.csv"
    t0 = all_ts[0]
    with open(filename, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "elapsed_seconds", "p99_latency", "cpu_cores", "replicas"])
        for ts in all_ts:
            writer.writerow([ts, ts - t0, p99_dict.get(ts, ""), cpu_dict.get(ts, ""), replica_dict.get(ts, "")])
    print(f"Saved {filename} with {len(all_ts)} data points")

if __name__ == "__main__":
    main()
