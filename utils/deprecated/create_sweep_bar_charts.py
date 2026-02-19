#!/usr/bin/env python3
"""
Create bar chart comparisons showing sweep scaling behavior per core count.

This script generates separate detailed charts for each core configuration,
showing Xeon vs EPYC performance at multiple load levels to demonstrate
how performance scales under increasing load.

Usage:
    python3 create_sweep_bar_charts.py [--intel-dir DIR] [--amd-dir DIR] [--output-dir DIR]
"""

import argparse
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
from pathlib import Path
import sys

# Import functions from the main analysis script
from analyze_benchmark_results import load_all_results

# Set style for better-looking plots
sns.set_style("whitegrid")


def get_load_level_data(df, test_name, num_points=4):
    """
    Get evenly distributed load points from a sweep test.
    Returns dataframe with num_points rows representing different load levels.
    """
    test_data = df[df['test_name'] == test_name].sort_values('requests_sec_mean')

    if len(test_data) < num_points:
        # If we don't have enough points, return what we have
        return test_data

    # Get evenly spaced indices
    indices = np.linspace(0, len(test_data) - 1, num_points, dtype=int)
    return test_data.iloc[indices].reset_index(drop=True)


def create_core_count_comparison(intel_df, amd_df, cores, output_dir="benchmark_reports_unified"):
    """Create detailed comparison chart for a specific core count."""
    Path(output_dir).mkdir(exist_ok=True)

    # Platform colors
    colors = {'Intel Xeon': '#0071C5', 'AMD EPYC': '#ED1C24'}

    # Find the test for this core count
    intel_test = intel_df[intel_df['cores'] == cores]['test_name'].unique()
    amd_test = amd_df[amd_df['cores'] == cores]['test_name'].unique()

    if len(intel_test) == 0 or len(amd_test) == 0:
        print(f"Warning: No data found for {cores} cores")
        return

    intel_test = intel_test[0]
    amd_test = amd_test[0]

    # Get load level data (4 evenly spaced points from each sweep)
    intel_loads = get_load_level_data(intel_df, intel_test, num_points=4)
    amd_loads = get_load_level_data(amd_df, amd_test, num_points=4)

    # Create figure with 2x2 grid for metrics
    fig, axes = plt.subplots(2, 2, figsize=(18, 12))
    fig.suptitle(f'{cores} Cores: Intel Xeon vs AMD EPYC Performance Scaling',
                 fontsize=18, fontweight='bold', y=0.995)

    # Metrics to plot
    metrics = [
        ('throughput_tokens_sec_mean', 'Throughput (tokens/sec) ↑', True),
        ('ttft_mean', 'Time to First Token (ms) ↓', False),
        ('tpot_mean', 'Time per Output Token (ms) ↓', False),
        ('latency_mean', 'Request Latency (sec) ↓', False),
    ]

    # Determine number of load points (use the minimum between the two platforms)
    num_loads = min(len(intel_loads), len(amd_loads))

    for idx, (metric_col, ylabel, higher_is_better) in enumerate(metrics):
        ax = axes[idx // 2, idx % 2]

        # Setup x-axis positions
        x = np.arange(num_loads)
        width = 0.35

        # Extract values for each platform
        intel_values = intel_loads[metric_col].values[:num_loads]
        amd_values = amd_loads[metric_col].values[:num_loads]
        intel_load_labels = intel_loads['requests_sec_mean'].values[:num_loads]
        amd_load_labels = amd_loads['requests_sec_mean'].values[:num_loads]

        # Create average load labels (since they might differ slightly)
        load_labels = [(i + a) / 2 for i, a in zip(intel_load_labels, amd_load_labels)]

        # Plot bars
        bars1 = ax.bar(x - width/2, intel_values, width, label='Intel Xeon',
                       alpha=0.9, color=colors['Intel Xeon'], edgecolor='black', linewidth=0.8)
        bars2 = ax.bar(x + width/2, amd_values, width, label='AMD EPYC',
                       alpha=0.9, color=colors['AMD EPYC'], edgecolor='black', linewidth=0.8)

        # Add value labels on bars
        for bars in [bars1, bars2]:
            for bar in bars:
                height = bar.get_height()
                if height > 0:
                    ax.text(bar.get_x() + bar.get_width()/2., height,
                           f'{height:.1f}',
                           ha='center', va='bottom', fontsize=10, fontweight='bold')

        # Add percentage difference labels
        if metric_col == 'throughput_tokens_sec_mean':
            for i in range(num_loads):
                if intel_values[i] > 0 and amd_values[i] > 0:
                    pct_diff = ((intel_values[i] - amd_values[i]) / amd_values[i]) * 100
                    if abs(pct_diff) > 2:  # Only show if difference is significant
                        color = colors['Intel Xeon'] if pct_diff > 0 else colors['AMD EPYC']
                        label = f'{pct_diff:+.0f}%'
                        ax.text(x[i], max(intel_values[i], amd_values[i]) * 1.05,
                               label, ha='center', va='bottom', fontsize=9,
                               color=color, fontweight='bold')

        # Formatting
        ax.set_xlabel('Load Level (Requests/sec)', fontsize=12, fontweight='bold')
        ax.set_ylabel(ylabel, fontsize=12, fontweight='bold')
        ax.set_title(ylabel.replace(' ↑', '').replace(' ↓', ''),
                    fontsize=14, fontweight='bold', pad=10)
        ax.set_xticks(x)
        ax.set_xticklabels([f'{load:.2f}' for load in load_labels], fontsize=10)
        ax.legend(loc='best', fontsize=11, framealpha=0.95)
        ax.grid(axis='y', alpha=0.3, linestyle='--')

        # Add trend arrow annotation
        if higher_is_better:
            if intel_values[-1] > intel_values[0]:
                arrow_text = "→ Scales up with load"
                arrow_color = 'green'
            else:
                arrow_text = "→ Degrades under load"
                arrow_color = 'orange'
        else:
            if intel_values[-1] > intel_values[0]:
                arrow_text = "→ Degrades under load"
                arrow_color = 'orange'
            else:
                arrow_text = "→ Improves with load"
                arrow_color = 'green'

        ax.annotate(arrow_text, xy=(0.02, 0.98), xycoords='axes fraction',
                   fontsize=9, style='italic', color=arrow_color,
                   verticalalignment='top', bbox=dict(boxstyle='round,pad=0.3',
                   facecolor='white', edgecolor=arrow_color, alpha=0.8))

    plt.tight_layout(rect=[0, 0, 1, 0.99])

    # Save the chart
    output_file = f'{output_dir}/sweep_scaling_{cores}c_comparison.png'
    plt.savefig(output_file, dpi=300, bbox_inches='tight', facecolor='white')
    print(f"Saved {output_file}")
    plt.close()


def create_summary_scaling_chart(intel_df, amd_df, output_dir="benchmark_reports_unified"):
    """Create a summary chart showing all core counts with low/high load comparison."""
    Path(output_dir).mkdir(exist_ok=True)

    # Platform colors
    colors = {'Intel Xeon': '#0071C5', 'AMD EPYC': '#ED1C24'}

    # Get all core counts
    all_cores = sorted(set(intel_df['cores'].unique()) | set(amd_df['cores'].unique()))

    # Create figure with 2x2 grid
    fig, axes = plt.subplots(2, 2, figsize=(20, 12))
    fig.suptitle('Performance Scaling Summary: Low Load vs High Load',
                 fontsize=18, fontweight='bold', y=0.995)

    # Metrics to plot
    metrics = [
        ('throughput_tokens_sec_mean', 'Throughput (tokens/sec) ↑', True),
        ('ttft_mean', 'Time to First Token (ms) ↓', False),
        ('tpot_mean', 'Time per Output Token (ms) ↓', False),
        ('latency_mean', 'Request Latency (sec) ↓', False),
    ]

    for idx, (metric_col, ylabel, higher_is_better) in enumerate(metrics):
        ax = axes[idx // 2, idx % 2]

        # Setup for grouped bars
        x = np.arange(len(all_cores))
        width = 0.2

        intel_low = []
        intel_high = []
        amd_low = []
        amd_high = []

        for cores in all_cores:
            # Get data for this core count
            intel_test = intel_df[intel_df['cores'] == cores]['test_name'].unique()
            amd_test = amd_df[amd_df['cores'] == cores]['test_name'].unique()

            if len(intel_test) > 0:
                intel_data = intel_df[intel_df['test_name'] == intel_test[0]].sort_values('requests_sec_mean')
                intel_low.append(intel_data[metric_col].iloc[0])
                intel_high.append(intel_data[metric_col].iloc[-1])
            else:
                intel_low.append(0)
                intel_high.append(0)

            if len(amd_test) > 0:
                amd_data = amd_df[amd_df['test_name'] == amd_test[0]].sort_values('requests_sec_mean')
                amd_low.append(amd_data[metric_col].iloc[0])
                amd_high.append(amd_data[metric_col].iloc[-1])
            else:
                amd_low.append(0)
                amd_high.append(0)

        # Plot bars
        ax.bar(x - 1.5*width, intel_low, width, label='Xeon (Low Load)',
               alpha=0.7, color=colors['Intel Xeon'], edgecolor='black', linewidth=0.5,
               hatch='//')
        ax.bar(x - 0.5*width, intel_high, width, label='Xeon (High Load)',
               alpha=0.95, color=colors['Intel Xeon'], edgecolor='black', linewidth=0.5)
        ax.bar(x + 0.5*width, amd_low, width, label='EPYC (Low Load)',
               alpha=0.7, color=colors['AMD EPYC'], edgecolor='black', linewidth=0.5,
               hatch='\\\\')
        ax.bar(x + 1.5*width, amd_high, width, label='EPYC (High Load)',
               alpha=0.95, color=colors['AMD EPYC'], edgecolor='black', linewidth=0.5)

        # Formatting
        ax.set_xlabel('Core Count', fontsize=12, fontweight='bold')
        ax.set_ylabel(ylabel, fontsize=12, fontweight='bold')
        ax.set_title(ylabel.replace(' ↑', '').replace(' ↓', ''),
                    fontsize=14, fontweight='bold', pad=10)
        ax.set_xticks(x)
        ax.set_xticklabels([f'{cores}c' for cores in all_cores])
        ax.legend(loc='best', fontsize=9, framealpha=0.95, ncol=2)
        ax.grid(axis='y', alpha=0.3, linestyle='--')

    plt.tight_layout(rect=[0, 0, 1, 0.99])

    # Save
    output_file = f'{output_dir}/sweep_scaling_summary_low_vs_high.png'
    plt.savefig(output_file, dpi=300, bbox_inches='tight', facecolor='white')
    print(f"Saved {output_file}")
    plt.close()


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Create bar chart comparisons showing sweep scaling per core count',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        '--intel-dir',
        default='/Users/summarization/xeon-multi-platform',
        help='Path to Intel benchmark results'
    )

    parser.add_argument(
        '--amd-dir',
        default='/Users/summarization/epyc-multi-platform-zendnn',
        help='Path to AMD benchmark results'
    )

    parser.add_argument(
        '--output-dir',
        default='benchmark_reports_unified',
        help='Directory for output reports'
    )

    return parser.parse_args()


def main():
    """Main execution function."""
    args = parse_args()

    print("=" * 80)
    print("Creating Sweep Scaling Bar Charts")
    print("=" * 80)
    print(f"Intel data directory: {args.intel_dir}")
    print(f"AMD data directory: {args.amd_dir}")
    print(f"Output directory: {args.output_dir}")

    print("\nLoading Intel Xeon results...")
    try:
        intel_df = load_all_results(base_path=args.intel_dir)
        print(f"Loaded {len(intel_df)} Intel runs from {intel_df['test_name'].nunique()} tests")
    except Exception as e:
        print(f"\nError loading Intel results: {e}")
        sys.exit(1)

    print("\nLoading AMD EPYC results...")
    try:
        amd_df = load_all_results(base_path=args.amd_dir)
        print(f"Loaded {len(amd_df)} AMD runs from {amd_df['test_name'].nunique()} tests")
    except Exception as e:
        print(f"\nError loading AMD results: {e}")
        sys.exit(1)

    # Get all core counts
    all_cores = sorted(set(intel_df['cores'].unique()) | set(amd_df['cores'].unique()))

    print(f"\nCreating detailed scaling charts for each core count...")
    print(f"Core counts: {all_cores}")

    for cores in all_cores:
        print(f"\n  Creating chart for {cores} cores...")
        create_core_count_comparison(intel_df, amd_df, cores, output_dir=args.output_dir)

    print(f"\nCreating summary low vs high load chart...")
    create_summary_scaling_chart(intel_df, amd_df, output_dir=args.output_dir)

    print("\n" + "=" * 80)
    print(f"Sweep scaling bar charts complete! Check '{args.output_dir}' directory.")
    print("=" * 80)
    print("\nGenerated files:")
    for cores in all_cores:
        print(f"  - sweep_scaling_{cores}c_comparison.png")
    print(f"  - sweep_scaling_summary_low_vs_high.png")


if __name__ == "__main__":
    main()
