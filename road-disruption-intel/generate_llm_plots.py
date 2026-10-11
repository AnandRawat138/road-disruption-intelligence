import matplotlib.pyplot as plt
import numpy as np
import os

# Create results directory if it doesn't exist
os.makedirs('results/llm_benchmark', exist_ok=True)

# Data
models = ['Llama 3 70B', 'Gemma 3 27B', 'Qwen3 30B', 'GPT-OSS 120B', 'DeepSeek-R1 70B']
event_f1 = [94, 93, 95, 96, 97]
temporal_f1 = [90, 89, 92, 94, 96]
location_f1 = [93, 92, 94, 97, 96]
overall_f1 = [93, 92, 94, 96, 96]
latency = [4.0, 2.5, 2.8, 6.0, 15.0]

# Elsevier style formatting guidelines (often Times New Roman or similar, 1-column or 2-column width)
plt.rcParams.update({
    'font.size': 10,
    'axes.labelsize': 10,
    'axes.titlesize': 11,
    'xtick.labelsize': 9,
    'ytick.labelsize': 9,
    'legend.fontsize': 9,
    'figure.figsize': (7, 4), # Good for two-column span or large single column
    'figure.dpi': 300,
    'font.family': 'serif',
    'axes.grid': True,
    'grid.alpha': 0.3
})

# ---------------------------------------------------------
# FIGURE A: LLM Performance Comparison
# ---------------------------------------------------------
x = np.arange(len(models))
width = 0.2

fig, ax = plt.subplots(figsize=(7, 4))
rects1 = ax.bar(x - width*1.5, event_f1, width, label='Event F1', color='#4c72b0', edgecolor='black', linewidth=0.5)
rects2 = ax.bar(x - width/2, temporal_f1, width, label='Temporal F1', color='#dd8452', edgecolor='black', linewidth=0.5)
rects3 = ax.bar(x + width/2, location_f1, width, label='Location F1', color='#55a868', edgecolor='black', linewidth=0.5)
rects4 = ax.bar(x + width*1.5, overall_f1, width, label='Overall F1', color='#c44e52', edgecolor='black', linewidth=0.5)

ax.set_ylabel('F1 Score (%)')
ax.set_title('LLM Semantic Extraction Performance')
ax.set_xticks(x)
ax.set_xticklabels(models, rotation=15, ha='right')
ax.set_ylim(85, 100) # Truncated axis but starting at 85 to show distinct variations
ax.legend(loc='lower right', ncol=2)

fig.tight_layout()
fig.savefig('results/llm_benchmark/fig_llm_comparison.pdf', format='pdf', bbox_inches='tight')
fig.savefig('results/llm_benchmark/fig_llm_comparison.png', format='png', bbox_inches='tight', dpi=300)
plt.close(fig)

# ---------------------------------------------------------
# FIGURE B: LLM Efficiency Comparison
# ---------------------------------------------------------
fig, ax = plt.subplots(figsize=(5, 4))
bars = ax.bar(models, latency, color='#8172b3', edgecolor='black', linewidth=0.5, width=0.6)

ax.set_ylabel('Latency (Seconds / Article)')
ax.set_title('LLM Inference Efficiency')
ax.set_xticklabels(models, rotation=25, ha='right')

# Add value labels on top of bars
for bar in bars:
    height = bar.get_height()
    ax.annotate(f'{height} s',
                xy=(bar.get_x() + bar.get_width() / 2, height),
                xytext=(0, 3),  # 3 points vertical offset
                textcoords="offset points",
                ha='center', va='bottom')

fig.tight_layout()
fig.savefig('results/llm_benchmark/fig_llm_efficiency.pdf', format='pdf', bbox_inches='tight')
fig.savefig('results/llm_benchmark/fig_llm_efficiency.png', format='png', bbox_inches='tight', dpi=300)
plt.close(fig)

print("Plots successfully generated in results/llm_benchmark/")
