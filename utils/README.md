# Utils

This directory contains utility scripts for benchmark analysis and reporting.

## Important: Maximum Throughput vs. Full Sweep Analysis

The analysis scripts in this directory fall into two categories:

1. **Maximum Throughput Analysis** (analyze_benchmark_results.py, compare_platforms.py)
   - Selects ONLY the highest throughput run from each test (highest load level)
   - Shows maximum achievable throughput (but with worst latency)
   - Provides clean single-number comparisons across core counts
   - **Limitation**: Does not show how performance varies with load or latency tradeoffs

2. **Full Sweep Analysis** (analyze_sweep_curves.py, compare_sweep_platforms.py)
   - Uses ALL data points from sweep tests
   - Shows complete performance curves as load increases
   - Reveals saturation behavior and performance degradation
   - **Use this** to understand how systems perform under varying load levels

When guidellm runs sweep tests, it generates ~8-9 data points per core configuration
at different load levels. The "maximum throughput" scripts select only the highest
throughput point (highest load), while the "sweep" scripts use all of them.

## Scripts

### analyze_benchmark_results.py

Analyzes guidellm sweep test results and generates maximum throughput performance
reports for a single platform.

**⚠️ Important**: This script uses ONLY the maximum throughput run
(highest load level) from each test. This shows peak throughput but
worst latency. For full sweep curve analysis showing all load levels
and latency tradeoffs, use
[analyze_sweep_curves.py](#analyze_sweep_curvespy) instead.

**Usage:**

```bash
# From project root - analyze single platform
python3 utils/analyze_benchmark_results.py /Users/Xeon-multi-platform

# Specify custom output directory
python3 utils/analyze_benchmark_results.py /Users/EPYC-multi-platform \
  --output-dir benchmark_reports_epyc
```

**What it does:**

- Parses guidellm CSV benchmark results
- Extracts mean and P95 metrics for:
  - Requests/second
  - Throughput (tokens/sec)
  - Time to First Token (TTFT)
  - Time per Output Token (TPOT)
  - Request Latency
- Generates visualizations (PNG charts)
- Creates summary tables (CSV and TXT)
- Outputs all reports to specified directory

**Requirements:**

```bash
pip install pandas matplotlib seaborn numpy
```

**Full Documentation:**
See [BENCHMARK_ANALYSIS_GUIDE.md](BENCHMARK_ANALYSIS_GUIDE.md) for complete
usage instructions, customization options, and troubleshooting.

### compare_platforms.py

Compares maximum throughput performance between Intel Xeon and AMD EPYC platforms.

**⚠️ Important**: This script uses ONLY the maximum throughput run
(highest load level) from each test. This shows peak throughput but worst
latency for each platform. For full sweep curve comparison showing how
platforms perform under varying load, use
[compare_sweep_platforms.py](#compare_sweep_platformspy) instead.

**Usage:**

```bash
# From project root - use default directories
python3 utils/compare_platforms.py

# Specify custom directories
python3 utils/compare_platforms.py \
  --intel-dir /Users/Xeon-multi-platform \
  --amd-dir /Users/EPYC-multi-platform \
  --output-dir benchmark_reports_comparison
```

**What it does:**

- Loads benchmark results from both Intel and AMD platforms
- Creates side-by-side comparison charts for all metrics
- Generates performance ratio analysis at common core counts
- Shows scaling differences between architectures
- Outputs all comparison reports to `benchmark_reports_comparison/`

**Output Files:**

- `platform_comparison_overview.png` - 5-panel comparison overview
- `*_platform_comparison.png` - Individual metric comparisons
- `platform_comparison_summary.csv` - Combined performance data
- `platform_comparison_summary.txt` - Formatted summary table
- `platform_comparison_analysis.txt` - Performance ratio analysis

### analyze_sweep_curves.py

Analyzes full sweep test performance curves showing how metrics vary with load.

**Usage:**

```bash
# From project root - analyze sweep curves
python3 utils/analyze_sweep_curves.py /Users/Xeon-multi-platform

# Specify custom output directory
python3 utils/analyze_sweep_curves.py /Users/EPYC-multi-platform \
  --output-dir benchmark_reports_sweep_epyc
```

**What it does:**

- Plots ALL sweep test data points (not just the best run)
- Shows performance curves as load increases
- Reveals saturation behavior and performance "knee"
- Generates efficiency analysis (achieved vs target rate)
- Creates per-metric load curves for each core configuration

**Output Files:**

- `*_sweep_overview.png` - 4-panel overview of performance curves
- `*_vs_load.png` - Individual metric curves vs load
- `*_efficiency_analysis.png` - Load efficiency analysis
- `sweep_summary.csv` - Summary of sweep test ranges
- `sweep_summary.txt` - Formatted sweep summary

**Key Difference from analyze_benchmark_results.py:**

The main analysis script selects only the maximum throughput run (highest load,
worst latency) to compare core counts. This script plots the full sweep curve
to show how each core configuration performs under varying load levels.

### compare_sweep_platforms.py

Compares full sweep test performance curves between Intel Xeon and AMD EPYC platforms.

**Usage:**

```bash
# From project root - use default directories
python3 utils/compare_sweep_platforms.py

# Specify custom directories
python3 utils/compare_sweep_platforms.py \
  --intel-dir /Users/Xeon-multi-platform \
  --amd-dir /Users/EPYC-multi-platform \
  --output-dir benchmark_reports_sweep_comparison
```

**What it does:**

- Loads sweep test results from both Intel and AMD platforms
- Creates side-by-side sweep curve comparisons at common core counts
- Shows platform-specific sweep curves for all core configurations
- Generates saturation behavior analysis comparing how platforms handle load
- Outputs all comparison reports to `benchmark_reports_sweep_comparison/`

**Output Files:**

- `platform_sweep_comparison_<cores>c.png` - Direct comparison at common core counts
- `platform_sweep_*.png` - Side-by-side sweep curves for each metric
- `platform_saturation_comparison.png` - Saturation behavior analysis
- `sweep_comparison_summary.csv` - Combined sweep test summary
- `sweep_comparison_summary.txt` - Formatted summary table

**Key Difference from compare_platforms.py:**

The regular platform comparison shows only the maximum throughput run from each
test (highest load, worst latency). This script plots the full sweep curves to
reveal how each platform's performance varies with load and where saturation occurs.

## Directory Structure

```text
utils/
├── README.md                        # This file
├── BENCHMARK_ANALYSIS_GUIDE.md      # Complete guide for benchmark analysis
├── analyze_benchmark_results.py    # Single platform analysis script
├── compare_platforms.py             # Multi-platform comparison script
├── analyze_sweep_curves.py          # Sweep performance curve analysis
└── compare_sweep_platforms.py       # Intel vs AMD sweep curve comparison
```

## Adding New Utilities

When adding new utility scripts to this directory:

1. Add a clear docstring at the top of the file
2. Update this README with usage instructions
3. Add any new dependencies to requirements (if needed)
4. Follow the existing code style and patterns
