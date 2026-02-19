#!/usr/bin/env python3
"""
Create unified sweep-based comparisons for 2 or 3 platforms.

This script generates comprehensive visualizations showing platform comparisons:
1. Full sweep curves with all platforms and all core counts
2. Per-core comparison showing all platforms side by side
3. Percentile distributions (MEAN/P95) for latency and throughput metrics

Supports comparing 2 or 3 platforms dynamically. Common configurations:
- Intel Xeon vs AMD EPYC (2 platforms)
- Intel Xeon vs AMD EPYC ZenDNN vs AMD EPYC vLLM (3 platforms)

Usage:
    # Two platforms
    python3 create_three_platform_sweep_comparison.py \
        --platform1-dir /path/to/platform1 --platform1-name "Intel Xeon" --platform1-color "#0071C5" \
        --platform2-dir /path/to/platform2 --platform2-name "AMD EPYC" --platform2-color "#ED1C24"

    # Three platforms
    python3 create_three_platform_sweep_comparison.py \
        --platform1-dir /path/to/platform1 --platform1-name "Intel Xeon" --platform1-color "#0071C5" \
        --platform2-dir /path/to/platform2 --platform2-name "EPYC ZenDNN" --platform2-color "#ED1C24" \
        --platform3-dir /path/to/platform3 --platform3-name "EPYC vLLM" --platform3-color "#00AA00"
"""

import argparse
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import sys
import ast
import re

# Import functions from the main analysis script
from analyze_benchmark_results import load_all_results

# Set style for better-looking plots
sns.set_style("whitegrid")


def extract_percentiles_from_str(percentile_str):
    """Extract P95 from percentile string.

    GuideLL M stores 11 percentiles: [p001, p01, p05, p10, p25, p50, p75, p90, p95, p99, p999]
    Indices: 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10

    We extract P95 for comparison with MEAN (not median/P50).
    """
    try:
        perc_list = ast.literal_eval(percentile_str)
        if len(perc_list) >= 9:
            return {
                'p95': float(perc_list[8]),  # 95th percentile
            }
        return {'p95': None}
    except:
        return {'p95': None}


def load_results_with_percentiles(base_path):
    """Load benchmark results including P95 percentiles.

    Note: The main DataFrame already has MEAN values for all metrics.
    We only need to extract P95 percentiles for comparison.
    """
    # First load the standard results (includes MEAN for all metrics)
    df = load_all_results(base_path=base_path)

    # Now add P95 percentile data by re-reading CSV files
    all_test_dirs = [d for d in Path(base_path).iterdir() if d.is_dir()]

    percentile_rows = []

    for test_dir in all_test_dirs:
        csv_files = list(test_dir.glob('*.csv'))
        if not csv_files:
            continue

        csv_path = csv_files[0]
        test_name = test_dir.name

        try:
            # Read CSV with multi-level headers
            csv_df = pd.read_csv(csv_path, header=[0, 1, 2])

            # Extract core count from directory name
            cores_match = re.search(r'(\d+)c', test_name)
            cores = int(cores_match.group(1)) if cores_match else None

            # Process each row with row index for unique matching
            for idx, row in csv_df.iterrows():
                # Get request rate
                req_sec = row[('Server Throughput', 'Successful Requests/Sec', 'Mean')]

                # Extract P95 for latency metrics
                ttft_percs = extract_percentiles_from_str(
                    row[('Time to First Token', 'Successful ms', 'Percentiles')])
                tpot_percs = extract_percentiles_from_str(
                    row[('Time per Output Token', 'Successful ms', 'Percentiles')])
                latency_percs = extract_percentiles_from_str(
                    row[('Request Latency', 'Successful Sec', 'Percentiles')])

                # Extract throughput P95
                throughput_percs = extract_percentiles_from_str(
                    row[('Token Throughput', 'Successful Output Tokens/Sec', 'Percentiles')])

                percentile_rows.append({
                    'test_name': test_name,
                    'cores': cores,
                    'requests_sec_mean': float(req_sec),
                    'row_index': idx,
                    'ttft_p95': ttft_percs['p95'],
                    'tpot_p95': tpot_percs['p95'],
                    'latency_p95': latency_percs['p95'],
                    'throughput_p95': throughput_percs['p95'],
                })

        except Exception as e:
            print(f"Warning: Could not extract percentiles from {csv_path}: {e}")
            continue

    # Create percentile DataFrame
    perc_df = pd.DataFrame(percentile_rows)

    # Add row index to main DataFrame for reliable matching
    df = df.reset_index(drop=True)
    df['row_index'] = df.groupby('test_name').cumcount()

    # Merge with main DataFrame on test_name and row_index
    if len(perc_df) > 0:
        df = df.merge(perc_df[['test_name', 'row_index',
                                'ttft_p95', 'tpot_p95', 'latency_p95', 'throughput_p95']],
                      on=['test_name', 'row_index'], how='left')
        # Drop the row_index column as it's no longer needed
        df = df.drop(columns=['row_index'])

    return df


def create_three_platform_sweep_curves(platforms, output_dir="benchmark_reports_three_platform"):
    """Create unified sweep curves showing all platforms and all core counts.

    Args:
        platforms: Dictionary of platform info with 'name', 'df', 'color', 'label_prefix'
        output_dir: Output directory for generated plots
    """
    Path(output_dir).mkdir(exist_ok=True)

    # Get all unique core counts across all platforms
    all_cores = set()
    for platform_info in platforms.values():
        all_cores |= set(platform_info['df']['cores'].unique())
    all_cores = sorted(all_cores)

    # Core count line styles and markers
    core_styles = {16: '-', 32: '--', 64: '-.', 96: ':'}
    core_markers = {16: 'o', 32: 's', 64: '^', 96: 'D'}

    # Create figure with 2x2 grid for main metrics
    fig, axes = plt.subplots(2, 2, figsize=(24, 16))

    # Build title from platform names
    platform_names = list(platforms.keys())
    if len(platform_names) == 2:
        title = f'LLM Inference Performance: {platform_names[0]} vs {platform_names[1]}\n' + \
                'Full Sweep Curves Across All Core Counts'
    else:
        title = f'LLM Inference Performance: {" vs ".join(platform_names)}\n' + \
                'Full Sweep Curves Across All Core Counts'

    fig.suptitle(title, fontsize=20, fontweight='bold', y=0.995)

    # Metrics to plot: (column_name, xlabel, ylabel, title)
    metrics = [
        ('throughput_tokens_sec_mean', 'Load (Requests/sec)', 'Throughput (tokens/sec)',
         'Throughput vs Load ↑ (Higher is Better)'),
        ('ttft_mean', 'Load (Requests/sec)', 'TTFT (ms)',
         'Time to First Token vs Load ↓ (Lower is Better)'),
        ('tpot_mean', 'Load (Requests/sec)', 'TPOT (ms)',
         'Time per Output Token vs Load ↓ (Lower is Better)'),
        ('latency_mean', 'Load (Requests/sec)', 'Latency (sec)',
         'Total Request Latency vs Load ↓ (Lower is Better)'),
    ]

    for idx, (metric_col, xlabel, ylabel, title) in enumerate(metrics):
        ax = axes[idx // 2, idx % 2]

        # Plot for each platform and core count
        for platform_name, platform_info in platforms.items():
            df = platform_info['df']
            color = platform_info['color']
            prefix = platform_info['label_prefix']

            for cores in all_cores:
                # Filter data for this core count
                core_data = df[df['cores'] == cores].sort_values('requests_sec_mean')

                if len(core_data) > 0:
                    ax.plot(core_data['requests_sec_mean'],
                           core_data[metric_col],
                           marker=core_markers.get(cores, 'o'),
                           linestyle=core_styles.get(cores, '-'),
                           linewidth=2.5,
                           markersize=6,
                           color=color,
                           alpha=0.7,
                           label=f'{prefix} {cores}c')

        ax.set_xlabel(xlabel, fontsize=13, fontweight='bold')
        ax.set_ylabel(ylabel, fontsize=13, fontweight='bold')
        ax.set_title(title, fontsize=14, fontweight='bold', pad=10)
        ax.legend(loc='best', fontsize=8, ncol=3, framealpha=0.95,
                 bbox_to_anchor=(1.0, 1.0), borderaxespad=0)
        ax.grid(True, alpha=0.3, linestyle='--')

    plt.tight_layout(rect=[0, 0, 1, 0.99])

    # Save the unified sweep curves
    output_file = f'{output_dir}/three_platform_sweep_curves_all_cores.png'
    plt.savefig(output_file, dpi=300, bbox_inches='tight', facecolor='white')
    print(f"✓ Saved {output_file}")
    plt.close()


def create_per_core_comparison(platforms, output_dir="benchmark_reports_three_platform"):
    """Create separate comparison for each core count showing all platforms.

    Args:
        platforms: Dictionary of platform info with 'name', 'df', 'color', 'label_prefix'
        output_dir: Output directory for generated plots
    """
    Path(output_dir).mkdir(exist_ok=True)

    # Get all unique core counts
    all_cores = set()
    for platform_info in platforms.values():
        all_cores |= set(platform_info['df']['cores'].unique())
    all_cores = sorted(all_cores)

    # Metrics to plot
    metrics = [
        ('throughput_tokens_sec_mean', 'Throughput (tokens/sec)', 'Throughput ↑'),
        ('ttft_mean', 'TTFT (ms)', 'Time to First Token ↓'),
        ('tpot_mean', 'TPOT (ms)', 'Time per Output Token ↓'),
        ('latency_mean', 'Latency (sec)', 'Total Latency ↓'),
    ]

    # Create one figure per core count
    for cores in all_cores:
        fig, axes = plt.subplots(2, 2, figsize=(20, 14))
        fig.suptitle(f'{cores}-Core Configuration: Platform Comparison Across Load Levels',
                     fontsize=18, fontweight='bold', y=0.995)

        for idx, (metric_col, ylabel, title) in enumerate(metrics):
            ax = axes[idx // 2, idx % 2]

            # Plot each platform
            for platform_name, platform_info in platforms.items():
                df = platform_info['df']
                color = platform_info['color']

                # Filter for this core count
                core_data = df[df['cores'] == cores].sort_values('requests_sec_mean')

                if len(core_data) > 0:
                    ax.plot(core_data['requests_sec_mean'],
                           core_data[metric_col],
                           marker='o',
                           linestyle='-',
                           linewidth=3,
                           markersize=8,
                           color=color,
                           alpha=0.8,
                           label=platform_name)

            ax.set_xlabel('Load (Requests/sec)', fontsize=12, fontweight='bold')
            ax.set_ylabel(ylabel, fontsize=12, fontweight='bold')
            ax.set_title(title, fontsize=14, fontweight='bold', pad=10)
            ax.legend(loc='best', fontsize=11, framealpha=0.95)
            ax.grid(True, alpha=0.3, linestyle='--')

        plt.tight_layout(rect=[0, 0, 1, 0.99])

        # Save per-core comparison
        output_file = f'{output_dir}/comparison_{cores}cores.png'
        plt.savefig(output_file, dpi=300, bbox_inches='tight', facecolor='white')
        print(f"✓ Saved {output_file}")
        plt.close()


def create_percentile_sweep_overview(platforms, output_dir="benchmark_reports_three_platform"):
    """Create MEAN, P95 percentile sweep overview showing latency distributions.

    Args:
        platforms: Dictionary of platform info with 'name', 'df', 'color', 'label_prefix'
        output_dir: Output directory for generated plots
    """
    Path(output_dir).mkdir(exist_ok=True)

    # Get all unique core counts
    all_cores = set()
    for platform_info in platforms.values():
        all_cores |= set(platform_info['df']['cores'].unique())
    all_cores = sorted(all_cores)

    # Create one figure per core count showing MEAN/P95 for all platforms
    for cores in all_cores:
        fig, axes = plt.subplots(1, 3, figsize=(24, 7))
        fig.suptitle(f'{cores}-Core Configuration: Latency Distribution (MEAN / P95)\n' +
                     'Lower is Better for All Metrics',
                     fontsize=18, fontweight='bold', y=0.98)

        # Metrics: TTFT, TPOT, Total Latency
        metrics = [
            ('ttft', 'Time to First Token (ms)', 'TTFT - Time to First Token'),
            ('tpot', 'Time per Output Token (ms)', 'TPOT - Time per Output Token'),
            ('latency', 'Total Request Latency (sec)', 'Total Request Latency'),
        ]

        for idx, (metric_prefix, ylabel, title) in enumerate(metrics):
            ax = axes[idx]

            # Plot each platform with MEAN, P95
            for platform_name, platform_info in platforms.items():
                df = platform_info['df']
                color = platform_info['color']

                # Filter for this core count
                core_data = df[df['cores'] == cores].sort_values('requests_sec_mean')

                if len(core_data) > 0:
                    # Use MEAN and P95 columns
                    mean_col = f'{metric_prefix}_mean'
                    p95_col = f'{metric_prefix}_p95'

                    if mean_col in core_data.columns and p95_col in core_data.columns:
                        # Plot P95 (solid - emphasized), MEAN (dashed)
                        ax.plot(core_data['requests_sec_mean'],
                               core_data[p95_col],
                               marker='s', linestyle='-', linewidth=2.5,
                               markersize=7, color=color, alpha=0.9,
                               label=f'{platform_name} P95')
                        ax.plot(core_data['requests_sec_mean'],
                               core_data[mean_col],
                               marker='o', linestyle='--', linewidth=2,
                               markersize=6, color=color, alpha=0.7,
                               label=f'{platform_name} MEAN')

            ax.set_xlabel('Load (Requests/sec)', fontsize=11, fontweight='bold')
            ax.set_ylabel(ylabel, fontsize=11, fontweight='bold')
            ax.set_title(title, fontsize=14, fontweight='bold', pad=12)
            ax.legend(loc='best', fontsize=10, ncol=1, framealpha=0.95)
            ax.grid(True, alpha=0.3, linestyle='--')

        plt.tight_layout()

        # Save per-core percentile overview
        output_file = f'{output_dir}/percentile_overview_{cores}cores.png'
        plt.savefig(output_file, dpi=300, bbox_inches='tight', facecolor='white')
        print(f"✓ Saved {output_file}")
        plt.close()


def create_throughput_percentile_overview(platforms,
                                         output_dir="benchmark_reports_three_platform"):
    """Create throughput MEAN, P95 percentile overview for all platforms.

    Args:
        platforms: Dictionary of platform info with 'name', 'df', 'color', 'label_prefix'
        output_dir: Output directory for generated plots
    """
    Path(output_dir).mkdir(exist_ok=True)

    # Get all unique core counts
    all_cores = set()
    for platform_info in platforms.values():
        all_cores |= set(platform_info['df']['cores'].unique())
    all_cores = sorted(all_cores)

    # Create one figure per core count showing throughput MEAN/P95
    for cores in all_cores:
        fig, ax = plt.subplots(1, 1, figsize=(12, 8))
        fig.suptitle(f'{cores}-Core Configuration: Throughput Distribution (MEAN / P95)\n' +
                     'Higher is Better',
                     fontsize=18, fontweight='bold', y=0.98)

        # Plot each platform with MEAN, P95 for throughput
        for platform_name, platform_info in platforms.items():
            df = platform_info['df']
            color = platform_info['color']

            # Filter for this core count
            core_data = df[df['cores'] == cores].sort_values('requests_sec_mean')

            if len(core_data) > 0:
                # Use MEAN and P95 columns for throughput
                mean_col = 'throughput_tokens_sec_mean'
                p95_col = 'throughput_p95'

                if mean_col in core_data.columns and p95_col in core_data.columns:
                    # Plot P95 (solid - emphasized), MEAN (dashed)
                    ax.plot(core_data['requests_sec_mean'],
                           core_data[p95_col],
                           marker='s', linestyle='-', linewidth=3,
                           markersize=7, color=color, alpha=0.9,
                           label=f'{platform_name} P95')
                    ax.plot(core_data['requests_sec_mean'],
                           core_data[mean_col],
                           marker='o', linestyle='--', linewidth=2.5,
                           markersize=6, color=color, alpha=0.7,
                           label=f'{platform_name} MEAN')

        ax.set_xlabel('Load (Requests/sec)', fontsize=13, fontweight='bold')
        ax.set_ylabel('Throughput (tokens/sec)', fontsize=13, fontweight='bold')
        ax.set_title('Throughput Distribution Across Load Levels',
                     fontsize=15, fontweight='bold', pad=15)
        ax.legend(loc='best', fontsize=11, ncol=1, framealpha=0.95)
        ax.grid(True, alpha=0.3, linestyle='--')

        plt.tight_layout()

        # Save throughput percentile overview
        output_file = f'{output_dir}/throughput_percentile_{cores}cores.png'
        plt.savefig(output_file, dpi=300, bbox_inches='tight', facecolor='white')
        print(f"✓ Saved {output_file}")
        plt.close()


def create_unified_percentile_overview(platforms,
                                       output_dir="benchmark_reports_three_platform"):
    """Create unified percentile overview with all cores on one graph.

    Args:
        platforms: Dictionary of platform info with 'name', 'df', 'color', 'label_prefix'
        output_dir: Output directory for generated plots
    """
    Path(output_dir).mkdir(exist_ok=True)

    # Get all unique core counts
    all_cores = set()
    for platform_info in platforms.values():
        all_cores |= set(platform_info['df']['cores'].unique())
    all_cores = sorted(all_cores)

    # Core styles
    core_styles = {16: '-', 32: '--', 64: '-.', 96: ':'}
    core_markers = {16: 'o', 32: 's', 64: '^', 96: 'D'}

    # Create figure showing MEAN, P95 for one key metric (TTFT)
    fig, axes = plt.subplots(1, 2, figsize=(20, 7))
    fig.suptitle('Time to First Token (TTFT) Distribution\n' +
                 'All Platforms and Core Counts - Lower is Better',
                 fontsize=18, fontweight='bold', y=0.98)

    metrics = [('mean', 'MEAN - Average time to first token'),
               ('p95', 'P95 - 95% of requests complete within this time')]

    for metric_idx, (metric, metric_title) in enumerate(metrics):
        ax = axes[metric_idx]
        col_name = f'ttft_{metric}'

        # Plot each platform and core count
        for platform_name, platform_info in platforms.items():
            df = platform_info['df']
            color = platform_info['color']
            prefix = platform_info['label_prefix']

            for cores in all_cores:
                core_data = df[df['cores'] == cores].sort_values('requests_sec_mean')

                if len(core_data) > 0 and col_name in core_data.columns:
                    ax.plot(core_data['requests_sec_mean'],
                           core_data[col_name],
                           marker=core_markers.get(cores, 'o'),
                           linestyle=core_styles.get(cores, '-'),
                           linewidth=2,
                           markersize=5,
                           color=color,
                           alpha=0.7,
                           label=f'{prefix} {cores}c')

        ax.set_xlabel('Load (Requests/sec)', fontsize=12, fontweight='bold')
        ax.set_ylabel('TTFT (ms)', fontsize=12, fontweight='bold')
        ax.set_title(metric_title, fontsize=12, fontweight='bold', pad=10)
        ax.legend(loc='best', fontsize=8, ncol=2, framealpha=0.95)
        ax.grid(True, alpha=0.3, linestyle='--')

    plt.tight_layout()

    # Save unified percentile overview
    output_file = f'{output_dir}/unified_percentile_overview_ttft.png'
    plt.savefig(output_file, dpi=300, bbox_inches='tight', facecolor='white')
    print(f"✓ Saved {output_file}")
    plt.close()


def create_summary_table(platforms, output_dir="benchmark_reports_three_platform"):
    """Create summary table comparing best performance for each platform/core combination.

    Args:
        platforms: Dictionary of platform info with 'name', 'df', 'color', 'label_prefix'
        output_dir: Output directory for generated plots
    """
    Path(output_dir).mkdir(exist_ok=True)

    # Collect best performance for each platform/core combination
    summary_data = []

    # Get all unique core counts
    all_cores = set()
    for platform_info in platforms.values():
        all_cores |= set(platform_info['df']['cores'].unique())
    all_cores = sorted(all_cores)

    for cores in all_cores:
        for platform_name, platform_info in platforms.items():
            df = platform_info['df']
            core_data = df[df['cores'] == cores]

            if len(core_data) > 0:
                # Use the same selection logic: >=95% of max throughput, lowest latency
                max_throughput = core_data['throughput_tokens_sec_mean'].max()
                threshold = max_throughput * 0.95
                top_runs = core_data[core_data['throughput_tokens_sec_mean'] >= threshold]

                if len(top_runs) > 0:
                    best_run = top_runs.loc[top_runs['latency_mean'].idxmin()]

                    summary_data.append({
                        'Platform': platform_name,
                        'Cores': cores,
                        'Throughput (tok/s)': f"{best_run['throughput_tokens_sec_mean']:.1f}",
                        'TTFT (ms)': f"{best_run['ttft_mean']:.1f}",
                        'TPOT (ms)': f"{best_run['tpot_mean']:.1f}",
                        'Latency (s)': f"{best_run['latency_mean']:.1f}",
                        'Load (req/s)': f"{best_run['requests_sec_mean']:.2f}"
                    })

    # Create summary table
    summary_df = pd.DataFrame(summary_data)

    # Save as CSV
    num_platforms = len(platforms)
    csv_file = f'{output_dir}/platform_summary.csv'
    summary_df.to_csv(csv_file, index=False)
    print(f"✓ Saved {csv_file}")

    # Save as text table
    txt_file = f'{output_dir}/platform_summary.txt'
    with open(txt_file, 'w') as f:
        f.write("=" * 120 + "\n")
        platform_count_text = f"{num_platforms}-Platform" if num_platforms > 1 else "Platform"
        f.write(f"{platform_count_text} Performance Summary (Selection: ≥95% max throughput + lowest latency)\n")
        f.write("=" * 120 + "\n\n")
        f.write(summary_df.to_string(index=False))
        f.write("\n\n" + "=" * 120 + "\n")

    print(f"✓ Saved {txt_file}")

    return summary_df


def print_load_summary(platforms):
    """Print summary of available load points for all platforms.

    Args:
        platforms: Dictionary of platform info with 'name', 'df', 'color', 'label_prefix'
    """
    print("\n" + "=" * 80)
    print("Available Load Points Summary")
    print("=" * 80)

    for platform_name, platform_info in platforms.items():
        df = platform_info['df']
        print(f"\n{platform_name}:")
        for test_name in sorted(df['test_name'].unique()):
            test_data = df[df['test_name'] == test_name]
            loads = sorted(test_data['requests_sec_mean'].values)
            print(f"  {test_name}: {len(loads)} points, "
                  f"range {loads[0]:.2f} - {loads[-1]:.2f} req/s")


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Create unified platform sweep comparisons (2 or 3 platforms)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Two platforms
  %(prog)s --platform1-dir /path/to/xeon --platform1-name "Intel Xeon" \\
           --platform2-dir /path/to/epyc --platform2-name "AMD EPYC"

  # Three platforms (default configuration)
  %(prog)s --intel-dir /path/to/xeon \\
           --epyc-zendnn-dir /path/to/epyc-zendnn \\
           --epyc-vllm-dir /path/to/epyc-vllm
        """
    )

    # Legacy three-platform arguments (for backward compatibility)
    parser.add_argument(
        '--intel-dir',
        help='Path to Intel Xeon benchmark results (legacy option)'
    )

    parser.add_argument(
        '--epyc-zendnn-dir',
        help='Path to AMD EPYC ZenDNN benchmark results (legacy option)'
    )

    parser.add_argument(
        '--epyc-vllm-dir',
        help='Path to AMD EPYC vLLM benchmark results (legacy option)'
    )

    # Generic platform arguments
    parser.add_argument(
        '--platform1-dir',
        help='Path to platform 1 benchmark results'
    )

    parser.add_argument(
        '--platform1-name',
        default='Platform 1',
        help='Display name for platform 1 (default: "Platform 1")'
    )

    parser.add_argument(
        '--platform1-color',
        default='#0071C5',
        help='Color for platform 1 (default: "#0071C5" - Intel blue)'
    )

    parser.add_argument(
        '--platform2-dir',
        help='Path to platform 2 benchmark results'
    )

    parser.add_argument(
        '--platform2-name',
        default='Platform 2',
        help='Display name for platform 2 (default: "Platform 2")'
    )

    parser.add_argument(
        '--platform2-color',
        default='#ED1C24',
        help='Color for platform 2 (default: "#ED1C24" - AMD red)'
    )

    parser.add_argument(
        '--platform3-dir',
        help='Path to platform 3 benchmark results (optional)'
    )

    parser.add_argument(
        '--platform3-name',
        default='Platform 3',
        help='Display name for platform 3 (default: "Platform 3")'
    )

    parser.add_argument(
        '--platform3-color',
        default='#00AA00',
        help='Color for platform 3 (default: "#00AA00" - green)'
    )

    parser.add_argument(
        '--output-dir',
        default='benchmark_reports',
        help='Directory for output reports (default: "benchmark_reports")'
    )

    return parser.parse_args()


def main():
    """Main execution function."""
    args = parse_args()

    # Build platforms dictionary based on provided arguments
    platforms = {}

    # Check for legacy three-platform mode
    if args.intel_dir and args.epyc_zendnn_dir:
        print("=" * 80)
        print("Using legacy three-platform mode")
        print("=" * 80)

        platforms['Intel Xeon'] = {
            'dir': args.intel_dir,
            'color': '#0071C5',
            'label_prefix': 'Xeon'
        }
        platforms['EPYC ZenDNN'] = {
            'dir': args.epyc_zendnn_dir,
            'color': '#ED1C24',
            'label_prefix': 'EPYC-ZenDNN'
        }
        if args.epyc_vllm_dir:
            platforms['EPYC vLLM'] = {
                'dir': args.epyc_vllm_dir,
                'color': '#00AA00',
                'label_prefix': 'EPYC-vLLM'
            }
    else:
        # Use generic platform mode
        if args.platform1_dir:
            # Generate a short prefix from the platform name
            prefix1 = args.platform1_name.replace(' ', '-')
            platforms[args.platform1_name] = {
                'dir': args.platform1_dir,
                'color': args.platform1_color,
                'label_prefix': prefix1
            }

        if args.platform2_dir:
            prefix2 = args.platform2_name.replace(' ', '-')
            platforms[args.platform2_name] = {
                'dir': args.platform2_dir,
                'color': args.platform2_color,
                'label_prefix': prefix2
            }

        if args.platform3_dir:
            prefix3 = args.platform3_name.replace(' ', '-')
            platforms[args.platform3_name] = {
                'dir': args.platform3_dir,
                'color': args.platform3_color,
                'label_prefix': prefix3
            }

    if len(platforms) < 2:
        print("Error: At least 2 platforms are required for comparison")
        print("\nPlease provide either:")
        print("  1. Legacy mode: --intel-dir and --epyc-zendnn-dir (and optionally --epyc-vllm-dir)")
        print("  2. Generic mode: --platform1-dir and --platform2-dir (and optionally --platform3-dir)")
        sys.exit(1)

    print("=" * 80)
    print(f"Creating {len(platforms)}-Platform Unified Sweep Comparisons")
    print("=" * 80)
    print(f"Platforms: {', '.join(platforms.keys())}")
    print(f"Output directory: {args.output_dir}")

    # Load all platform data with percentiles
    for platform_name, platform_info in platforms.items():
        print(f"\nLoading {platform_name} results with percentiles...")
        try:
            df = load_results_with_percentiles(base_path=platform_info['dir'])
            platform_info['df'] = df
            print(f"✓ Loaded {len(df)} runs from {df['test_name'].nunique()} tests")
        except Exception as e:
            print(f"✗ Error loading {platform_name} results: {e}")
            sys.exit(1)

    # Print load summary
    print_load_summary(platforms)

    print("\n" + "=" * 80)
    print("Creating unified platform sweep curves...")
    print("=" * 80)
    create_three_platform_sweep_curves(platforms, output_dir=args.output_dir)

    print("\n" + "=" * 80)
    print("Creating per-core comparisons...")
    print("=" * 80)
    create_per_core_comparison(platforms, output_dir=args.output_dir)

    print("\n" + "=" * 80)
    print("Creating summary table...")
    print("=" * 80)
    create_summary_table(platforms, output_dir=args.output_dir)

    print("\n" + "=" * 80)
    print("Creating latency percentile sweep overviews (MEAN/P95)...")
    print("=" * 80)
    create_percentile_sweep_overview(platforms, output_dir=args.output_dir)

    print("\n" + "=" * 80)
    print("Creating throughput percentile overviews (MEAN/P95)...")
    print("=" * 80)
    create_throughput_percentile_overview(platforms, output_dir=args.output_dir)

    print("\n" + "=" * 80)
    print("Creating unified TTFT percentile overview...")
    print("=" * 80)
    create_unified_percentile_overview(platforms, output_dir=args.output_dir)

    print("\n" + "=" * 80)
    print(f"{len(platforms)}-platform comparisons complete! Check '{args.output_dir}' directory.")
    print("=" * 80)
    print("\nGenerated files:")
    print("  - three_platform_sweep_curves_all_cores.png")
    print("  - comparison_XXcores.png (for each core count)")
    print("  - percentile_overview_XXcores.png (latency MEAN/P95 for each core count)")
    print("  - throughput_percentile_XXcores.png (throughput MEAN/P95 for each core count)")
    print("  - unified_percentile_overview_ttft.png (all platforms/cores TTFT MEAN/P95)")
    print("  - platform_summary.csv")
    print("  - platform_summary.txt")
    print("=" * 80)


if __name__ == "__main__":
    main()
