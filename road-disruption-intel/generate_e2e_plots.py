import matplotlib.pyplot as plt
import numpy as np
import os

# Create results directory
os.makedirs('results/end_to_end', exist_ok=True)

# Data parsed from user ranges (midpoints)
metrics = [
    'Relevant Article Detection',
    'Event Extraction F1',
    'Temporal F1',
    'Location F1',
    'Road Matching F1',
    'Valid Structured Output',
    'Duplicate Suppression',
    'Contradiction Detection',
    'Successful Processing',
    'Overall End-to-End Event F1'
]

# (Min + Max) / 2
values = [
    (80 + 93) / 2,   # 86.5
    (90 + 96) / 2,   # 93.0
    (87 + 95) / 2,   # 91.0
    (88 + 95) / 2,   # 91.5
    (82 + 93) / 2,   # 87.5
    (97 + 99.5) / 2, # 98.25 -> 98.3
    (80 + 95) / 2,   # 87.5
    (75 + 90) / 2,   # 82.5
    (90 + 98) / 2,   # 94.0
    (88 + 95) / 2    # 91.5
]

# Round to 1 decimal place for display
values = [round(v, 1) for v in values]

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
# FIGURE H: End-to-End Performance
# ---------------------------------------------------------
fig, ax = plt.subplots(figsize=(8, 5))

# Use horizontal bars for readability of long labels
y_pos = np.arange(len(metrics))
# Reverse the order so the first metric is at the top
y_pos = y_pos[::-1]

bars = ax.barh(y_pos, values, color='#4c72b0', edgecolor='black', linewidth=0.5, height=0.6)

ax.set_xlabel('Performance Metric (%)')
ax.set_title('End-to-End Pipeline Evaluation')
ax.set_yticks(y_pos)
ax.set_yticklabels(metrics)
ax.set_xlim(70, 100) # Start x-axis at 70 to highlight differences

# Add value labels at the end of each bar
for i, bar in enumerate(bars):
    width = bar.get_width()
    ax.annotate(f'{width:.1f}%',
                xy=(width, bar.get_y() + bar.get_height() / 2),
                xytext=(5, 0),  # 5 points horizontal offset
                textcoords="offset points",
                ha='left', va='center', fontsize=9)

fig.tight_layout()
fig.savefig('results/end_to_end/fig_end_to_end.pdf', format='pdf', bbox_inches='tight')
fig.savefig('results/end_to_end/fig_end_to_end.png', format='png', bbox_inches='tight', dpi=300)
plt.close(fig)

print("End-to-end plots successfully generated.")
