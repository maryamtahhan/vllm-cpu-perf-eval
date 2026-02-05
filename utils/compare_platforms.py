#!/usr/bin/env python3
"""
Compare performance between Intel Xeon and AMD EPYC platforms.

This script loads benchmark results from both Intel and AMD platforms and
creates comparison visualizations and tables.

Usage:
    python3 compare_platforms.py [--intel-dir DIR] [--amd-dir DIR] [--output-dir DIR]

Arguments:
    --intel-dir     Path to Intel benchmark results (default: /Users/Xeon-multi-platform)
    --amd-dir       Path to AMD benchmark results (default: /Users/EPYC-multi-platform)
    --output-dir    Directory for output reports (default: benchmark_reports_comparison)
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
plt.rcParams['figure.figsize'] = (14, 8)


def create_platform_comparison_plots(intel_df, amd_df, output_dir="benchmark_reports_comparison"):
    """Create comparison plots between Intel and AMD platforms.

    Note: This function selects ONLY the maximum throughput run from each test
    (highest load level with worst latency). This shows peak throughput but does not
    show latency tradeoffs or how performance varies with load. For full sweep curve
    comparison, use compare_sweep_platforms.py instead.
    """
    Path(output_dir).mkdir(exist_ok=True)

    # Get maximum throughput runs for each platform (highest throughput run from each test)
    # For sweep tests with multiple load levels, this selects only the highest load run
    intel_best = intel_df.loc[intel_df.groupby('test_name')['throughput_tokens_sec_mean'].idxmax()]
    amd_best = amd_df.loc[amd_df.groupby('test_name')['throughput_tokens_sec_mean'].idxmax()]

    # Add platform labels
    intel_best = intel_best.copy()
    amd_best = amd_best.copy()
    intel_best['platform'] = 'Intel Xeon'
    amd_best['platform'] = 'AMD EPYC'

    # Combine data
    combined = pd.concat([intel_best, amd_best], ignore_index=True)

    # Platform colors
    colors = {'Intel Xeon': '#0071C5', 'AMD EPYC': '#ED1C24'}

    # Metrics to compare: (mean_col, p95_col, title, ylabel, higher_is_better, show_p95)
    metrics = [
        ('requests_sec_mean', 'requests_sec_p95', 'Requests/Second ↑',
         'Requests per Second', True, False),
        ('throughput_tokens_sec_mean', 'throughput_tokens_sec_p95',
         'Throughput (tokens/sec) ↑', 'Tokens per Second', True, False),
        ('ttft_mean', 'ttft_p95', 'TTFT (ms) ↓',
         'Time to First Token (ms)', False, True),
        ('tpot_mean', 'tpot_p95', 'TPOT (ms) ↓',
         'Time per Output Token (ms)', False, True),
        ('latency_mean', 'latency_p95', 'Latency (sec) ↓',
         'Request Latency (seconds)', False, True),
    ]

    for mean_col, p95_col, metric_name, ylabel, higher_is_better, show_p95 in metrics:
        # Create figure with 1 or 2 subplots depending on whether we show P95
        if show_p95:
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
        else:
            fig, ax1 = plt.subplots(1, 1, figsize=(10, 6))

        # Left plot: Mean values
        for platform in ['Intel Xeon', 'AMD EPYC']:
            platform_data = combined[combined['platform'] == platform].sort_values('cores')
            ax1.plot(platform_data['cores'], platform_data[mean_col],
                    marker='o', linewidth=2, markersize=8,
                    label=platform, color=colors[platform])

            # Add value labels on points
            for _, row in platform_data.iterrows():
                ax1.annotate(f'{row[mean_col]:.1f}',
                           (row['cores'], row[mean_col]),
                           textcoords="offset points",
                           xytext=(0, 10), ha='center', fontsize=9)

        ax1.set_xlabel('Number of Cores', fontsize=12)
        ax1.set_ylabel(ylabel if not show_p95 else f'{ylabel} (Mean)', fontsize=12)
        ax1.set_title(metric_name if not show_p95 else f'{metric_name} - Mean',
                     fontsize=13, fontweight='bold')
        ax1.legend()
        ax1.grid(True, alpha=0.3)

        # Right plot: P95 values (only for latency metrics)
        if show_p95:
            for platform in ['Intel Xeon', 'AMD EPYC']:
                platform_data = combined[combined['platform'] == platform].sort_values('cores')
                ax2.plot(platform_data['cores'], platform_data[p95_col],
                        marker='o', linewidth=2, markersize=8,
                        label=platform, color=colors[platform])

                # Add value labels on points
                for _, row in platform_data.iterrows():
                    ax2.annotate(f'{row[p95_col]:.1f}',
                               (row['cores'], row[p95_col]),
                               textcoords="offset points",
                               xytext=(0, 10), ha='center', fontsize=9)

            ax2.set_xlabel('Number of Cores', fontsize=12)
            ax2.set_ylabel(f'{ylabel} (P95)', fontsize=12)
            ax2.set_title(f'{metric_name} - P95', fontsize=13, fontweight='bold')
            ax2.legend()
            ax2.grid(True, alpha=0.3)

        plt.tight_layout()
        plt.savefig(f'{output_dir}/{mean_col}_platform_comparison.png',
                   dpi=300, bbox_inches='tight')
        print(f"Saved {mean_col}_platform_comparison.png")
        plt.close()

    # Create combined overview
    fig, axes = plt.subplots(2, 3, figsize=(18, 10))
    fig.suptitle('Platform Comparison: Intel Xeon vs AMD EPYC (Mean Values)',
                 fontsize=16, fontweight='bold')

    for idx, (mean_col, p95_col, metric_name, ylabel, higher_is_better, show_p95) in enumerate(metrics):
        ax = axes[idx // 3, idx % 3]

        for platform in ['Intel Xeon', 'AMD EPYC']:
            platform_data = combined[combined['platform'] == platform].sort_values('cores')
            ax.plot(platform_data['cores'], platform_data[mean_col],
                   marker='o', linewidth=2, markersize=8,
                   label=platform, color=colors[platform])

        ax.set_xlabel('Cores')
        ax.set_ylabel(ylabel)
        ax.set_title(metric_name, fontweight='bold')
        ax.legend()
        ax.grid(True, alpha=0.3)

    # Hide the last empty subplot
    axes[1, 2].set_visible(False)

    plt.tight_layout()
    plt.savefig(f'{output_dir}/platform_comparison_overview.png',
               dpi=300, bbox_inches='tight')
    print("Saved platform_comparison_overview.png")
    plt.close()


def create_comparison_tables(intel_df, amd_df, output_dir="benchmark_reports_comparison"):
    """Create comparison summary tables.

    Note: This function selects ONLY the maximum throughput run from each test
    (highest load level with worst latency). For full sweep data showing all load
    levels, use compare_sweep_platforms.py.
    """
    Path(output_dir).mkdir(exist_ok=True)

    # Get maximum throughput runs (highest throughput run from each test)
    # For sweep tests, this excludes all other load level data points
    intel_best = intel_df.loc[intel_df.groupby('test_name')['throughput_tokens_sec_mean'].idxmax()]
    amd_best = amd_df.loc[amd_df.groupby('test_name')['throughput_tokens_sec_mean'].idxmax()]

    # Add platform labels
    intel_best = intel_best.copy()
    amd_best = amd_best.copy()
    intel_best['platform'] = 'Intel Xeon'
    amd_best['platform'] = 'AMD EPYC'

    # Combine data
    combined = pd.concat([intel_best, amd_best], ignore_index=True)

    # Create summary table
    summary = combined[['platform', 'cores', 'requests_sec_mean',
                        'throughput_tokens_sec_mean', 'ttft_mean',
                        'tpot_mean', 'latency_mean',
                        'successful_requests']].copy()

    summary.columns = ['Platform', 'Cores', 'Req/s (mean)',
                      'Throughput tok/s (mean)', 'TTFT ms (mean)',
                      'TPOT ms (mean)', 'Latency s (mean)', 'Successful Reqs']

    summary = summary.sort_values(['Platform', 'Cores'])

    # Save to CSV
    summary.to_csv(f'{output_dir}/platform_comparison_summary.csv',
                  index=False, float_format='%.2f')
    print("Saved platform_comparison_summary.csv")

    # Create formatted text table
    with open(f'{output_dir}/platform_comparison_summary.txt', 'w') as f:
        f.write("=" * 140 + "\n")
        f.write("Platform Performance Comparison: Intel Xeon vs AMD EPYC\n")
        f.write("=" * 140 + "\n\n")
        f.write(summary.to_string(index=False))
        f.write("\n\n" + "=" * 140 + "\n")

    print("Saved platform_comparison_summary.txt")

    # Create performance ratio analysis
    intel_pivot = intel_best.pivot_table(
        index='cores',
        values=['requests_sec_mean', 'throughput_tokens_sec_mean',
                'ttft_mean', 'tpot_mean', 'latency_mean'],
        aggfunc='first'
    )
    amd_pivot = amd_best.pivot_table(
        index='cores',
        values=['requests_sec_mean', 'throughput_tokens_sec_mean',
                'ttft_mean', 'tpot_mean', 'latency_mean'],
        aggfunc='first'
    )

    with open(f'{output_dir}/platform_comparison_analysis.txt', 'w') as f:
        f.write("=" * 80 + "\n")
        f.write("Platform Performance Analysis\n")
        f.write("=" * 80 + "\n\n")

        f.write("Intel Xeon Multi-Platform Performance:\n")
        f.write("-" * 80 + "\n")
        f.write(intel_pivot.to_string(float_format='%.2f'))
        f.write("\n\n")

        f.write("AMD EPYC Multi-Platform Performance:\n")
        f.write("-" * 80 + "\n")
        f.write(amd_pivot.to_string(float_format='%.2f'))
        f.write("\n\n")

        # Compare at common core counts
        common_cores = set(intel_best['cores'].unique()) & set(amd_best['cores'].unique())
        if common_cores:
            f.write("Performance Comparison at Common Core Counts:\n")
            f.write("-" * 80 + "\n")
            for cores in sorted(common_cores):
                intel_row = intel_best[intel_best['cores'] == cores].iloc[0]
                amd_row = amd_best[amd_best['cores'] == cores].iloc[0]

                f.write(f"\n{cores} Cores:\n")
                f.write(f"  Requests/sec:  Intel {intel_row['requests_sec_mean']:.2f} vs "
                       f"AMD {amd_row['requests_sec_mean']:.2f} "
                       f"({amd_row['requests_sec_mean']/intel_row['requests_sec_mean']:.2f}x)\n")
                f.write(f"  Throughput:    Intel {intel_row['throughput_tokens_sec_mean']:.2f} vs "
                       f"AMD {amd_row['throughput_tokens_sec_mean']:.2f} "
                       f"({amd_row['throughput_tokens_sec_mean']/intel_row['throughput_tokens_sec_mean']:.2f}x)\n")
                f.write(f"  TTFT (ms):     Intel {intel_row['ttft_mean']:.2f} vs "
                       f"AMD {amd_row['ttft_mean']:.2f} "
                       f"({intel_row['ttft_mean']/amd_row['ttft_mean']:.2f}x better for Intel)\n")

        f.write("\n" + "=" * 80 + "\n")

    print("Saved platform_comparison_analysis.txt")

    return summary


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Compare Intel Xeon and AMD EPYC platform performance',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use default directories
  python3 compare_platforms.py

  # Specify custom directories
  python3 compare_platforms.py --intel-dir /path/to/intel --amd-dir /path/to/amd

  # Specify custom output directory
  python3 compare_platforms.py --output-dir my_comparison
        """
    )

    parser.add_argument(
        '--intel-dir',
        default='/Users/Xeon-multi-platform',
        help='Path to Intel benchmark results (default: /Users/Xeon-multi-platform)'
    )

    parser.add_argument(
        '--amd-dir',
        default='/Users/EPYC-multi-platform',
        help='Path to AMD benchmark results (default: /Users/EPYC-multi-platform)'
    )

    parser.add_argument(
        '--output-dir',
        default='benchmark_reports_comparison',
        help='Directory for output reports (default: benchmark_reports_comparison)'
    )

    return parser.parse_args()


def main():
    """Main execution function."""
    args = parse_args()

    print("=" * 80)
    print("Platform Performance Comparison: Intel Xeon vs AMD EPYC")
    print("=" * 80)
    print(f"Intel data directory: {args.intel_dir}")
    print(f"AMD data directory: {args.amd_dir}")
    print(f"Output directory: {args.output_dir}")

    print("\nLoading Intel Xeon benchmark results...")
    try:
        intel_df = load_all_results(base_path=args.intel_dir)
        print(f"Loaded {len(intel_df)} Intel benchmark runs from "
              f"{intel_df['test_name'].nunique()} tests")
        print(f"Intel core counts: {sorted(intel_df['cores'].unique())}")
    except Exception as e:
        print(f"\nError loading Intel results: {e}")
        sys.exit(1)

    print("\nLoading AMD EPYC benchmark results...")
    try:
        amd_df = load_all_results(base_path=args.amd_dir)
        print(f"Loaded {len(amd_df)} AMD benchmark runs from "
              f"{amd_df['test_name'].nunique()} tests")
        print(f"AMD core counts: {sorted(amd_df['cores'].unique())}")
    except Exception as e:
        print(f"\nError loading AMD results: {e}")
        sys.exit(1)

    print("\nCreating comparison visualizations...")
    create_platform_comparison_plots(intel_df, amd_df, output_dir=args.output_dir)

    print("\nGenerating comparison tables and analysis...")
    summary = create_comparison_tables(intel_df, amd_df, output_dir=args.output_dir)

    print("\n" + "=" * 80)
    print("Summary Preview:")
    print("=" * 80)
    print(summary.to_string(index=False))

    print("\n" + "=" * 80)
    print(f"Comparison complete! Check the '{args.output_dir}' directory for outputs.")
    print("=" * 80)


if __name__ == "__main__":
    main()
