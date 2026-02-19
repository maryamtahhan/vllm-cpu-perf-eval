#!/usr/bin/env python3
"""
Compare sweep test performance curves between two platforms.

This script loads sweep test results from two platforms and creates side-by-side
comparisons showing how performance varies with load. Unlike the regular platform
comparison which shows only best runs, this reveals the full performance curves
and saturation behavior differences between architectures.

Usage:
    python3 compare_sweep_platforms.py [--intel-dir DIR] [--amd-dir DIR] [--output-dir DIR] \\
        [--platform1-label LABEL] [--platform2-label LABEL] \\
        [--platform1-color COLOR] [--platform2-color COLOR]

Arguments:
    --intel-dir         Path to first platform benchmark results
    --amd-dir           Path to second platform benchmark results
    --output-dir        Directory for output reports
    --platform1-label   Label for first platform (e.g., "Intel Xeon", "EPYC ZenDNN")
    --platform2-label   Label for second platform (e.g., "AMD EPYC", "EPYC vLLM")
    --platform1-color   Hex color for first platform (default: #0071C5)
    --platform2-color   Hex color for second platform (default: #ED1C24)
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


def create_platform_sweep_comparison(intel_df, amd_df, output_dir="benchmark_reports_sweep_comparison",
                                     platform1_label="Intel Xeon", platform2_label="AMD EPYC",
                                     platform1_color='#0071C5', platform2_color='#ED1C24'):
    """Create sweep curve comparison plots between two platforms."""
    Path(output_dir).mkdir(exist_ok=True)

    # Add platform labels
    intel_df = intel_df.copy()
    amd_df = amd_df.copy()
    intel_df['platform'] = platform1_label
    amd_df['platform'] = platform2_label

    # Platform colors
    colors = {platform1_label: platform1_color, platform2_label: platform2_color}

    # Get common core counts for direct comparison
    intel_cores = set(intel_df['cores'].unique())
    amd_cores = set(amd_df['cores'].unique())
    common_cores = sorted(intel_cores & amd_cores)

    print(f"{platform1_label} core counts: {sorted(intel_cores)}")
    print(f"{platform2_label} core counts: {sorted(amd_cores)}")
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
                # Plot Platform 1
                if len(intel_core_data) > 0:
                    ax.plot(intel_core_data[x_col], intel_core_data[y_col],
                           marker='o', linewidth=2, markersize=6,
                           label=platform1_label, color=colors[platform1_label])

                # Plot Platform 2
                if len(amd_core_data) > 0:
                    ax.plot(amd_core_data[x_col], amd_core_data[y_col],
                           marker='s', linewidth=2, markersize=6,
                           label=platform2_label, color=colors[platform2_label])

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
        ax1.set_title(platform1_label, fontweight='bold', fontsize=12)
        ax1.legend(title='Cores', fontsize=9)
        ax1.grid(True, alpha=0.3)

        # Right: Platform 2
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
        ax2.set_title(platform2_label, fontweight='bold', fontsize=12)
        ax2.legend(title='Cores', fontsize=9)
        ax2.grid(True, alpha=0.3)

        plt.tight_layout()
        safe_ylabel = ylabel.replace('/', '_').replace(' ', '_').replace('(', '').replace(')', '').replace('↑', '').replace('↓', '')
        plt.savefig(f'{output_dir}/platform_sweep_{safe_ylabel.lower()}.png',
                   dpi=300, bbox_inches='tight')
        print(f"Saved platform_sweep_{safe_ylabel.lower()}.png")
        plt.close()


def create_saturation_comparison(intel_df, amd_df, output_dir="benchmark_reports_sweep_comparison",
                                platform1_label="Intel Xeon", platform2_label="AMD EPYC",
                                platform1_color='#0071C5', platform2_color='#ED1C24'):
    """Compare saturation behavior between platforms."""
    Path(output_dir).mkdir(exist_ok=True)

    # Add platform labels
    intel_df = intel_df.copy()
    amd_df = amd_df.copy()
    intel_df['platform'] = platform1_label
    amd_df['platform'] = platform2_label

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

    colors = {platform1_label: platform1_color, platform2_label: platform2_color}

    for idx, cores in enumerate(common_cores):
        intel_data = intel_df[intel_df['cores'] == cores].sort_values('requests_sec_mean')
        amd_data = amd_df[amd_df['cores'] == cores].sort_values('requests_sec_mean')

        # Left: Throughput vs Load
        ax_left = axes[idx][0]

        if len(intel_data) > 0:
            ax_left.plot(intel_data['requests_sec_mean'],
                        intel_data['throughput_tokens_sec_mean'],
                        marker='o', linewidth=2, markersize=6,
                        label=platform1_label, color=colors[platform1_label])

        if len(amd_data) > 0:
            ax_left.plot(amd_data['requests_sec_mean'],
                        amd_data['throughput_tokens_sec_mean'],
                        marker='s', linewidth=2, markersize=6,
                        label=platform2_label, color=colors[platform2_label])

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
                         label=platform1_label, color=colors[platform1_label])

        if len(amd_data) > 0:
            ax_right.plot(amd_data['requests_sec_mean'],
                         amd_data['ttft_mean'],
                         marker='s', linewidth=2, markersize=6,
                         label=platform2_label, color=colors[platform2_label])

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


def create_high_level_metrics_summary(intel_df, amd_df, output_dir="benchmark_reports_sweep_comparison",
                                     platform1_label="Intel Xeon", platform2_label="AMD EPYC",
                                     platform1_color='#0071C5', platform2_color='#ED1C24'):
    """Create high-level metrics summary table with all key performance indicators."""
    Path(output_dir).mkdir(exist_ok=True)

    # Get common core counts
    common_cores = sorted(set(intel_df['cores'].unique()) & set(amd_df['cores'].unique()))

    if not common_cores:
        print("No common core counts for metrics summary")
        return

    # Collect metrics for each platform
    summary_data = []

    for cores in common_cores:
        # Platform 1
        p1_data = intel_df[intel_df['cores'] == cores].copy()
        if len(p1_data) > 0:
            # Select best run: high throughput with low latency
            # Filter to runs with >= 95% of max throughput
            max_throughput = p1_data['throughput_tokens_sec_mean'].max()
            threshold = max_throughput * 0.95
            top_throughput_runs = p1_data[p1_data['throughput_tokens_sec_mean'] >= threshold]

            # Among those, pick the one with lowest latency
            if len(top_throughput_runs) > 0:
                best_run = top_throughput_runs.loc[top_throughput_runs['latency_mean'].idxmin()]
            else:
                # Fallback to max throughput if filtering fails
                best_run = p1_data.loc[p1_data['throughput_tokens_sec_mean'].idxmax()]

            # ITL is often the same as TPOT or can be calculated
            itl_value = best_run.get('itl_mean', best_run['tpot_mean'])

            summary_data.append({
                'Platform': platform1_label,
                'Cores': cores,
                'Throughput (tok/s)': best_run['throughput_tokens_sec_mean'],
                'TTFT (ms)': best_run['ttft_mean'],
                'TPOT (ms)': best_run['tpot_mean'],
                'ITL (ms)': itl_value,
                'Latency (s)': best_run['latency_mean'],
            })

        # Platform 2
        p2_data = amd_df[amd_df['cores'] == cores].copy()
        if len(p2_data) > 0:
            # Select best run: high throughput with low latency
            # Filter to runs with >= 95% of max throughput
            max_throughput = p2_data['throughput_tokens_sec_mean'].max()
            threshold = max_throughput * 0.95
            top_throughput_runs = p2_data[p2_data['throughput_tokens_sec_mean'] >= threshold]

            # Among those, pick the one with lowest latency
            if len(top_throughput_runs) > 0:
                best_run = top_throughput_runs.loc[top_throughput_runs['latency_mean'].idxmin()]
            else:
                # Fallback to max throughput if filtering fails
                best_run = p2_data.loc[p2_data['throughput_tokens_sec_mean'].idxmax()]

            # ITL is often the same as TPOT or can be calculated
            itl_value = best_run.get('itl_mean', best_run['tpot_mean'])

            summary_data.append({
                'Platform': platform2_label,
                'Cores': cores,
                'Throughput (tok/s)': best_run['throughput_tokens_sec_mean'],
                'TTFT (ms)': best_run['ttft_mean'],
                'TPOT (ms)': best_run['tpot_mean'],
                'ITL (ms)': itl_value,
                'Latency (s)': best_run['latency_mean'],
            })

    metrics_df = pd.DataFrame(summary_data)

    # Create visual summary
    fig = plt.figure(figsize=(20, 12))
    fig.suptitle('High-Level Performance Metrics Summary', fontsize=18, fontweight='bold', y=0.98)

    # Create 2x3 grid for metrics
    gs = fig.add_gridspec(2, 3, hspace=0.3, wspace=0.3, top=0.93, bottom=0.08, left=0.06, right=0.96)

    metrics_to_plot = [
        ('Throughput (tok/s)', 'Throughput (tokens/second)', True),
        ('TTFT (ms)', 'Time to First Token (ms)', False),
        ('TPOT (ms)', 'Time Per Output Token (ms)', False),
        ('ITL (ms)', 'Inter-Token Latency (ms)', False),
        ('Latency (s)', 'Total Latency (seconds)', False),
    ]

    for idx, (metric, title, higher_is_better) in enumerate(metrics_to_plot):
        row = idx // 3
        col = idx % 3
        ax = fig.add_subplot(gs[row, col])

        # Get data for each platform
        p1_data = metrics_df[metrics_df['Platform'] == platform1_label]
        p2_data = metrics_df[metrics_df['Platform'] == platform2_label]

        x = np.arange(len(common_cores))
        width = 0.35

        bars1 = ax.bar(x - width/2, p1_data[metric].values, width,
                      label=platform1_label, color=platform1_color, alpha=0.9,
                      edgecolor='black', linewidth=1)
        bars2 = ax.bar(x + width/2, p2_data[metric].values, width,
                      label=platform2_label, color=platform2_color, alpha=0.9,
                      edgecolor='black', linewidth=1)

        # Add value labels on bars
        for bars in [bars1, bars2]:
            for bar in bars:
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2., height,
                       f'{height:.1f}',
                       ha='center', va='bottom', fontsize=9, fontweight='bold')

        ax.set_xlabel('Core Count', fontsize=11, fontweight='bold')
        ax.set_ylabel(title.split('(')[0].strip(), fontsize=11, fontweight='bold')
        ax.set_title(title, fontsize=12, fontweight='bold', pad=10)
        ax.set_xticks(x)
        ax.set_xticklabels([f'{c}' for c in common_cores])
        ax.legend(fontsize=9, loc='best')
        ax.grid(axis='y', alpha=0.3, linestyle='--')

        # Add indicator for better direction
        direction = '↑ Higher is better' if higher_is_better else '↓ Lower is better'
        ax.text(0.98, 0.02, direction, transform=ax.transAxes,
               fontsize=8, style='italic', color='gray',
               ha='right', va='bottom')

    # Add table in the last position
    ax_table = fig.add_subplot(gs[1, 2])
    ax_table.axis('off')

    # Create summary table data
    table_data = [['Metric', platform1_label, platform2_label, 'Winner']]

    for cores in common_cores:
        p1_row = metrics_df[(metrics_df['Platform'] == platform1_label) & (metrics_df['Cores'] == cores)]
        p2_row = metrics_df[(metrics_df['Platform'] == platform2_label) & (metrics_df['Cores'] == cores)]

        if len(p1_row) > 0 and len(p2_row) > 0:
            p1_throughput = p1_row['Throughput (tok/s)'].values[0]
            p2_throughput = p2_row['Throughput (tok/s)'].values[0]
            winner = platform1_label if p1_throughput > p2_throughput else platform2_label

            table_data.append([
                f'{cores} cores',
                f'{p1_throughput:.0f} tok/s',
                f'{p2_throughput:.0f} tok/s',
                winner
            ])

    table = ax_table.table(cellText=table_data, cellLoc='center', loc='center',
                          bbox=[0, 0, 1, 1])
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1, 2)

    # Style header row
    for i in range(4):
        table[(0, i)].set_facecolor('#E8E8E8')
        table[(0, i)].set_text_props(weight='bold')

    # Color winner cells
    for i in range(1, len(table_data)):
        winner = table_data[i][3]
        if winner == platform1_label:
            table[(i, 3)].set_facecolor('#E3F2FD')
        else:
            table[(i, 3)].set_facecolor('#FFEBEE')

    ax_table.set_title('Throughput Winner by Core Count', fontsize=12, fontweight='bold', pad=10)

    plt.savefig(f'{output_dir}/high_level_metrics_summary.png', dpi=300, bbox_inches='tight')
    print("Saved high_level_metrics_summary.png")
    plt.close()

    # Save detailed CSV
    metrics_df_pivot = metrics_df.pivot(index='Cores', columns='Platform')
    metrics_df_pivot.to_csv(f'{output_dir}/high_level_metrics_detailed.csv')
    print("Saved high_level_metrics_detailed.csv")

    return metrics_df


def create_sweep_comparison_summary(intel_df, amd_df, output_dir="benchmark_reports_sweep_comparison",
                                   platform1_label="Intel Xeon", platform2_label="AMD EPYC"):
    """Create summary comparing sweep test characteristics."""
    Path(output_dir).mkdir(exist_ok=True)

    summary_data = []

    # Platform 1 summary
    for cores in sorted(intel_df['cores'].unique()):
        core_data = intel_df[intel_df['cores'] == cores]
        summary_data.append({
            'Platform': platform1_label,
            'Cores': cores,
            'Num Points': len(core_data),
            'Load Range (req/s)': f"{core_data['requests_sec_mean'].min():.2f} - {core_data['requests_sec_mean'].max():.2f}",
            'Max Throughput (tok/s)': core_data['throughput_tokens_sec_mean'].max(),
            'TTFT Range (ms)': f"{core_data['ttft_mean'].min():.1f} - {core_data['ttft_mean'].max():.1f}",
        })

    # Platform 2 summary
    for cores in sorted(amd_df['cores'].unique()):
        core_data = amd_df[amd_df['cores'] == cores]
        summary_data.append({
            'Platform': platform2_label,
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
        description='Compare sweep test performance curves between two platforms',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Compare Intel Xeon vs AMD EPYC (default)
  python3 compare_sweep_platforms.py

  # Compare ZenDNN vs vLLM on AMD EPYC
  python3 compare_sweep_platforms.py \\
    --intel-dir /path/to/zendnn --amd-dir /path/to/vllm \\
    --platform1-label "EPYC ZenDNN" --platform2-label "EPYC vLLM" \\
    --platform1-color "#00A4EF" --platform2-color "#ED1C24" \\
    --output-dir epyc_framework_comparison

  # Custom directories and labels
  python3 compare_sweep_platforms.py \\
    --intel-dir /path/to/platform1 --amd-dir /path/to/platform2 \\
    --platform1-label "Platform A" --platform2-label "Platform B"
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

    parser.add_argument(
        '--platform1-label',
        default='Intel Xeon',
        help='Label for first platform (default: Intel Xeon)'
    )

    parser.add_argument(
        '--platform2-label',
        default='AMD EPYC',
        help='Label for second platform (default: AMD EPYC)'
    )

    parser.add_argument(
        '--platform1-color',
        default='#0071C5',
        help='Color for first platform (default: #0071C5 - Intel blue)'
    )

    parser.add_argument(
        '--platform2-color',
        default='#ED1C24',
        help='Color for second platform (default: #ED1C24 - AMD red)'
    )

    return parser.parse_args()


def main():
    """Main execution function."""
    args = parse_args()

    print("=" * 80)
    print(f"Platform Sweep Comparison: {args.platform1_label} vs {args.platform2_label}")
    print("=" * 80)
    print(f"Platform 1 ({args.platform1_label}) data directory: {args.intel_dir}")
    print(f"Platform 2 ({args.platform2_label}) data directory: {args.amd_dir}")
    print(f"Output directory: {args.output_dir}")

    print(f"\nLoading {args.platform1_label} sweep results...")
    try:
        intel_df = load_all_results(base_path=args.intel_dir)
        print(f"Loaded {len(intel_df)} {args.platform1_label} runs from {intel_df['test_name'].nunique()} tests")
        print(f"{args.platform1_label} core counts: {sorted(intel_df['cores'].unique())}")
    except Exception as e:
        print(f"\nError loading {args.platform1_label} results: {e}")
        sys.exit(1)

    print(f"\nLoading {args.platform2_label} sweep results...")
    try:
        amd_df = load_all_results(base_path=args.amd_dir)
        print(f"Loaded {len(amd_df)} {args.platform2_label} runs from {amd_df['test_name'].nunique()} tests")
        print(f"{args.platform2_label} core counts: {sorted(amd_df['cores'].unique())}")
    except Exception as e:
        print(f"\nError loading {args.platform2_label} results: {e}")
        sys.exit(1)

    print("\nCreating sweep curve comparisons...")
    create_platform_sweep_comparison(intel_df, amd_df, output_dir=args.output_dir,
                                     platform1_label=args.platform1_label,
                                     platform2_label=args.platform2_label,
                                     platform1_color=args.platform1_color,
                                     platform2_color=args.platform2_color)

    print("\nCreating saturation analysis...")
    create_saturation_comparison(intel_df, amd_df, output_dir=args.output_dir,
                                platform1_label=args.platform1_label,
                                platform2_label=args.platform2_label,
                                platform1_color=args.platform1_color,
                                platform2_color=args.platform2_color)

    print("\nCreating high-level metrics summary...")
    create_high_level_metrics_summary(intel_df, amd_df, output_dir=args.output_dir,
                                     platform1_label=args.platform1_label,
                                     platform2_label=args.platform2_label,
                                     platform1_color=args.platform1_color,
                                     platform2_color=args.platform2_color)

    print("\nGenerating comparison summary...")
    summary = create_sweep_comparison_summary(intel_df, amd_df, output_dir=args.output_dir,
                                             platform1_label=args.platform1_label,
                                             platform2_label=args.platform2_label)

    print("\n" + "=" * 80)
    print("Summary Preview:")
    print("=" * 80)
    print(summary.to_string(index=False))

    print("\n" + "=" * 80)
    print(f"Sweep comparison complete! Check the '{args.output_dir}' directory.")
    print("=" * 80)


if __name__ == "__main__":
    main()
