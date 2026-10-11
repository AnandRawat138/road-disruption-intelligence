import matplotlib.pyplot as plt
import numpy as np
import os

# Create results directory
os.makedirs('results/source_benchmark', exist_ok=True)

# Exact mean values from Table 2
sources = ['Google News', 'GDELT', 'News API', 'Reddit', 'Twitter']
rel_val = [65.0, 47.5, 62.5, 37.5, 55.0]
uni_val = [45.0, 50.0, 45.0, 35.0, 42.5]
dup_val = [22.5, 30.0, 22.5, 17.5, 25.0]
geo_val = [82.5, 91.5, 82.5, 65.0, 77.5]
vol_val = [4000, 10000, 4500, 3000, 3750]

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
# FIGURE C1: Source Effectiveness (Percentages - No Error Bars)
# ---------------------------------------------------------
x = np.arange(len(sources))
width = 0.2

fig, ax = plt.subplots(figsize=(8, 4.5))

ax.bar(x - width*1.5, rel_val, width, label='Relevant', color='#4c72b0', edgecolor='black', linewidth=0.5)
ax.bar(x - width/2, uni_val, width, label='Unique Event', color='#55a868', edgecolor='black', linewidth=0.5)
ax.bar(x + width/2, geo_val, width, label='Geo Coverage', color='#8172b3', edgecolor='black', linewidth=0.5)
ax.bar(x + width*1.5, dup_val, width, label='Duplicate', color='#c44e52', edgecolor='black', linewidth=0.5)

ax.set_ylabel('Percentage (%)')
ax.set_title('News Source Effectiveness and Quality (Mean Values)')
ax.set_xticks(x)
ax.set_xticklabels(sources, rotation=15, ha='right')
ax.set_ylim(0, 100)
ax.legend(loc='upper right', ncol=2)

fig.tight_layout()
fig.savefig('results/source_benchmark/fig_source_comparison_pct.pdf', format='pdf', bbox_inches='tight')
fig.savefig('results/source_benchmark/fig_source_comparison_pct.png', format='png', bbox_inches='tight', dpi=300)
plt.close(fig)

# ---------------------------------------------------------
# FIGURE C2: Source Volume (Articles - No Error Bars)
# ---------------------------------------------------------
fig, ax = plt.subplots(figsize=(6, 4))
bars = ax.bar(sources, vol_val, color='#64b5cd', edgecolor='black', linewidth=0.5, width=0.6)

ax.set_ylabel('Articles Retrieved')
ax.set_title('Average Acquisition Volume by Source')
ax.set_xticklabels(sources, rotation=15, ha='right')

# Format y-axis with comma separators
ax.get_yaxis().set_major_formatter(plt.FuncFormatter(lambda x, loc: "{:,}".format(int(x))))

# Add value labels on top of bars
for bar in bars:
    height = bar.get_height()
    ax.annotate(f'{int(height):,}',
                xy=(bar.get_x() + bar.get_width() / 2, height),
                xytext=(0, 3), 
                textcoords="offset points",
                ha='center', va='bottom', fontsize=9)

fig.tight_layout()
fig.savefig('results/source_benchmark/fig_source_volume.pdf', format='pdf', bbox_inches='tight')
fig.savefig('results/source_benchmark/fig_source_volume.png', format='png', bbox_inches='tight', dpi=300)
plt.close(fig)

print("Consistent source plots successfully generated.")
