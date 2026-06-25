# plot_results.py — builds comparison_results.png from the three result CSVs.
#
# The latency panel y-axis is capped at 0.7s so the steady-state behaviour around
# the 0.5s SLO line is readable. Two early HPA-70 samples (t=30s, t=45s) are
# warm-up artifacts of the histogram quantile over a tiny initial window
# (4.125s and 2.11s); they are real data but off-scale, so they are annotated
# explicitly rather than hidden. Blank/NaN p99 values during high load are
# expected: under saturation, too few requests complete per 1-minute window for
# histogram_quantile() to return a value (discussed in REPORT.md).

import csv
import matplotlib.pyplot as plt


def load_csv(filename):
    elapsed, p99, cpu, replicas = [], [], [], []
    with open(filename) as f:
        for row in csv.DictReader(f):
            elapsed.append(float(row["elapsed_seconds"]))
            p99.append(float(row["p99_latency"]) if row["p99_latency"] not in ("", "nan") else float("nan"))
            cpu.append(float(row["cpu_cores"]) if row["cpu_cores"] not in ("", "nan") else float("nan"))
            replicas.append(float(row["replicas"]) if row["replicas"] not in ("", "nan") else float("nan"))
    return elapsed, p99, cpu, replicas


experiments = [
    ("results_custom_scaled.csv", "Custom Autoscaler", "g", "o"),
    ("results_hpa70_scaled.csv", "HPA 70% CPU", "b", "s"),
    ("results_hpa90_scaled.csv", "HPA 90% CPU", "r", "^"),
]

LAT_CAP = 0.7  # y-axis cap for the latency panel (seconds)

fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 12))
fig.suptitle('Autoscaler Comparison: Custom vs Kubernetes HPA\n(Real data from Prometheus)',
             fontsize=14, fontweight='bold')

for filename, label, color, marker in experiments:
    elapsed, p99, cpu, replicas = load_csv(filename)
    ax1.plot(elapsed, p99, color=color, marker=marker, markersize=3, label=label, linewidth=1.5)
    ax2.plot(elapsed, cpu, color=color, marker=marker, markersize=3, label=label, linewidth=1.5)
    ax3.plot(elapsed, replicas, color=color, marker=marker, markersize=3, label=label,
             linewidth=1.5, drawstyle='steps-post')

# ---- Panel 1: p99 latency (capped + SLO line) ----
ax1.axhline(y=0.5, color='black', linestyle='--', linewidth=1.5, label='SLO (0.5s)')
ax1.set_ylim(0, LAT_CAP)
ax1.set_xlabel('Time (seconds)')
ax1.set_ylabel('99th Percentile Latency (s)')
ax1.set_title('Service 99th Percentile Latency Over Time (y-axis capped at 0.7s for clarity)')
ax1.legend(loc='upper right')
ax1.grid(True, alpha=0.3)

# Annotate the two off-scale HPA-70 warm-up samples (real data, but off-scale).
ax1.annotate('HPA 70% warm-up artifacts:\nt=30s -> 4.13s, t=45s -> 2.11s\n(off-scale; tiny initial sample window)',
             xy=(45, LAT_CAP - 0.02), xytext=(120, 0.6),
             fontsize=8, color='darkblue',
             arrowprops=dict(arrowstyle='->', color='darkblue', lw=1))

# Annotate the saturation gap (no measurable p99) around the high-load window.
ax1.annotate('p99 gap under saturation:\ntoo few completions per window\nto compute a quantile',
             xy=(330, 0.30), xytext=(330, 0.05),
             fontsize=8, color='darkred',
             arrowprops=dict(arrowstyle='->', color='darkred', lw=1))

# ---- Panel 2: CPU cores ----
ax2.set_xlabel('Time (seconds)')
ax2.set_ylabel('CPU Cores Used')
ax2.set_title('Total CPU Cores Consumed Over Time')
ax2.legend(loc='upper right')
ax2.grid(True, alpha=0.3)

# ---- Panel 3: replica count ----
ax3.set_xlabel('Time (seconds)')
ax3.set_ylabel('Number of Replicas')
ax3.set_title('Replica Count Over Time')
ax3.legend(loc='upper right')
ax3.grid(True, alpha=0.3)
ax3.set_ylim(0, 6)

plt.tight_layout()
plt.savefig('comparison_results.png', dpi=150, bbox_inches='tight')
print("Saved comparison_results.png")

# ---- Summary (steady-state, ignoring first 45s warm-up) ----
print("\n=== SUMMARY (steady-state, ignoring first 60s warm-up) ===")
for filename, label, _, _ in experiments:
    elapsed, p99, cpu, replicas = load_csv(filename)
    steady = [p99[i] for i in range(len(elapsed)) if elapsed[i] >= 60 and p99[i] == p99[i]]
    valid_cpu = [v for v in cpu if v == v]
    max_replicas = max([r for r in replicas if r == r], default=0)
    print(f"\n{label}:")
    if steady:
        print(f"  Steady-state peak p99 latency: {max(steady):.3f}s")
    else:
        print("  Steady-state peak p99 latency: N/A")
    print(f"  Peak CPU cores used: {max(valid_cpu):.3f}")
    print(f"  Max replicas reached: {int(max_replicas)}")
    print(f"  Duration: {elapsed[-1]:.0f}s")
