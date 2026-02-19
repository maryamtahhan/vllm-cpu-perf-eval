#!/usr/bin/env python3
"""
Create a unified single-slide comparison of Xeon vs EPYC across all core counts.

This script generates a comprehensive single-page visualization showing all
performance metrics for both platforms across all core configurations.

Usage:
    python3 create_unified_comparison.py [--intel-dir DIR] [--amd-dir DIR] [--output-dir DIR]
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


def create_unified_comparison(intel_df, amd_df, output_dir="benchmark_reports_unified"):
    """Create a single comprehensive comparison slide."""
    Path(output_dir).mkdir(exist_ok=True)

    # Get max throughput run for each configuration
    intel_best = intel_df.loc[intel_df.groupby('test_name')['throughput_tokens_sec_mean'].idxmax()]
    amd_best = amd_df.loc[amd_df.groupby('test_name')['throughput_tokens_sec_mean'].idxmax()]

    # Platform colors
    colors = {'Intel Xeon': '#0071C5', 'AMD EPYC': '#ED1C24'}

    # Create figure with 2x3 grid
    fig, axes = plt.subplots(2, 3, figsize=(20, 12))
    fig.suptitle('Intel Xeon vs AMD EPYC: Performance Comparison Across All Core Counts',
                 fontsize=18, fontweight='bold', y=0.995)

    # Get sorted core counts
    all_cores = sorted(set(intel_best['cores'].unique()) | set(amd_best['cores'].unique()))
    x = np.arange(len(all_cores))
    width = 0.35

    # Metrics to plot: (column_name, title, ylabel, higher_is_better)
    metrics = [
        ('throughput_tokens_sec_mean', 'Throughput ↑', 'Tokens/sec', True),
        ('requests_sec_mean', 'Requests/sec ↑', 'Requests/sec', True),
        ('ttft_mean', 'Time to First Token ↓', 'TTFT (ms)', False),
        ('tpot_mean', 'Time per Output Token ↓', 'TPOT (ms)', False),
        ('latency_mean', 'Request Latency ↓', 'Latency (sec)', False),
    ]

    for idx, (metric_col, title, ylabel, higher_is_better) in enumerate(metrics):
        ax = axes[idx // 3, idx % 3]

        # Prepare data
        intel_values = []
        amd_values = []

        for cores in all_cores:
            intel_val = intel_best[intel_best['cores'] == cores][metric_col].values
            amd_val = amd_best[amd_best['cores'] == cores][metric_col].values

            intel_values.append(intel_val[0] if len(intel_val) > 0 else 0)
            amd_values.append(amd_val[0] if len(amd_val) > 0 else 0)

        # Plot bars
        bars1 = ax.bar(x - width/2, intel_values, width, label='Intel Xeon',
                       alpha=0.9, color=colors['Intel Xeon'], edgecolor='black', linewidth=0.5)
        bars2 = ax.bar(x + width/2, amd_values, width, label='AMD EPYC',
                       alpha=0.9, color=colors['AMD EPYC'], edgecolor='black', linewidth=0.5)

        # Add value labels on bars
        for bars in [bars1, bars2]:
            for bar in bars:
                height = bar.get_height()
                if height > 0:
                    ax.text(bar.get_x() + bar.get_width()/2., height,
                           f'{height:.1f}',
                           ha='center', va='bottom', fontsize=9, fontweight='bold')

        # Formatting
        ax.set_xlabel('Core Count', fontsize=11, fontweight='bold')
        ax.set_ylabel(ylabel, fontsize=11, fontweight='bold')
        ax.set_title(title, fontsize=13, fontweight='bold', pad=10)
        ax.set_xticks(x)
        ax.set_xticklabels([f'{cores}c' for cores in all_cores])
        ax.legend(loc='upper left', fontsize=10, framealpha=0.9)
        ax.grid(axis='y', alpha=0.3, linestyle='--')

        # Add percentage improvement labels for throughput
        if metric_col == 'throughput_tokens_sec_mean':
            for i, cores in enumerate(all_cores):
                if intel_values[i] > 0 and amd_values[i] > 0:
                    pct_diff = ((intel_values[i] - amd_values[i]) / amd_values[i]) * 100
                    color = colors['Intel Xeon'] if pct_diff > 0 else colors['AMD EPYC']
                    ax.text(x[i], max(intel_values[i], amd_values[i]) * 1.08,
                           f'{abs(pct_diff):.1f}%',
                           ha='center', va='bottom', fontsize=8,
                           color=color, fontweight='bold')

    # Create summary table in the 6th subplot
    ax_table = axes[1, 2]
    ax_table.axis('off')

    # Build summary data
    summary_data = []
    for cores in all_cores:
        intel_row = intel_best[intel_best['cores'] == cores]
        amd_row = amd_best[amd_best['cores'] == cores]

        if len(intel_row) > 0 and len(amd_row) > 0:
            intel_throughput = intel_row['throughput_tokens_sec_mean'].values[0]
            amd_throughput = amd_row['throughput_tokens_sec_mean'].values[0]
            advantage = "Xeon" if intel_throughput > amd_throughput else "EPYC"
            diff_pct = abs((intel_throughput - amd_throughput) / max(intel_throughput, amd_throughput)) * 100

            summary_data.append([
                f'{cores}c',
                f'{intel_throughput:.1f}',
                f'{amd_throughput:.1f}',
                f'{advantage}\n+{diff_pct:.1f}%'
            ])

    table = ax_table.table(cellText=summary_data,
                          colLabels=['Cores', 'Xeon\ntok/s', 'EPYC\ntok/s', 'Leader'],
                          cellLoc='center',
                          loc='center',
                          bbox=[0, 0.2, 1, 0.7])

    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 2.5)

    # Style header
    for i in range(4):
        table[(0, i)].set_facecolor('#404040')
        table[(0, i)].set_text_props(weight='bold', color='white')

    # Color code rows
    for i, row in enumerate(summary_data, 1):
        if 'Xeon' in row[3]:
            table[(i, 3)].set_facecolor('#B3D9FF')
        else:
            table[(i, 3)].set_facecolor('#FFB3B3')

    ax_table.set_title('Throughput Summary', fontsize=13, fontweight='bold', pad=20)

    plt.tight_layout(rect=[0, 0, 1, 0.99])

    # Save the unified comparison
    output_file = f'{output_dir}/unified_xeon_vs_epyc_comparison.png'
    plt.savefig(output_file, dpi=300, bbox_inches='tight', facecolor='white')
    print(f"Saved {output_file}")
    plt.close()


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Create unified single-slide comparison of Intel Xeon vs AMD EPYC',
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
    print("Creating Unified Platform Comparison")
    print("=" * 80)
    print(f"Intel data directory: {args.intel_dir}")
    print(f"AMD data directory: {args.amd_dir}")
    print(f"Output directory: {args.output_dir}")

    print("\nLoading Intel Xeon results...")
    try:
        intel_df = load_all_results(base_path=args.intel_dir)
        print(f"Loaded {len(intel_df)} Intel runs")
    except Exception as e:
        print(f"\nError loading Intel results: {e}")
        sys.exit(1)

    print("\nLoading AMD EPYC results...")
    try:
        amd_df = load_all_results(base_path=args.amd_dir)
        print(f"Loaded {len(amd_df)} AMD runs")
    except Exception as e:
        print(f"\nError loading AMD results: {e}")
        sys.exit(1)

    print("\nCreating unified comparison visualization...")
    create_unified_comparison(intel_df, amd_df, output_dir=args.output_dir)

    print("\n" + "=" * 80)
    print(f"Unified comparison complete! Check '{args.output_dir}' directory.")
    print("=" * 80)


if __name__ == "__main__":
    main()
