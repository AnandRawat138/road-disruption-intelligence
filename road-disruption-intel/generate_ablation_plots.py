import matplotlib.pyplot as plt
import numpy as np
import os

# Create results directory
os.makedirs('results/ablation', exist_ok=True)

# Data parsed from user ranges (midpoints) with corrected Full Framework baseline
configurations = [
    'Full Framework',
    '$-$ Temporal',
    '$-$ Evidence',
    '$-$ Geographic',
    '$-$ Contradiction',
    'Baseline'
]

# Midpoint values (Index 0 strictly aligned with E2E table)
event_f1 = [93.0, 89.0, 89.0, 91.0, 91.0, 86.0]
temporal_f1 = [91.0, 76.0, 86.5, 90.5, 88.0, 82.0]
location_f1 = [91.5, 91.0, 89.5, 65.0, 90.5, 84.5]
road_f1 = [87.5, 87.0, 85.5, 55.0, 86.5, 81.5]

# Deltas from Full Framework (Performance Degradation)
delta_event = [event_f1[0] - x for x in event_f1[1:]]
delta_temporal = [temporal_f1[0] - x for x in temporal_f1[1:]]
delta_location = [location_f1[0] - x for x in location_f1[1:]]
labels_ablation = configurations[1:]

plt.rcParams.update({
    'font.size': 10,
    'axes.labelsize': 10,
    'axes.titlesize': 11,
    'xtick.labelsize': 9,
    'ytick.labelsize': 9,
    'legend.fontsize': 9,
    'figure.dpi': 300,
    'font.family': 'serif',
    'axes.grid': True,
    'grid.alpha': 0.3
})

# ---------------------------------------------------------
# FIGURE E: Ablation Study Comparison
# ---------------------------------------------------------
x = np.arange(len(configurations))
width = 0.2

fig, ax = plt.subplots(figsize=(9, 4.5))

ax.bar(x - width*1.5, event_f1, width, label='Event F1', color='#4c72b0', edgecolor='black', linewidth=0.5)
ax.bar(x - width/2, temporal_f1, width, label='Temporal F1', color='#dd8452', edgecolor='black', linewidth=0.5)
ax.bar(x + width/2, location_f1, width, label='Location F1', color='#55a868', edgecolor='black', linewidth=0.5)
ax.bar(x + width*1.5, road_f1, width, label='Road Match F1', color='#c44e52', edgecolor='black', linewidth=0.5)

ax.set_ylabel('F1 Score (%)')
ax.set_title('Ablation Study: Component Impact on System Performance')
ax.set_xticks(x)
ax.set_xticklabels(configurations, rotation=15, ha='right')
ax.set_ylim(40, 100)
ax.legend(loc='lower left', ncol=4)

fig.tight_layout()
fig.savefig('results/ablation/fig_ablation_comparison.pdf', format='pdf', bbox_inches='tight')
fig.savefig('results/ablation/fig_ablation_comparison.png', format='png', bbox_inches='tight', dpi=300)
plt.close(fig)

# ---------------------------------------------------------
# FIGURE F: Component Contribution (Performance Degradation)
# ---------------------------------------------------------
x_deg = np.arange(len(labels_ablation))
width_deg = 0.25

fig, ax = plt.subplots(figsize=(7, 4.5))

ax.bar(x_deg - width_deg, delta_event, width_deg, label=r'$\Delta$ Event F1', color='#4c72b0', edgecolor='black', linewidth=0.5)
ax.bar(x_deg, delta_temporal, width_deg, label=r'$\Delta$ Temporal F1', color='#dd8452', edgecolor='black', linewidth=0.5)
ax.bar(x_deg + width_deg, delta_location, width_deg, label=r'$\Delta$ Location F1', color='#55a868', edgecolor='black', linewidth=0.5)

ax.set_ylabel('Absolute Performance Loss (%)')
ax.set_title('Performance Degradation upon Component Removal')
ax.set_xticks(x_deg)
ax.set_xticklabels(labels_ablation, rotation=15, ha='right')

# Highlight the massive drop from Geographic Matching on Location
for i, val in enumerate(delta_location):
    if val > 15:
        ax.annotate(f'-{val:.1f}%',
                    xy=(x_deg[i] + width_deg, val),
                    xytext=(0, 3), 
                    textcoords="offset points",
                    ha='center', va='bottom', fontsize=9, fontweight='bold', color='#c44e52')

ax.legend(loc='upper left')

fig.tight_layout()
fig.savefig('results/ablation/fig_component_contribution.pdf', format='pdf', bbox_inches='tight')
fig.savefig('results/ablation/fig_component_contribution.png', format='png', bbox_inches='tight', dpi=300)
plt.close(fig)

print("Corrected ablation plots successfully generated.")
