#!/usr/bin/env python3
"""
Analyze guidellm sweep test results and generate performance reports.

This script processes benchmark CSV data and creates visualizations and tables
comparing performance metrics across different configurations.

Usage:
    python3 analyze_benchmark_results.py [data_dir] [--output-dir OUTPUT_DIR]

Arguments:
    data_dir        Path to directory containing benchmark results
                    (default: /Users/Xeon-single-platform)
    --output-dir    Directory for output reports (default: benchmark_reports)
"""

import argparse
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
from pathlib import Path
import re
import sys
import json

# Set style for better-looking plots
sns.set_style("whitegrid")
plt.rcParams['figure.figsize'] = (14, 8)

def parse_csv_file(csv_path):
    """Parse a guidellm CSV file with multi-level headers."""
    # Read the CSV file with all 3 header rows
    df = pd.read_csv(csv_path, header=[0, 1, 2])

    return df

def extract_p95_from_percentiles(percentile_str):
    """Extract P95 value from percentile string."""
    import ast
    try:
        perc_list = ast.literal_eval(percentile_str)
        # guidellm stores 11 percentile values
        # Index 9 appears to be P95 (or P90), index 10 is max
        if len(perc_list) >= 10:
            return float(perc_list[9])
        return None
    except (ValueError, SyntaxError):
        return None


def extract_metrics(df):
    """Extract key metrics from the dataframe."""
    metrics = []

    # Find the correct column names by searching for them
    run_index_col = [c for c in df.columns if c[0] == 'Run Info' and c[1] == 'Run Index'][0]
    strategy_col = [c for c in df.columns if c[0] == 'Benchmark' and c[1] == 'Strategy'][0]
    successful_col = [c for c in df.columns if c[0] == 'Request Counts' and c[1] == 'Successful'][0]

    for idx, row in df.iterrows():
        try:
            # Get column values using multi-level indexing
            run_index_val = row[run_index_col]

            # Skip header explanation rows
            if pd.isna(run_index_val):
                continue

            strategy_val = row[strategy_col]

            # Extract mean values
            requests_sec_mean = row[('Server Throughput', 'Successful Requests/Sec', 'Mean')]
            concurrency_mean = row[('Server Throughput', 'Successful Concurrency', 'Mean')]
            throughput_mean = row[('Token Throughput', 'Successful Output Tokens/Sec', 'Mean')]
            ttft_mean = row[('Time to First Token', 'Successful ms', 'Mean')]
            tpot_mean = row[('Time per Output Token', 'Successful ms', 'Mean')]
            latency_mean = row[('Request Latency', 'Successful Sec', 'Mean')]
            successful = row[successful_col]

            # Extract P95 values from percentiles
            requests_sec_p95 = extract_p95_from_percentiles(
                row[('Server Throughput', 'Successful Requests/Sec', 'Percentiles')])
            concurrency_p95 = extract_p95_from_percentiles(
                row[('Server Throughput', 'Successful Concurrency', 'Percentiles')])
            throughput_p95 = extract_p95_from_percentiles(
                row[('Token Throughput', 'Successful Output Tokens/Sec', 'Percentiles')])
            ttft_p95 = extract_p95_from_percentiles(
                row[('Time to First Token', 'Successful ms', 'Percentiles')])
            tpot_p95 = extract_p95_from_percentiles(
                row[('Time per Output Token', 'Successful ms', 'Percentiles')])
            latency_p95 = extract_p95_from_percentiles(
                row[('Request Latency', 'Successful Sec', 'Percentiles')])

            metric = {
                'run_index': int(run_index_val),
                'strategy': str(strategy_val),
                'requests_sec_mean': float(requests_sec_mean),
                'requests_sec_p95': requests_sec_p95,
                'concurrency_mean': float(concurrency_mean),
                'concurrency_p95': concurrency_p95,
                'throughput_tokens_sec_mean': float(throughput_mean),
                'throughput_tokens_sec_p95': throughput_p95,
                'ttft_mean': float(ttft_mean),
                'ttft_p95': ttft_p95,
                'tpot_mean': float(tpot_mean),
                'tpot_p95': tpot_p95,
                'latency_mean': float(latency_mean),
                'latency_p95': latency_p95,
                'successful_requests': int(successful),
            }
            metrics.append(metric)
        except (ValueError, KeyError, AttributeError, TypeError) as e:
            # Skip problematic rows silently (likely header rows)
            continue

    return pd.DataFrame(metrics)

def parse_json_file(json_path):
    """Parse guidellm JSON benchmark file as fallback when CSV is corrupted."""
    with open(json_path, 'r') as f:
        data = json.load(f)

    metrics = []

    for idx, bench in enumerate(data['benchmarks']):
        try:
            m = bench['metrics']

            # Extract statistics
            def get_stat(metric_dict, stat_name):
                if isinstance(metric_dict, dict) and 'successful' in metric_dict:
                    return metric_dict['successful'].get(stat_name)
                return None

            def get_p95(metric_dict):
                """Extract P95 from percentiles dictionary."""
                if isinstance(metric_dict, dict) and 'successful' in metric_dict:
                    successful = metric_dict['successful']
                    if 'percentiles' in successful and isinstance(successful['percentiles'], dict):
                        return successful['percentiles'].get('p95')
                return None

            # Get mean values
            req_per_sec = get_stat(m['requests_per_second'], 'mean')
            concurrency = get_stat(m['request_concurrency'], 'mean')
            output_tok_per_sec = get_stat(m['output_tokens_per_second'], 'mean')
            ttft = get_stat(m['time_to_first_token_ms'], 'mean')
            tpot = get_stat(m['time_per_output_token_ms'], 'mean')
            latency = get_stat(m['request_latency'], 'mean')
            successful = m['request_totals']['successful']

            # Get P95 values from percentiles
            req_per_sec_p95 = get_p95(m['requests_per_second'])
            concurrency_p95 = get_p95(m['request_concurrency'])
            output_tok_per_sec_p95 = get_p95(m['output_tokens_per_second'])
            ttft_p95 = get_p95(m['time_to_first_token_ms'])
            tpot_p95 = get_p95(m['time_per_output_token_ms'])
            latency_p95 = get_p95(m['request_latency'])

            # Get strategy from config
            strategy = bench.get('config', {}).get('mode', 'unknown')

            metric = {
                'run_index': idx,
                'strategy': str(strategy),
                'requests_sec_mean': float(req_per_sec) if req_per_sec is not None else 0.0,
                'requests_sec_p95': float(req_per_sec_p95) if req_per_sec_p95 is not None else 0.0,
                'concurrency_mean': float(concurrency) if concurrency is not None else 0.0,
                'concurrency_p95': float(concurrency_p95) if concurrency_p95 is not None else 0.0,
                'throughput_tokens_sec_mean': float(output_tok_per_sec) if output_tok_per_sec is not None else 0.0,
                'throughput_tokens_sec_p95': float(output_tok_per_sec_p95) if output_tok_per_sec_p95 is not None else 0.0,
                'ttft_mean': float(ttft) if ttft is not None else 0.0,
                'ttft_p95': float(ttft_p95) if ttft_p95 is not None else 0.0,
                'tpot_mean': float(tpot) if tpot is not None else 0.0,
                'tpot_p95': float(tpot_p95) if tpot_p95 is not None else 0.0,
                'latency_mean': float(latency) if latency is not None else 0.0,
                'latency_p95': float(latency_p95) if latency_p95 is not None else 0.0,
                'successful_requests': int(successful) if successful is not None else 0,
            }
            metrics.append(metric)
        except (KeyError, AttributeError, TypeError, ValueError) as e:
            print(f"Warning: Failed to parse benchmark {idx} from JSON: {e}")
            continue

    return pd.DataFrame(metrics)

def load_all_results(base_path="/Users/Xeon-single-platform"):
    """Load all benchmark results from the directory."""
    base = Path(base_path)

    # Check if directory exists
    if not base.exists():
        raise FileNotFoundError(f"Data directory not found: {base_path}")

    if not base.is_dir():
        raise ValueError(f"Path is not a directory: {base_path}")

    all_results = []

    # Pattern to extract test info from directory name
    pattern = r'T(\d+)-(llama|tinyllama)-(\d+)c-nopreempt'

    for test_dir in sorted(base.iterdir()):
        if not test_dir.is_dir() or test_dir.name.startswith('.'):
            continue

        match = re.match(pattern, test_dir.name)
        if not match:
            continue

        test_num, model, cores = match.groups()

        csv_file = test_dir / f"{test_dir.name}.csv"
        json_file = test_dir / "benchmarks.json"

        print(f"Processing {test_dir.name}...")
        try:
            # Try CSV first
            if csv_file.exists():
                df = parse_csv_file(csv_file)
                metrics_df = extract_metrics(df)

                # Check if data looks corrupted (throughput decreases as requests increase)
                # This is a simple heuristic to detect scrambled CSV data
                if len(metrics_df) > 2:
                    sorted_df = metrics_df.sort_values('requests_sec_mean')
                    throughputs = sorted_df['throughput_tokens_sec_mean'].values
                    # If throughput drops to near-zero for higher request rates, data is likely corrupted
                    if throughputs[-1] < throughputs[0] / 10 and throughputs[-1] < 1.0:
                        print(f"  WARNING: CSV data appears corrupted (throughput drops with increasing load)")
                        print(f"  Falling back to JSON file...")
                        raise ValueError("Corrupted CSV data")
            else:
                raise FileNotFoundError("CSV not found")

        except Exception as csv_error:
            # Fall back to JSON if CSV fails or is corrupted
            if json_file.exists():
                print(f"  Using JSON file instead of CSV")
                metrics_df = parse_json_file(json_file)
            else:
                print(f"  Error: No valid data source found for {test_dir.name}")
                print(f"  CSV error: {csv_error}")
                continue

        # Add metadata
        metrics_df['test_name'] = test_dir.name
        metrics_df['model'] = 'Llama' if model == 'llama' else 'TinyLlama'
        metrics_df['cores'] = int(cores)
        metrics_df['test_num'] = int(test_num)

        all_results.append(metrics_df)

    if not all_results:
        raise ValueError("No results found!")

    return pd.concat(all_results, ignore_index=True)

def create_comparison_plots(df, output_dir="benchmark_reports"):
    """Create comparison plots for all metrics.

    Note: This function selects ONLY the maximum throughput run from each test
    (the run with highest mean throughput at highest load level). This shows peak
    throughput but worst latency. For full sweep curve analysis showing all data
    points and latency tradeoffs, use analyze_sweep_curves.py instead.
    """
    Path(output_dir).mkdir(exist_ok=True)

    # Filter to get the maximum throughput run for each configuration
    # For sweep tests with multiple load levels, this selects only the highest throughput run
    # (which is at the highest load level with worst latency)
    best_runs = df.loc[df.groupby('test_name')['throughput_tokens_sec_mean'].idxmax()]

    # Get available models and assign colors
    models = sorted(best_runs['model'].unique())
    colors = {'Llama': '#5B9BD5', 'TinyLlama': '#ED7D31'}

    # Metrics: (mean_col, p95_col, title, ylabel, higher_is_better, show_p95)
    # Note: P95 doesn't make sense for throughput/rate metrics (shows instantaneous
    # peaks rather than sustained performance)
    metrics = [
        ('requests_sec_mean', 'requests_sec_p95', 'Requests/Second ↑',
         'Requests per Second', True, False),  # Don't show P95 for rates
        ('throughput_tokens_sec_mean', 'throughput_tokens_sec_p95',
         'Throughput (tokens/sec) ↑', 'Tokens per Second', True, False),  # Don't show P95
        ('ttft_mean', 'ttft_p95', 'TTFT (ms) ↓',
         'Time to First Token (ms)', False, True),  # Show P95 for latency
        ('tpot_mean', 'tpot_p95', 'TPOT (ms) ↓',
         'Time per Output Token (ms)', False, True),  # Show P95 for latency
        ('latency_mean', 'latency_p95', 'Latency (sec) ↓',
         'Request Latency (seconds)', False, True),  # Show P95 for latency
    ]

    for mean_col, p95_col, metric_name, ylabel, higher_is_better, show_p95 in metrics:
        # Create figure with 1 or 2 subplots depending on whether we show P95
        if show_p95:
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
        else:
            fig, ax1 = plt.subplots(1, 1, figsize=(10, 6))

        # Left plot: Mean values
        plot_data_mean = best_runs.pivot(index='cores', columns='model', values=mean_col)
        x = np.arange(len(plot_data_mean.index))
        width = 0.35 if len(models) > 1 else 0.6

        # Plot bars for each model
        all_bars_mean = []
        for i, model in enumerate(models):
            if model in plot_data_mean.columns:
                offset = (i - len(models)/2 + 0.5) * width if len(models) > 1 else 0
                bars = ax1.bar(x + offset, plot_data_mean[model], width,
                              label=model, alpha=0.8, color=colors.get(model, '#999999'))
                all_bars_mean.append(bars)

        ax1.set_xlabel('Number of Cores', fontsize=12)
        ax1.set_ylabel(ylabel if not show_p95 else f'{ylabel} (Mean)', fontsize=12)
        ax1.set_title(metric_name if not show_p95 else f'{metric_name} - Mean',
                     fontsize=13, fontweight='bold')
        ax1.set_xticks(x)
        ax1.set_xticklabels([f'{cores}c' for cores in plot_data_mean.index])
        ax1.legend()
        ax1.grid(axis='y', alpha=0.3)

        # Add value labels on bars
        for bars in all_bars_mean:
            for bar in bars:
                height = bar.get_height()
                if not np.isnan(height):
                    ax1.text(bar.get_x() + bar.get_width()/2., height,
                           f'{height:.1f}',
                           ha='center', va='bottom', fontsize=9)

        # Right plot: P95 values (only for latency metrics)
        if show_p95:
            plot_data_p95 = best_runs.pivot(index='cores', columns='model', values=p95_col)

            all_bars_p95 = []
            for i, model in enumerate(models):
                if model in plot_data_p95.columns:
                    offset = (i - len(models)/2 + 0.5) * width if len(models) > 1 else 0
                    bars = ax2.bar(x + offset, plot_data_p95[model], width,
                                  label=model, alpha=0.8, color=colors.get(model, '#999999'))
                    all_bars_p95.append(bars)

            ax2.set_xlabel('Number of Cores', fontsize=12)
            ax2.set_ylabel(f'{ylabel} (P95)', fontsize=12)
            ax2.set_title(f'{metric_name} - P95', fontsize=13, fontweight='bold')
            ax2.set_xticks(x)
            ax2.set_xticklabels([f'{cores}c' for cores in plot_data_p95.index])
            ax2.legend()
            ax2.grid(axis='y', alpha=0.3)

            # Add value labels on bars
            for bars in all_bars_p95:
                for bar in bars:
                    height = bar.get_height()
                    if not np.isnan(height):
                        ax2.text(bar.get_x() + bar.get_width()/2., height,
                               f'{height:.1f}',
                               ha='center', va='bottom', fontsize=9)

        plt.tight_layout()
        plt.savefig(f'{output_dir}/{mean_col}_comparison.png', dpi=300, bbox_inches='tight')
        print(f"Saved {mean_col}_comparison.png")
        plt.close()

    # Create a combined performance overview (Mean values only)
    # With 5 metrics, use a 2x3 grid (last position will be empty)
    fig, axes = plt.subplots(2, 3, figsize=(18, 10))
    fig.suptitle('Performance Metrics Overview (Mean Values)',
                 fontsize=16, fontweight='bold')

    for idx, (mean_col, p95_col, metric_name, ylabel, higher_is_better, show_p95) in enumerate(metrics):
        ax = axes[idx // 3, idx % 3]

        plot_data = best_runs.pivot(index='cores', columns='model', values=mean_col)
        x = np.arange(len(plot_data.index))
        width = 0.35 if len(models) > 1 else 0.6

        for i, model in enumerate(models):
            if model in plot_data.columns:
                offset = (i - len(models)/2 + 0.5) * width if len(models) > 1 else 0
                ax.bar(x + offset, plot_data[model], width, label=model,
                      alpha=0.8, color=colors.get(model, '#999999'))

        ax.set_xlabel('Cores')
        ax.set_ylabel(ylabel)
        ax.set_title(metric_name, fontweight='bold')
        ax.set_xticks(x)
        ax.set_xticklabels([f'{cores}c' for cores in plot_data.index])
        ax.legend()
        ax.grid(axis='y', alpha=0.3)

    # Hide the last empty subplot
    axes[1, 2].set_visible(False)

    plt.tight_layout()
    plt.savefig(f'{output_dir}/performance_overview.png', dpi=300, bbox_inches='tight')
    print("Saved performance_overview.png")
    plt.close()

def create_summary_tables(df, output_dir="benchmark_reports"):
    """Create summary tables.

    Note: This function selects ONLY the maximum throughput run from each test
    (highest load level with worst latency). For full sweep data showing all load
    levels, use analyze_sweep_curves.py.
    """
    Path(output_dir).mkdir(exist_ok=True)

    # Get maximum throughput runs (highest throughput run from each test)
    # For sweep tests, this excludes all other load level data points
    best_runs = df.loc[df.groupby('test_name')['throughput_tokens_sec_mean'].idxmax()]

    # Create comprehensive summary tables with both mean and P95
    summary_mean = best_runs[['model', 'cores', 'requests_sec_mean',
                               'throughput_tokens_sec_mean', 'ttft_mean', 'tpot_mean',
                               'latency_mean', 'successful_requests']].copy()

    summary_mean.columns = ['Model', 'Cores', 'Req/s (mean)',
                            'Throughput tok/s (mean)', 'TTFT ms (mean)',
                            'TPOT ms (mean)', 'Latency s (mean)', 'Successful Reqs']

    summary_p95 = best_runs[['model', 'cores', 'requests_sec_p95',
                              'throughput_tokens_sec_p95', 'ttft_p95', 'tpot_p95',
                              'latency_p95']].copy()

    summary_p95.columns = ['Model', 'Cores', 'Req/s (P95)',
                           'Throughput tok/s (P95)', 'TTFT ms (P95)',
                           'TPOT ms (P95)', 'Latency s (P95)']

    # Merge mean and P95 for combined table
    summary_combined = best_runs[['model', 'cores', 'requests_sec_mean',
                                   'requests_sec_p95',
                                   'throughput_tokens_sec_mean',
                                   'throughput_tokens_sec_p95',
                                   'ttft_mean', 'ttft_p95', 'tpot_mean', 'tpot_p95',
                                   'latency_mean', 'latency_p95',
                                   'successful_requests']].copy()

    summary_combined.columns = ['Model', 'Cores', 'Req/s (↑ mean)', 'Req/s (P95)',
                                 'Throughput tok/s (↑ mean)',
                                 'Throughput tok/s (P95)',
                                 'TTFT ms (↓ mean)', 'TTFT ms (P95)',
                                 'TPOT ms (↓ mean)', 'TPOT ms (P95)',
                                 'Latency s (↓ mean)', 'Latency s (P95)',
                                 'Successful Reqs']

    summary_combined = summary_combined.sort_values(['Model', 'Cores'])
    summary_mean = summary_mean.sort_values(['Model', 'Cores'])
    summary_p95 = summary_p95.sort_values(['Model', 'Cores'])

    # Save to CSV files
    summary_combined.to_csv(f'{output_dir}/performance_summary_combined.csv',
                            index=False, float_format='%.2f')
    summary_mean.to_csv(f'{output_dir}/performance_summary_mean.csv',
                        index=False, float_format='%.2f')
    summary_p95.to_csv(f'{output_dir}/performance_summary_p95.csv',
                       index=False, float_format='%.2f')
    print("Saved performance_summary_*.csv files")

    # Create nicely formatted text tables
    with open(f'{output_dir}/performance_summary.txt', 'w') as f:
        f.write("=" * 160 + "\n")
        f.write("VLLM CPU Performance Evaluation - Combined Summary (Mean & P95)\n")
        f.write("=" * 160 + "\n\n")
        f.write(summary_combined.to_string(index=False))
        f.write("\n\n" + "=" * 160 + "\n\n")

        f.write("=" * 120 + "\n")
        f.write("Mean Values Only\n")
        f.write("=" * 120 + "\n\n")
        f.write(summary_mean.to_string(index=False))
        f.write("\n\n" + "=" * 120 + "\n\n")

        f.write("=" * 120 + "\n")
        f.write("P95 Values Only\n")
        f.write("=" * 120 + "\n\n")
        f.write(summary_p95.to_string(index=False))
        f.write("\n\n" + "=" * 120 + "\n")

    print("Saved performance_summary.txt")

    # Create pivot tables for each metric (mean and P95)
    metrics_mean = {
        'Requests/sec (mean) ↑': 'Req/s (mean)',
        'Throughput tok/s (mean) ↑': 'Throughput tok/s (mean)',
        'TTFT ms (mean) ↓': 'TTFT ms (mean)',
        'TPOT ms (mean) ↓': 'TPOT ms (mean)',
        'Latency s (mean) ↓': 'Latency s (mean)',
    }

    metrics_p95 = {
        'Requests/sec (P95) ↑': 'Req/s (P95)',
        'Throughput tok/s (P95) ↑': 'Throughput tok/s (P95)',
        'TTFT ms (P95) ↓': 'TTFT ms (P95)',
        'TPOT ms (P95) ↓': 'TPOT ms (P95)',
        'Latency s (P95) ↓': 'Latency s (P95)',
    }

    with open(f'{output_dir}/pivot_tables.txt', 'w') as f:
        f.write("=" * 80 + "\n")
        f.write("MEAN VALUES - Pivot Tables by Model and Core Count\n")
        f.write("=" * 80 + "\n")
        for metric_name, col_name in metrics_mean.items():
            f.write(f"\n{'=' * 80}\n")
            f.write(f"{metric_name}\n")
            f.write(f"{'=' * 80}\n")
            pivot = summary_mean.pivot(index='Model', columns='Cores', values=col_name)
            f.write(pivot.to_string(float_format='%.2f'))
            f.write("\n")

        f.write("\n\n" + "=" * 80 + "\n")
        f.write("P95 VALUES - Pivot Tables by Model and Core Count\n")
        f.write("=" * 80 + "\n")
        for metric_name, col_name in metrics_p95.items():
            f.write(f"\n{'=' * 80}\n")
            f.write(f"{metric_name}\n")
            f.write(f"{'=' * 80}\n")
            pivot = summary_p95.pivot(index='Model', columns='Cores', values=col_name)
            f.write(pivot.to_string(float_format='%.2f'))
            f.write("\n")

    print("Saved pivot_tables.txt")

    return summary_combined

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Analyze guidellm benchmark results and generate performance reports',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use default data directory
  python3 analyze_benchmark_results.py

  # Specify custom data directory
  python3 analyze_benchmark_results.py /path/to/benchmark/data

  # Specify custom output directory
  python3 analyze_benchmark_results.py --output-dir my_reports

  # Both custom directories
  python3 analyze_benchmark_results.py /path/to/data --output-dir my_reports
        """
    )

    parser.add_argument(
        'data_dir',
        nargs='?',
        default='/Users/Xeon-single-platform',
        help='Path to directory containing benchmark results (default: /Users/Xeon-single-platform)'
    )

    parser.add_argument(
        '--output-dir',
        default='benchmark_reports',
        help='Directory for output reports (default: benchmark_reports)'
    )

    return parser.parse_args()


def main():
    """Main execution function."""
    args = parse_args()

    print(f"Data directory: {args.data_dir}")
    print(f"Output directory: {args.output_dir}")
    print("\nLoading benchmark results...")

    try:
        df = load_all_results(base_path=args.data_dir)
    except FileNotFoundError as e:
        print(f"\nError: {e}")
        print(f"Please check that '{args.data_dir}' exists and contains benchmark data.")
        sys.exit(1)
    except ValueError as e:
        print(f"\nError: {e}")
        sys.exit(1)

    print(f"\nLoaded {len(df)} benchmark runs from {df['test_name'].nunique()} tests")
    print(f"Models: {df['model'].unique()}")
    print(f"Core counts: {sorted(df['cores'].unique())}")

    print("\nCreating visualizations...")
    create_comparison_plots(df, output_dir=args.output_dir)

    print("\nGenerating summary tables...")
    summary = create_summary_tables(df, output_dir=args.output_dir)

    print("\n" + "=" * 80)
    print("Summary Preview:")
    print("=" * 80)
    print(summary.to_string(index=False))

    print("\n" + "=" * 80)
    print(f"Analysis complete! Check the '{args.output_dir}' directory for outputs.")
    print("=" * 80)


if __name__ == "__main__":
    main()
