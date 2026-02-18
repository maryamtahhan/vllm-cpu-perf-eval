#!/usr/bin/env python3
"""
Create unified sweep-based comparisons of Xeon vs EPYC across all core counts.

This script generates two types of visualizations:
1. Full sweep curves showing load vs performance metrics
2. Bar chart comparison at a consistent load point

Usage:
    python3 create_sweep_unified_comparison.py [--intel-dir DIR] [--amd-dir DIR] [--output-dir DIR]
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


def create_sweep_curves_unified(intel_df, amd_df, output_dir="benchmark_reports_unified"):
    """Create unified sweep curves showing all core counts on one slide."""
    Path(output_dir).mkdir(exist_ok=True)

    # Platform colors
    intel_color = '#0071C5'
    amd_color = '#ED1C24'

    # Get unique core counts
    all_cores = sorted(set(intel_df['cores'].unique()) | set(amd_df['cores'].unique()))

    # Core count line styles
    core_styles = {16: '-', 32: '--', 64: '-.', 96: ':'}
    core_markers = {16: 'o', 32: 's', 64: '^', 96: 'D'}

    # Create figure with 2x2 grid for main metrics
    fig, axes = plt.subplots(2, 2, figsize=(20, 14))
    fig.suptitle('Intel Xeon vs AMD EPYC: Full Sweep Curves Across All Core Counts',
                 fontsize=18, fontweight='bold', y=0.995)

    # Metrics to plot: (column_name, xlabel, ylabel, title)
    metrics = [
        ('throughput_tokens_sec_mean', 'Load (Requests/sec)', 'Throughput (tokens/sec)', 'Throughput vs Load ↑'),
        ('ttft_mean', 'Load (Requests/sec)', 'TTFT (ms)', 'Time to First Token vs Load ↓'),
        ('tpot_mean', 'Load (Requests/sec)', 'TPOT (ms)', 'Time per Output Token vs Load ↓'),
        ('latency_mean', 'Load (Requests/sec)', 'Latency (sec)', 'Request Latency vs Load ↓'),
    ]

    for idx, (metric_col, xlabel, ylabel, title) in enumerate(metrics):
        ax = axes[idx // 2, idx % 2]

        # Plot for each core count
        for cores in all_cores:
            # Intel data
            intel_core_data = intel_df[intel_df['cores'] == cores].sort_values('requests_sec_mean')
            if len(intel_core_data) > 0:
                ax.plot(intel_core_data['requests_sec_mean'],
                       intel_core_data[metric_col],
                       marker=core_markers.get(cores, 'o'),
                       linestyle=core_styles.get(cores, '-'),
                       linewidth=2.5,
                       markersize=7,
                       color=intel_color,
                       alpha=0.8,
                       label=f'Xeon {cores}c')

            # AMD data
            amd_core_data = amd_df[amd_df['cores'] == cores].sort_values('requests_sec_mean')
            if len(amd_core_data) > 0:
                ax.plot(amd_core_data['requests_sec_mean'],
                       amd_core_data[metric_col],
                       marker=core_markers.get(cores, 'o'),
                       linestyle=core_styles.get(cores, '-'),
                       linewidth=2.5,
                       markersize=7,
                       color=amd_color,
                       alpha=0.8,
                       label=f'EPYC {cores}c')

        ax.set_xlabel(xlabel, fontsize=12, fontweight='bold')
        ax.set_ylabel(ylabel, fontsize=12, fontweight='bold')
        ax.set_title(title, fontsize=14, fontweight='bold', pad=10)
        ax.legend(loc='best', fontsize=9, ncol=2, framealpha=0.95)
        ax.grid(True, alpha=0.3, linestyle='--')

    plt.tight_layout(rect=[0, 0, 1, 0.99])

    # Save the unified sweep curves
    output_file = f'{output_dir}/unified_sweep_curves_all_cores.png'
    plt.savefig(output_file, dpi=300, bbox_inches='tight', facecolor='white')
    print(f"Saved {output_file}")
    plt.close()


def find_consistent_load_point(intel_df, amd_df, target_load=1.5):
    """
    Find the closest data point to a target load for each configuration.
    Returns dataframes with one row per test (at the target load).
    """
    intel_at_load = []
    amd_at_load = []

    # Process each test
    for test_name in intel_df['test_name'].unique():
        test_data = intel_df[intel_df['test_name'] == test_name]
        # Find the run closest to target load
        closest_idx = (test_data['requests_sec_mean'] - target_load).abs().idxmin()
        intel_at_load.append(test_data.loc[closest_idx])

    for test_name in amd_df['test_name'].unique():
        test_data = amd_df[amd_df['test_name'] == test_name]
        # Find the run closest to target load
        closest_idx = (test_data['requests_sec_mean'] - target_load).abs().idxmin()
        amd_at_load.append(test_data.loc[closest_idx])

    intel_result = pd.DataFrame(intel_at_load)
    amd_result = pd.DataFrame(amd_at_load)

    return intel_result, amd_result


def create_consistent_load_comparison(intel_df, amd_df, output_dir="benchmark_reports_unified", target_load=1.5):
    """Create bar chart comparison at a consistent load point."""
    Path(output_dir).mkdir(exist_ok=True)

    # Get data at consistent load point
    intel_at_load, amd_at_load = find_consistent_load_point(intel_df, amd_df, target_load)

    # Platform colors
    colors = {'Intel Xeon': '#0071C5', 'AMD EPYC': '#ED1C24'}

    # Create figure with 2x3 grid
    fig, axes = plt.subplots(2, 3, figsize=(20, 12))
    fig.suptitle(f'Intel Xeon vs AMD EPYC at ~{target_load:.1f} req/s Load: Performance Comparison',
                 fontsize=18, fontweight='bold', y=0.995)

    # Get sorted core counts
    all_cores = sorted(set(intel_at_load['cores'].unique()) | set(amd_at_load['cores'].unique()))
    x = np.arange(len(all_cores))
    width = 0.35

    # Metrics to plot: (column_name, title, ylabel, higher_is_better)
    metrics = [
        ('throughput_tokens_sec_mean', 'Throughput ↑', 'Tokens/sec', True),
        ('requests_sec_mean', 'Actual Load', 'Requests/sec', True),
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
            intel_val = intel_at_load[intel_at_load['cores'] == cores][metric_col].values
            amd_val = amd_at_load[amd_at_load['cores'] == cores][metric_col].values

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
                    if pct_diff > 0:
                        color = colors['Intel Xeon']
                        label = f'+{pct_diff:.1f}%'
                    else:
                        color = colors['AMD EPYC']
                        label = f'{pct_diff:.1f}%'
                    ax.text(x[i], max(intel_values[i], amd_values[i]) * 1.08,
                           label,
                           ha='center', va='bottom', fontsize=8,
                           color=color, fontweight='bold')

    # Create summary table in the 6th subplot
    ax_table = axes[1, 2]
    ax_table.axis('off')

    # Build summary data
    summary_data = []
    for cores in all_cores:
        intel_row = intel_at_load[intel_at_load['cores'] == cores]
        amd_row = amd_at_load[amd_at_load['cores'] == cores]

        if len(intel_row) > 0 and len(amd_row) > 0:
            intel_throughput = intel_row['throughput_tokens_sec_mean'].values[0]
            amd_throughput = amd_row['throughput_tokens_sec_mean'].values[0]
            intel_ttft = intel_row['ttft_mean'].values[0]
            amd_ttft = amd_row['ttft_mean'].values[0]

            # Determine leader
            if intel_throughput > amd_throughput * 1.05:  # >5% better
                throughput_leader = "Xeon"
            elif amd_throughput > intel_throughput * 1.05:
                throughput_leader = "EPYC"
            else:
                throughput_leader = "~Tie"

            summary_data.append([
                f'{cores}c',
                f'{intel_throughput:.0f}',
                f'{amd_throughput:.0f}',
                f'{intel_ttft:.0f}',
                f'{amd_ttft:.0f}',
                throughput_leader
            ])

    table = ax_table.table(cellText=summary_data,
                          colLabels=['Cores', 'Xeon\nTok/s', 'EPYC\nTok/s',
                                    'Xeon\nTTFT', 'EPYC\nTTFT', 'Leader'],
                          cellLoc='center',
                          loc='center',
                          bbox=[0, 0.15, 1, 0.75])

    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1, 2.2)

    # Style header
    for i in range(6):
        table[(0, i)].set_facecolor('#404040')
        table[(0, i)].set_text_props(weight='bold', color='white')

    # Color code leader column
    for i, row in enumerate(summary_data, 1):
        if 'Xeon' in row[5]:
            table[(i, 5)].set_facecolor('#B3D9FF')
        elif 'EPYC' in row[5]:
            table[(i, 5)].set_facecolor('#FFB3B3')
        else:
            table[(i, 5)].set_facecolor('#E0E0E0')

    ax_table.set_title(f'Performance Summary at ~{target_load:.1f} req/s Load',
                      fontsize=13, fontweight='bold', pad=20)

    plt.tight_layout(rect=[0, 0, 1, 0.99])

    # Save the consistent load comparison
    output_file = f'{output_dir}/unified_consistent_load_{target_load:.1f}rps.png'
    plt.savefig(output_file, dpi=300, bbox_inches='tight', facecolor='white')
    print(f"Saved {output_file}")
    plt.close()


def print_load_summary(intel_df, amd_df):
    """Print summary of available load points."""
    print("\n" + "=" * 80)
    print("Available Load Points Summary")
    print("=" * 80)

    for platform_name, df in [("Intel Xeon", intel_df), ("AMD EPYC", amd_df)]:
        print(f"\n{platform_name}:")
        for test_name in sorted(df['test_name'].unique()):
            test_data = df[df['test_name'] == test_name]
            loads = sorted(test_data['requests_sec_mean'].values)
            print(f"  {test_name}: {len(loads)} points, "
                  f"range {loads[0]:.2f} - {loads[-1]:.2f} req/s")


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Create unified sweep-based comparisons of Intel Xeon vs AMD EPYC',
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

    parser.add_argument(
        '--target-load',
        type=float,
        default=1.5,
        help='Target load (req/s) for consistent load comparison (default: 1.5)'
    )

    return parser.parse_args()


def main():
    """Main execution function."""
    args = parse_args()

    print("=" * 80)
    print("Creating Unified Sweep-Based Platform Comparisons")
    print("=" * 80)
    print(f"Intel data directory: {args.intel_dir}")
    print(f"AMD data directory: {args.amd_dir}")
    print(f"Output directory: {args.output_dir}")
    print(f"Target load for consistent comparison: {args.target_load} req/s")

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

    # Print load summary
    print_load_summary(intel_df, amd_df)

    print("\n" + "=" * 80)
    print("Creating unified sweep curves visualization...")
    print("=" * 80)
    create_sweep_curves_unified(intel_df, amd_df, output_dir=args.output_dir)

    print("\n" + "=" * 80)
    print(f"Creating consistent load comparison at ~{args.target_load} req/s...")
    print("=" * 80)
    create_consistent_load_comparison(intel_df, amd_df,
                                     output_dir=args.output_dir,
                                     target_load=args.target_load)

    print("\n" + "=" * 80)
    print(f"Sweep-based comparisons complete! Check '{args.output_dir}' directory.")
    print("=" * 80)


if __name__ == "__main__":
    main()
