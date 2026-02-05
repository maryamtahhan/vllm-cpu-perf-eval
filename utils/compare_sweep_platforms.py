#!/usr/bin/env python3
"""
Compare sweep test performance curves between Intel Xeon and AMD EPYC platforms.

This script loads sweep test results from both platforms and creates side-by-side
comparisons showing how performance varies with load. Unlike the regular platform
comparison which shows only best runs, this reveals the full performance curves
and saturation behavior differences between architectures.

Usage:
    python3 compare_sweep_platforms.py [--intel-dir DIR] [--amd-dir DIR] [--output-dir DIR]

Arguments:
    --intel-dir     Path to Intel benchmark results (default: /Users/Xeon-multi-platform)
    --amd-dir       Path to AMD benchmark results (default: /Users/EPYC-multi-platform)
    --output-dir    Directory for output reports (default: benchmark_reports_sweep_comparison)
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


def create_platform_sweep_comparison(intel_df, amd_df, output_dir="benchmark_reports_sweep_comparison"):
    """Create sweep curve comparison plots between Intel and AMD."""
    Path(output_dir).mkdir(exist_ok=True)

    # Add platform labels
    intel_df = intel_df.copy()
    amd_df = amd_df.copy()
    intel_df['platform'] = 'Intel Xeon'
    amd_df['platform'] = 'AMD EPYC'

    # Platform colors
    colors = {'Intel Xeon': '#0071C5', 'AMD EPYC': '#ED1C24'}

    # Get common core counts for direct comparison
    intel_cores = set(intel_df['cores'].unique())
    amd_cores = set(amd_df['cores'].unique())
    common_cores = sorted(intel_cores & amd_cores)

    print(f"Intel core counts: {sorted(intel_cores)}")
    print(f"AMD core counts: {sorted(amd_cores)}")
    print(f"Common core counts for comparison: {common_cores}")

    # Metrics to compare
    metrics = [
        ('requests_sec_mean', 'throughput_tokens_sec_mean',
         'Load (Requests/sec)', 'Throughput (tokens/sec) ↑', True),
        ('requests_sec_mean', 'ttft_mean',
         'Load (Requests/sec)', 'TTFT (ms) ↓', False),
        ('requests_sec_mean', 'tpot_mean',
         'Load (Requests/sec)', 'TPOT (ms) ↓', False),
        ('requests_sec_mean', 'latency_mean',
         'Load (Requests/sec)', 'Latency (sec) ↓', False),
    ]

    # Create comparison for common core counts
    if common_cores:
        for cores in common_cores:
            intel_core_data = intel_df[intel_df['cores'] == cores].sort_values('requests_sec_mean')
            amd_core_data = amd_df[amd_df['cores'] == cores].sort_values('requests_sec_mean')

            fig, axes = plt.subplots(2, 2, figsize=(16, 12))
            fig.suptitle(f'Platform Comparison at {cores} Cores: Performance Curves',
                         fontsize=16, fontweight='bold')

            for idx, (ax, (x_col, y_col, xlabel, ylabel, higher_is_better)) in enumerate(zip(
                axes.flatten(), metrics
            )):
                # Plot Intel
                if len(intel_core_data) > 0:
                    ax.plot(intel_core_data[x_col], intel_core_data[y_col],
                           marker='o', linewidth=2, markersize=6,
                           label='Intel Xeon', color=colors['Intel Xeon'])

                # Plot AMD
                if len(amd_core_data) > 0:
                    ax.plot(amd_core_data[x_col], amd_core_data[y_col],
                           marker='s', linewidth=2, markersize=6,
                           label='AMD EPYC', color=colors['AMD EPYC'])

                ax.set_xlabel(xlabel, fontsize=11)
                ax.set_ylabel(ylabel, fontsize=11)
                ax.set_title(ylabel.replace(' ↑', '').replace(' ↓', ''), fontweight='bold')
                ax.legend(fontsize=10)
                ax.grid(True, alpha=0.3)

            plt.tight_layout()
            plt.savefig(f'{output_dir}/platform_sweep_comparison_{cores}c.png',
                       dpi=300, bbox_inches='tight')
            print(f"Saved platform_sweep_comparison_{cores}c.png")
            plt.close()

    # Create overall comparison showing all core counts on same plot
    for x_col, y_col, xlabel, ylabel, higher_is_better in metrics:
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
        fig.suptitle(f'Platform Sweep Comparison: {ylabel.replace(" ↑", "").replace(" ↓", "")}',
                     fontsize=16, fontweight='bold')

        # Left: Intel Xeon
        intel_cores_sorted = sorted(intel_df['cores'].unique())
        core_colors_intel = plt.cm.Blues(np.linspace(0.4, 0.9, len(intel_cores_sorted)))

        for idx, cores in enumerate(intel_cores_sorted):
            core_data = intel_df[intel_df['cores'] == cores].sort_values(x_col)
            if len(core_data) > 0:
                ax1.plot(core_data[x_col], core_data[y_col],
                        marker='o', linewidth=2, markersize=5,
                        label=f'{cores}c', color=core_colors_intel[idx])

        ax1.set_xlabel(xlabel, fontsize=11)
        ax1.set_ylabel(ylabel, fontsize=11)
        ax1.set_title('Intel Xeon', fontweight='bold', fontsize=12)
        ax1.legend(title='Cores', fontsize=9)
        ax1.grid(True, alpha=0.3)

        # Right: AMD EPYC
        amd_cores_sorted = sorted(amd_df['cores'].unique())
        core_colors_amd = plt.cm.Reds(np.linspace(0.4, 0.9, len(amd_cores_sorted)))

        for idx, cores in enumerate(amd_cores_sorted):
            core_data = amd_df[amd_df['cores'] == cores].sort_values(x_col)
            if len(core_data) > 0:
                ax2.plot(core_data[x_col], core_data[y_col],
                        marker='s', linewidth=2, markersize=5,
                        label=f'{cores}c', color=core_colors_amd[idx])

        ax2.set_xlabel(xlabel, fontsize=11)
        ax2.set_ylabel(ylabel, fontsize=11)
        ax2.set_title('AMD EPYC', fontweight='bold', fontsize=12)
        ax2.legend(title='Cores', fontsize=9)
        ax2.grid(True, alpha=0.3)

        plt.tight_layout()
        safe_ylabel = ylabel.replace('/', '_').replace(' ', '_').replace('(', '').replace(')', '').replace('↑', '').replace('↓', '')
        plt.savefig(f'{output_dir}/platform_sweep_{safe_ylabel.lower()}.png',
                   dpi=300, bbox_inches='tight')
        print(f"Saved platform_sweep_{safe_ylabel.lower()}.png")
        plt.close()


def create_saturation_comparison(intel_df, amd_df, output_dir="benchmark_reports_sweep_comparison"):
    """Compare saturation behavior between platforms."""
    Path(output_dir).mkdir(exist_ok=True)

    # Add platform labels
    intel_df = intel_df.copy()
    amd_df = amd_df.copy()
    intel_df['platform'] = 'Intel Xeon'
    amd_df['platform'] = 'AMD EPYC'

    # Get common cores
    common_cores = sorted(set(intel_df['cores'].unique()) & set(amd_df['cores'].unique()))

    if not common_cores:
        print("No common core counts for saturation comparison")
        return

    # Create saturation analysis
    if len(common_cores) == 1:
        fig, axes = plt.subplots(1, 2, figsize=(16, 6))
        axes = [axes]  # Make it a list of axis arrays for consistent indexing
    else:
        fig, axes = plt.subplots(len(common_cores), 2, figsize=(16, 6 * len(common_cores)))

    fig.suptitle('Platform Saturation Comparison: Throughput vs Load',
                 fontsize=16, fontweight='bold')

    colors = {'Intel Xeon': '#0071C5', 'AMD EPYC': '#ED1C24'}

    for idx, cores in enumerate(common_cores):
        intel_data = intel_df[intel_df['cores'] == cores].sort_values('requests_sec_mean')
        amd_data = amd_df[amd_df['cores'] == cores].sort_values('requests_sec_mean')

        # Left: Throughput vs Load
        ax_left = axes[idx][0]

        if len(intel_data) > 0:
            ax_left.plot(intel_data['requests_sec_mean'],
                        intel_data['throughput_tokens_sec_mean'],
                        marker='o', linewidth=2, markersize=6,
                        label='Intel Xeon', color=colors['Intel Xeon'])

        if len(amd_data) > 0:
            ax_left.plot(amd_data['requests_sec_mean'],
                        amd_data['throughput_tokens_sec_mean'],
                        marker='s', linewidth=2, markersize=6,
                        label='AMD EPYC', color=colors['AMD EPYC'])

        ax_left.set_xlabel('Load (Requests/sec)', fontsize=11)
        ax_left.set_ylabel('Throughput (tokens/sec)', fontsize=11)
        ax_left.set_title(f'{cores} Cores: Throughput vs Load', fontweight='bold')
        ax_left.legend()
        ax_left.grid(True, alpha=0.3)

        # Right: TTFT vs Load (showing latency degradation)
        ax_right = axes[idx][1]

        if len(intel_data) > 0:
            ax_right.plot(intel_data['requests_sec_mean'],
                         intel_data['ttft_mean'],
                         marker='o', linewidth=2, markersize=6,
                         label='Intel Xeon', color=colors['Intel Xeon'])

        if len(amd_data) > 0:
            ax_right.plot(amd_data['requests_sec_mean'],
                         amd_data['ttft_mean'],
                         marker='s', linewidth=2, markersize=6,
                         label='AMD EPYC', color=colors['AMD EPYC'])

        ax_right.set_xlabel('Load (Requests/sec)', fontsize=11)
        ax_right.set_ylabel('TTFT (ms)', fontsize=11)
        ax_right.set_title(f'{cores} Cores: TTFT vs Load', fontweight='bold')
        ax_right.legend()
        ax_right.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(f'{output_dir}/platform_saturation_comparison.png',
               dpi=300, bbox_inches='tight')
    print("Saved platform_saturation_comparison.png")
    plt.close()


def create_sweep_comparison_summary(intel_df, amd_df, output_dir="benchmark_reports_sweep_comparison"):
    """Create summary comparing sweep test characteristics."""
    Path(output_dir).mkdir(exist_ok=True)

    summary_data = []

    # Intel summary
    for cores in sorted(intel_df['cores'].unique()):
        core_data = intel_df[intel_df['cores'] == cores]
        summary_data.append({
            'Platform': 'Intel Xeon',
            'Cores': cores,
            'Num Points': len(core_data),
            'Load Range (req/s)': f"{core_data['requests_sec_mean'].min():.2f} - {core_data['requests_sec_mean'].max():.2f}",
            'Max Throughput (tok/s)': core_data['throughput_tokens_sec_mean'].max(),
            'TTFT Range (ms)': f"{core_data['ttft_mean'].min():.1f} - {core_data['ttft_mean'].max():.1f}",
        })

    # AMD summary
    for cores in sorted(amd_df['cores'].unique()):
        core_data = amd_df[amd_df['cores'] == cores]
        summary_data.append({
            'Platform': 'AMD EPYC',
            'Cores': cores,
            'Num Points': len(core_data),
            'Load Range (req/s)': f"{core_data['requests_sec_mean'].min():.2f} - {core_data['requests_sec_mean'].max():.2f}",
            'Max Throughput (tok/s)': core_data['throughput_tokens_sec_mean'].max(),
            'TTFT Range (ms)': f"{core_data['ttft_mean'].min():.1f} - {core_data['ttft_mean'].max():.1f}",
        })

    summary_df = pd.DataFrame(summary_data)
    summary_df = summary_df.sort_values(['Platform', 'Cores'])

    # Save to CSV
    summary_df.to_csv(f'{output_dir}/sweep_comparison_summary.csv', index=False)

    # Save to text
    with open(f'{output_dir}/sweep_comparison_summary.txt', 'w') as f:
        f.write("=" * 120 + "\n")
        f.write("Platform Sweep Comparison Summary\n")
        f.write("=" * 120 + "\n\n")
        f.write(summary_df.to_string(index=False))
        f.write("\n\n" + "=" * 120 + "\n")

    print("Saved sweep_comparison_summary.csv and sweep_comparison_summary.txt")

    return summary_df


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Compare Intel Xeon and AMD EPYC sweep test performance curves',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use default directories
  python3 compare_sweep_platforms.py

  # Specify custom directories
  python3 compare_sweep_platforms.py \\
    --intel-dir /path/to/intel --amd-dir /path/to/amd

  # Custom output directory
  python3 compare_sweep_platforms.py --output-dir my_sweep_comparison
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
        default='benchmark_reports_sweep_comparison',
        help='Directory for output reports (default: benchmark_reports_sweep_comparison)'
    )

    return parser.parse_args()


def main():
    """Main execution function."""
    args = parse_args()

    print("=" * 80)
    print("Platform Sweep Comparison: Intel Xeon vs AMD EPYC")
    print("=" * 80)
    print(f"Intel data directory: {args.intel_dir}")
    print(f"AMD data directory: {args.amd_dir}")
    print(f"Output directory: {args.output_dir}")

    print("\nLoading Intel Xeon sweep results...")
    try:
        intel_df = load_all_results(base_path=args.intel_dir)
        print(f"Loaded {len(intel_df)} Intel runs from {intel_df['test_name'].nunique()} tests")
        print(f"Intel core counts: {sorted(intel_df['cores'].unique())}")
    except Exception as e:
        print(f"\nError loading Intel results: {e}")
        sys.exit(1)

    print("\nLoading AMD EPYC sweep results...")
    try:
        amd_df = load_all_results(base_path=args.amd_dir)
        print(f"Loaded {len(amd_df)} AMD runs from {amd_df['test_name'].nunique()} tests")
        print(f"AMD core counts: {sorted(amd_df['cores'].unique())}")
    except Exception as e:
        print(f"\nError loading AMD results: {e}")
        sys.exit(1)

    print("\nCreating sweep curve comparisons...")
    create_platform_sweep_comparison(intel_df, amd_df, output_dir=args.output_dir)

    print("\nCreating saturation analysis...")
    create_saturation_comparison(intel_df, amd_df, output_dir=args.output_dir)

    print("\nGenerating comparison summary...")
    summary = create_sweep_comparison_summary(intel_df, amd_df, output_dir=args.output_dir)

    print("\n" + "=" * 80)
    print("Summary Preview:")
    print("=" * 80)
    print(summary.to_string(index=False))

    print("\n" + "=" * 80)
    print(f"Sweep comparison complete! Check the '{args.output_dir}' directory.")
    print("=" * 80)


if __name__ == "__main__":
    main()
