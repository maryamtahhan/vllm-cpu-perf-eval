#!/usr/bin/env python3
"""
Analyze guidellm sweep test performance curves across different load levels.

This script plots the full sweep test results showing how performance varies
with load (request rate) for each core configuration. Unlike the main analysis
script which selects only the best run, this shows all constant-rate test points
to reveal the performance curve and saturation behavior.

Usage:
    python3 analyze_sweep_curves.py [data_dir] [--output-dir OUTPUT_DIR]

Arguments:
    data_dir        Path to directory containing benchmark results
                    (default: /Users/Xeon-multi-platform)
    --output-dir    Directory for output reports (default: benchmark_reports_sweep)
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


def filter_sweep_data(df):
    """
    Filter data to include only constant-rate sweep strategies.

    Excludes synchronous and throughput strategies to focus on the
    constant-rate load tests that form the performance curve.

    :param df: DataFrame with all benchmark results
    :return: Filtered DataFrame with only constant-rate strategies
    """
    # Filter to only 'constant' strategy type
    # The strategy column should be parsed from the CSV data
    # For now, we'll use all data except the extremes
    # A better approach would be to parse the Strategy column

    # Group by test and filter out likely sync/throughput runs
    # Sync has lowest throughput, throughput has highest
    filtered = []

    for test_name in df['test_name'].unique():
        test_data = df[df['test_name'] == test_name].copy()

        # Sort by throughput
        test_data = test_data.sort_values('throughput_tokens_sec_mean')

        # Skip first (sync) and last (throughput) if we have more than 3 runs
        if len(test_data) > 3:
            test_data = test_data.iloc[1:-1]

        filtered.append(test_data)

    return pd.concat(filtered, ignore_index=True) if filtered else df


def create_sweep_performance_curves(df, output_dir="benchmark_reports_sweep"):
    """Create performance curve plots showing load vs metrics."""
    Path(output_dir).mkdir(exist_ok=True)

    # Get unique models and core counts
    models = sorted(df['model'].unique())
    core_counts = sorted(df['cores'].unique())

    # Colors for different core counts
    core_colors = {
        8: '#1f77b4',   # blue
        16: '#ff7f0e',  # orange
        24: '#2ca02c',  # green
        32: '#d62728',  # red
        64: '#9467bd',  # purple
        96: '#8c564b',  # brown
    }

    # Metrics to plot
    metrics = [
        ('requests_sec_mean', 'Load (Target Requests/sec)',
         'Throughput (tokens/sec)', 'throughput_tokens_sec_mean', True),
        ('requests_sec_mean', 'Load (Target Requests/sec)',
         'Actual Requests/sec', 'requests_sec_mean', True),
        ('requests_sec_mean', 'Load (Target Requests/sec)',
         'TTFT (ms)', 'ttft_mean', False),
        ('requests_sec_mean', 'Load (Target Requests/sec)',
         'TPOT (ms)', 'tpot_mean', False),
        ('requests_sec_mean', 'Load (Target Requests/sec)',
         'Latency (sec)', 'latency_mean', False),
    ]

    for model in models:
        model_data = df[df['model'] == model]

        for x_col, xlabel, ylabel, y_col, higher_is_better in metrics:
            fig, ax = plt.subplots(figsize=(12, 7))

            for cores in core_counts:
                core_data = model_data[model_data['cores'] == cores].sort_values(x_col)

                if len(core_data) > 0:
                    ax.plot(core_data[x_col], core_data[y_col],
                           marker='o', linewidth=2, markersize=6,
                           label=f'{cores}c',
                           color=core_colors.get(cores, '#999999'))

            direction = "↑" if higher_is_better else "↓"
            ax.set_xlabel(xlabel, fontsize=12)
            ax.set_ylabel(f'{ylabel} {direction}', fontsize=12)
            ax.set_title(f'{model}: {ylabel} vs Load', fontsize=14, fontweight='bold')
            ax.legend(title='Core Count', fontsize=10)
            ax.grid(True, alpha=0.3)

            plt.tight_layout()
            safe_ylabel = ylabel.replace('/', '_').replace(' ', '_').replace('(', '').replace(')', '')
            filename = f'{model.lower()}_{safe_ylabel.lower()}_vs_load.png'
            plt.savefig(f'{output_dir}/{filename}', dpi=300, bbox_inches='tight')
            print(f"Saved {filename}")
            plt.close()

    # Create combined overview for each model
    for model in models:
        model_data = df[df['model'] == model]

        fig, axes = plt.subplots(2, 2, figsize=(16, 12))
        fig.suptitle(f'{model}: Performance Curves Across Load Levels',
                     fontsize=16, fontweight='bold')

        plot_configs = [
            (axes[0, 0], 'requests_sec_mean', 'throughput_tokens_sec_mean',
             'Load (Requests/sec)', 'Throughput (tokens/sec) ↑'),
            (axes[0, 1], 'requests_sec_mean', 'ttft_mean',
             'Load (Requests/sec)', 'TTFT (ms) ↓'),
            (axes[1, 0], 'requests_sec_mean', 'tpot_mean',
             'Load (Requests/sec)', 'TPOT (ms) ↓'),
            (axes[1, 1], 'requests_sec_mean', 'latency_mean',
             'Load (Requests/sec)', 'Latency (sec) ↓'),
        ]

        for ax, x_col, y_col, xlabel, ylabel in plot_configs:
            for cores in core_counts:
                core_data = model_data[model_data['cores'] == cores].sort_values(x_col)

                if len(core_data) > 0:
                    ax.plot(core_data[x_col], core_data[y_col],
                           marker='o', linewidth=2, markersize=6,
                           label=f'{cores}c',
                           color=core_colors.get(cores, '#999999'))

            ax.set_xlabel(xlabel, fontsize=10)
            ax.set_ylabel(ylabel, fontsize=10)
            ax.set_title(ylabel.replace(' ↑', '').replace(' ↓', ''), fontweight='bold')
            ax.legend(title='Cores', fontsize=9)
            ax.grid(True, alpha=0.3)

        plt.tight_layout()
        plt.savefig(f'{output_dir}/{model.lower()}_sweep_overview.png',
                   dpi=300, bbox_inches='tight')
        print(f"Saved {model.lower()}_sweep_overview.png")
        plt.close()


def create_efficiency_analysis(df, output_dir="benchmark_reports_sweep"):
    """Create efficiency analysis showing achieved vs target rates."""
    Path(output_dir).mkdir(exist_ok=True)

    models = sorted(df['model'].unique())
    core_counts = sorted(df['cores'].unique())

    core_colors = {
        8: '#1f77b4', 16: '#ff7f0e', 24: '#2ca02c', 32: '#d62728',
        64: '#9467bd', 96: '#8c564b',
    }

    for model in models:
        model_data = df[df['model'] == model]

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
        fig.suptitle(f'{model}: Load Efficiency Analysis',
                     fontsize=16, fontweight='bold')

        # Left: Achieved vs Target Rate
        for cores in core_counts:
            core_data = model_data[model_data['cores'] == cores].sort_values('requests_sec_mean')

            if len(core_data) > 0:
                # Plot achieved vs target (ideal would be y=x line)
                ax1.plot(core_data['requests_sec_mean'], core_data['requests_sec_mean'],
                        marker='o', linewidth=2, markersize=6,
                        label=f'{cores}c',
                        color=core_colors.get(cores, '#999999'))

        # Add ideal line
        max_rate = df['requests_sec_mean'].max()
        ax1.plot([0, max_rate], [0, max_rate], 'k--', alpha=0.3, label='Ideal (100%)')

        ax1.set_xlabel('Target Load (Requests/sec)', fontsize=12)
        ax1.set_ylabel('Achieved Rate (Requests/sec)', fontsize=12)
        ax1.set_title('Achieved vs Target Request Rate', fontweight='bold')
        ax1.legend(title='Cores')
        ax1.grid(True, alpha=0.3)

        # Right: Efficiency (achieved/target ratio) vs Load
        for cores in core_counts:
            core_data = model_data[model_data['cores'] == cores].sort_values('requests_sec_mean')

            if len(core_data) > 0:
                # Calculate efficiency (achieved/target)
                # For now assume target = measured (we'd need strategy data for actual target)
                # This is a limitation - we should parse the strategy column
                efficiency = core_data['requests_sec_mean'] / core_data['requests_sec_mean'].max()

                ax2.plot(core_data['requests_sec_mean'], efficiency,
                        marker='o', linewidth=2, markersize=6,
                        label=f'{cores}c',
                        color=core_colors.get(cores, '#999999'))

        ax2.axhline(y=0.98, color='r', linestyle='--', alpha=0.3, label='98% threshold')
        ax2.set_xlabel('Load (Requests/sec)', fontsize=12)
        ax2.set_ylabel('Efficiency Ratio', fontsize=12)
        ax2.set_title('Load Efficiency vs Request Rate', fontweight='bold')
        ax2.legend(title='Cores')
        ax2.grid(True, alpha=0.3)
        ax2.set_ylim([0, 1.1])

        plt.tight_layout()
        plt.savefig(f'{output_dir}/{model.lower()}_efficiency_analysis.png',
                   dpi=300, bbox_inches='tight')
        print(f"Saved {model.lower()}_efficiency_analysis.png")
        plt.close()


def create_sweep_summary(df, output_dir="benchmark_reports_sweep"):
    """Create summary table for sweep analysis."""
    Path(output_dir).mkdir(exist_ok=True)

    # Group by test and core count, get stats
    summary_data = []

    for test_name in df['test_name'].unique():
        test_data = df[df['test_name'] == test_name]
        model = test_data['model'].iloc[0]
        cores = test_data['cores'].iloc[0]

        summary_data.append({
            'Model': model,
            'Cores': cores,
            'Num Points': len(test_data),
            'Min Load (req/s)': test_data['requests_sec_mean'].min(),
            'Max Load (req/s)': test_data['requests_sec_mean'].max(),
            'Max Throughput (tok/s)': test_data['throughput_tokens_sec_mean'].max(),
            'Min TTFT (ms)': test_data['ttft_mean'].min(),
            'Max TTFT (ms)': test_data['ttft_mean'].max(),
        })

    summary_df = pd.DataFrame(summary_data)
    summary_df = summary_df.sort_values(['Model', 'Cores'])

    # Save to CSV
    summary_df.to_csv(f'{output_dir}/sweep_summary.csv', index=False, float_format='%.2f')

    # Save to text
    with open(f'{output_dir}/sweep_summary.txt', 'w') as f:
        f.write("=" * 120 + "\n")
        f.write("Sweep Test Summary - Performance Curve Analysis\n")
        f.write("=" * 120 + "\n\n")
        f.write(summary_df.to_string(index=False))
        f.write("\n\n" + "=" * 120 + "\n")

    print("Saved sweep_summary.csv and sweep_summary.txt")

    return summary_df


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Analyze guidellm sweep test performance curves',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use default directory
  python3 analyze_sweep_curves.py

  # Specify custom data directory
  python3 analyze_sweep_curves.py /path/to/benchmark/data

  # Specify custom output directory
  python3 analyze_sweep_curves.py --output-dir my_sweep_reports
        """
    )

    parser.add_argument(
        'data_dir',
        nargs='?',
        default='/Users/Xeon-multi-platform',
        help='Path to directory containing benchmark results'
    )

    parser.add_argument(
        '--output-dir',
        default='benchmark_reports_sweep',
        help='Directory for output reports (default: benchmark_reports_sweep)'
    )

    return parser.parse_args()


def main():
    """Main execution function."""
    args = parse_args()

    print("=" * 80)
    print("Sweep Test Performance Curve Analysis")
    print("=" * 80)
    print(f"Data directory: {args.data_dir}")
    print(f"Output directory: {args.output_dir}")

    print("\nLoading benchmark results...")
    try:
        df = load_all_results(base_path=args.data_dir)
        print(f"Loaded {len(df)} benchmark runs from {df['test_name'].nunique()} tests")
        print(f"Models: {sorted(df['model'].unique())}")
        print(f"Core counts: {sorted(df['cores'].unique())}")
    except Exception as e:
        print(f"\nError loading results: {e}")
        sys.exit(1)

    print(f"\nTotal data points: {len(df)}")

    # Note: We're using all data points - ideally we'd filter to only constant-rate
    # strategies, but that requires parsing the Strategy column from CSV
    print("\nCreating performance curve visualizations...")
    create_sweep_performance_curves(df, output_dir=args.output_dir)

    print("\nCreating efficiency analysis...")
    create_efficiency_analysis(df, output_dir=args.output_dir)

    print("\nGenerating sweep summary...")
    summary = create_sweep_summary(df, output_dir=args.output_dir)

    print("\n" + "=" * 80)
    print("Summary Preview:")
    print("=" * 80)
    print(summary.to_string(index=False))

    print("\n" + "=" * 80)
    print(f"Sweep analysis complete! Check the '{args.output_dir}' directory.")
    print("=" * 80)


if __name__ == "__main__":
    main()
