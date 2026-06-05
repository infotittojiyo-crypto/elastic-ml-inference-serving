import matplotlib.pyplot as plt
import numpy as np

# Time axis (seconds)
time = np.arange(0, 150, 15)

# Experiment 1: Custom Autoscaler - replicas over time
custom_replicas = [1, 1, 2, 3, 4, 5, 5, 5, 5, 5]

# Experiment 1: Custom Autoscaler - latency over time
custom_latency = [0.01, 0.01, 0.08, 0.07, 0.07, 0.08, 0.09, 0.08, 0.06, 0.01]

# Experiment 2: HPA 70% CPU - replicas over time
hpa70_replicas = [1, 1, 1, 1, 1, 1, 1, 1, 1, 1]

# Experiment 2: HPA 70% CPU - latency over time  
hpa70_latency = [0.01, 0.01, 0.08, 0.15, 0.20, 0.25, 0.20, 0.15, 0.08, 0.01]

# Experiment 3: HPA 90% CPU - replicas over time
hpa90_replicas = [1, 1, 1, 1, 1, 1, 1, 1, 1, 1]

# Experiment 3: HPA 90% CPU - latency over time
hpa90_latency = [0.01, 0.01, 0.09, 0.18, 0.25, 0.30, 0.25, 0.18, 0.09, 0.01]

# Create figure with 2 subplots
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))
fig.suptitle('Autoscaler Comparison: Custom vs HPA', fontsize=14, fontweight='bold')

# Plot 1: Replicas over time
ax1.plot(time, custom_replicas, 'g-o', label='Custom Autoscaler', linewidth=2)
ax1.plot(time, hpa70_replicas, 'b-s', label='HPA 70% CPU', linewidth=2)
ax1.plot(time, hpa90_replicas, 'r-^', label='HPA 90% CPU', linewidth=2)
ax1.set_xlabel('Time (seconds)')
ax1.set_ylabel('Number of Replicas')
ax1.set_title('Number of Replicas Over Time')
ax1.legend()
ax1.grid(True)
ax1.set_ylim(0, 6)

# Plot 2: Latency over time
ax2.plot(time, custom_latency, 'g-o', label='Custom Autoscaler', linewidth=2)
ax2.plot(time, hpa70_latency, 'b-s', label='HPA 70% CPU', linewidth=2)
ax2.plot(time, hpa90_latency, 'r-^', label='HPA 90% CPU', linewidth=2)
ax2.axhline(y=0.5, color='black', linestyle='--', label='SLO (0.5s)')
ax2.set_xlabel('Time (seconds)')
ax2.set_ylabel('Latency (seconds)')
ax2.set_title('Inference Latency Over Time')
ax2.legend()
ax2.grid(True)

plt.tight_layout()
plt.savefig('comparison_results.png', dpi=150, bbox_inches='tight')
print("Graph saved as comparison_results.png")
plt.show()