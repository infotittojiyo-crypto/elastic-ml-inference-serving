import csv
import matplotlib.pyplot as plt

def load_csv(filename):
    elapsed = []
    p99 = []
    cpu = []
    replicas = []
    with open(filename) as f:
        reader = csv.DictReader(f)
        for row in reader:
            elapsed.append(float(row["elapsed_seconds"]))
            p99.append(float(row["p99_latency"]) if row["p99_latency"] not in ("", "nan") else float("nan"))
            cpu.append(float(row["cpu_cores"]) if row["cpu_cores"] not in ("", "nan") else float("nan"))
            replicas.append(float(row["replicas"]) if row["replicas"] not in ("", "nan") else float("nan"))
    return elapsed, p99, cpu, replicas

experiments = [
    ("results_custom.csv", "Custom Autoscaler", "g", "o"),
    ("results_hpa70.csv", "HPA 70% CPU", "b", "s"),
    ("results_hpa90.csv", "HPA 90% CPU", "r", "^"),
]

fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 12))
fig.suptitle('Autoscaler Comparison: Custom vs Kubernetes HPA\n(Real data from Prometheus)', fontsize=14, fontweight='bold')

for filename, label, color, marker in experiments:
    elapsed, p99, cpu, replicas = load_csv(filename)

    ax1.plot(elapsed, p99, color=color, marker=marker, markersize=3,
              label=label, linewidth=1.5)

    ax2.plot(elapsed, cpu, color=color, marker=marker, markersize=3,
              label=label, linewidth=1.5)

    ax3.plot(elapsed, replicas, color=color, marker=marker, markersize=3,
              label=label, linewidth=1.5, drawstyle='steps-post')

# Plot 1: p99 latency
ax1.axhline(y=0.5, color='black', linestyle='--', linewidth=1.5, label='SLO (0.5s)')
ax1.set_xlabel('Time (seconds)')
ax1.set_ylabel('99th Percentile Latency (s)')
ax1.set_title('Service 99th Percentile Latency Over Time')
ax1.legend(loc='upper right')
ax1.grid(True, alpha=0.3)

# Plot 2: CPU cores used
ax2.set_xlabel('Time (seconds)')
ax2.set_ylabel('CPU Cores Used')
ax2.set_title('Total CPU Cores Consumed Over Time')
ax2.legend(loc='upper right')
ax2.grid(True, alpha=0.3)

# Plot 3: Replica count (bonus, helps explain the other two)
ax3.set_xlabel('Time (seconds)')
ax3.set_ylabel('Number of Replicas')
ax3.set_title('Replica Count Over Time')
ax3.legend(loc='upper right')
ax3.grid(True, alpha=0.3)
ax3.set_ylim(0, 6)

ax1.annotate('p99 latency unmeasurable here:\nservice saturated, too few\ncompletions per window',
             xy=(500, 0.27), xytext=(420, 0.08),
             fontsize=8, color='darkred',
             arrowprops=dict(arrowstyle='->', color='darkred', lw=1))

plt.tight_layout()
plt.savefig('comparison_results.png', dpi=150, bbox_inches='tight')
print("Saved comparison_results.png")

# Print summary stats for the report
print("\n=== SUMMARY ===")
for filename, label, _, _ in experiments:
    elapsed, p99, cpu, replicas = load_csv(filename)
    valid_p99 = [v for v in p99 if v == v]  # filters out NaN
    valid_cpu = [v for v in cpu if v == v]
    max_replicas = max([r for r in replicas if r == r], default=0)

    print(f"\n{label}:")
    ACTIVE_WINDOW = 650  # load test runs ~630s; ignore idle tail after this
    active_p99 = [p99[i] for i in range(len(elapsed)) if elapsed[i] <= ACTIVE_WINDOW]
    valid_active_p99 = [v for v in active_p99 if v == v]
    total_points = len(active_p99)
    valid_points = len(valid_active_p99)
    missing_pct = 100 * (1 - valid_points / total_points) if total_points else 0
    if missing_pct > 15:
        print(f"  Peak p99 latency: UNRELIABLE - {missing_pct:.0f}% of samples missing during active load")
        print(f"  (measured peak among available samples: {max(valid_active_p99):.3f}s, but likely understates true peak)" if valid_active_p99 else "  (no valid samples at all)")
    else:
        print(f"  Peak p99 latency: {max(valid_p99):.3f}s" if valid_p99 else "  Peak p99 latency: N/A (no valid samples)")
    print(f"  Peak CPU cores used: {max(valid_cpu):.3f}")
    print(f"  Max replicas reached: {int(max_replicas)}")
    print(f"  Duration: {elapsed[-1]:.0f}s")