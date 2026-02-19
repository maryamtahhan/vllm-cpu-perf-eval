# Benchmark Analysis Utilities

This directory contains utility scripts for benchmark analysis and reporting.

## Quick Start

**For platform comparisons (2 or 3 platforms):**
```bash
# Compare two platforms
python3 utils/create_three_platform_sweep_comparison.py \
  --platform1-dir /path/to/platform1 --platform1-name "Intel Xeon" \
  --platform2-dir /path/to/platform2 --platform2-name "AMD EPYC" \
  --output-dir benchmark_reports

# Compare three platforms (legacy mode)
python3 utils/create_three_platform_sweep_comparison.py \
  --intel-dir /Users/summarization/xeon-multi-platform \
  --epyc-zendnn-dir /Users/summarization/epyc-multi-platform-zendnn \
  --epyc-vllm-dir /Users/summarization/epyc-multi-platform-vllm \
  --output-dir benchmark_reports_three_platform
```

## Active Scripts

### create_three_platform_sweep_comparison.py

**Main tool** for comprehensive platform comparisons with percentile analysis.

Generates unified benchmark visualizations for 2 or 3 platforms:
- Full sweep curves across all platforms and core counts
- Per-core comparisons showing platform performance side-by-side
- Latency percentile distributions (P50/P95) for TTFT, TPOT, and Total Latency
- Throughput percentile distributions (P50/P95)
- Performance summary tables

**Features:**
- Extracts P50/P95 percentiles from GuideLL M results
- Emphasizes P95 (solid lines) over P50 (dashed) to highlight worst-case performance
- Supports both generic mode (--platform1/2/3) and legacy mode (--intel-dir/--epyc-zendnn-dir)
- Flexible configuration with custom platform names and colors

**Usage (Generic Mode):**
```bash
# Two platforms
python3 utils/create_three_platform_sweep_comparison.py \
  --platform1-dir /path/to/platform1 \
  --platform1-name "Intel Xeon" \
  --platform1-color "#0071C5" \
  --platform2-dir /path/to/platform2 \
  --platform2-name "AMD EPYC" \
  --platform2-color "#ED1C24" \
  --output-dir benchmark_reports

# Three platforms
python3 utils/create_three_platform_sweep_comparison.py \
  --platform1-dir /path/to/platform1 \
  --platform1-name "Intel Xeon" \
  --platform1-color "#0071C5" \
  --platform2-dir /path/to/platform2 \
  --platform2-name "EPYC ZenDNN" \
  --platform2-color "#ED1C24" \
  --platform3-dir /path/to/platform3 \
  --platform3-name "EPYC vLLM" \
  --platform3-color "#00AA00" \
  --output-dir benchmark_reports
```

**Usage (Legacy Mode - backward compatible):**
```bash
python3 utils/create_three_platform_sweep_comparison.py \
  --intel-dir /Users/summarization/xeon-multi-platform \
  --epyc-zendnn-dir /Users/summarization/epyc-multi-platform-zendnn \
  --epyc-vllm-dir /Users/summarization/epyc-multi-platform-vllm \
  --output-dir benchmark_reports_three_platform
```

**Output Files:**
- `three_platform_sweep_curves_all_cores.png` - Unified sweep curves showing all platforms
- `comparison_XXcores.png` - Per-core comparison for each core count
- `percentile_overview_XXcores.png` - Latency P50/P95 for each core count (TTFT, TPOT, Total)
- `throughput_percentile_XXcores.png` - Throughput P50/P95 for each core count
- `unified_percentile_overview_ttft.png` - TTFT P50/P95 across all platforms/cores
- `platform_summary.csv` - Performance summary table (CSV)
- `platform_summary.txt` - Performance summary table (formatted text)

### analyze_benchmark_results.py

Core analysis library used by other scripts. Can also be used standalone for single-platform analysis.

**Usage:**
```bash
# Analyze single platform
python3 utils/analyze_benchmark_results.py /path/to/benchmark/results

# Specify custom output directory
python3 utils/analyze_benchmark_results.py /path/to/results \
  --output-dir benchmark_reports_custom
```

**What it does:**
- Parses GuideLL M CSV benchmark results
- Extracts mean and P95 metrics for throughput, latency, TTFT, TPOT
- Generates visualizations and summary tables
- Used as a library by create_three_platform_sweep_comparison.py

## Requirements

```bash
pip install pandas matplotlib seaborn numpy
```

## Understanding GuideLL M Sweep Tests

GuideLL M sweep tests generate ~8-9 data points per core configuration at different load levels. The scripts in this directory analyze:

1. **Full Sweep Curves** - How performance varies with increasing load
2. **Percentile Distributions** - P50 (median) and P95 (worst case for 95% of requests)
3. **Platform Comparisons** - Side-by-side performance across platforms
4. **Saturation Behavior** - Where and how performance degrades under load

**Key Metrics:**
- **Throughput** (tokens/sec) - Higher is better
- **TTFT** (Time to First Token, ms) - Lower is better
- **TPOT** (Time per Output Token, ms) - Lower is better
- **Latency** (Total request latency, sec) - Lower is better

**Percentile Interpretation:**
- **P50 (Median)** - Typical performance, 50% of requests complete within this time/throughput
- **P95** - Reliability floor, 95% of requests meet this performance level
  - For throughput (higher is better): P95 < P50 (P95 shows minimum throughput 95% of time)
  - For latency (lower is better): P95 > P50 (P95 shows maximum latency 95% of time)

## Directory Structure

```text
utils/
├── README.md                                 # This file
├── BENCHMARK_ANALYSIS_GUIDE.md               # Complete analysis guide
├── analyze_benchmark_results.py              # Core analysis library
├── create_three_platform_sweep_comparison.py # Main comparison tool (2 or 3 platforms)
└── deprecated/                               # Deprecated legacy scripts
    ├── README.md                             # Documentation for deprecated scripts
    ├── analyze_sweep_curves.py
    ├── compare_platforms.py
    ├── compare_sweep_platforms.py
    ├── create_executive_summary.py
    ├── create_key_findings_slide.py
    ├── create_sweep_bar_charts.py
    ├── create_sweep_unified_comparison.py
    └── create_unified_comparison.py
```

## Deprecated Scripts

Legacy scripts have been moved to `deprecated/` directory. They are maintained only for reference.

**Use `create_three_platform_sweep_comparison.py` for all new comparisons.**

See [deprecated/README.md](deprecated/README.md) for information about legacy scripts.

## Full Documentation

See [BENCHMARK_ANALYSIS_GUIDE.md](BENCHMARK_ANALYSIS_GUIDE.md) for:
- Complete usage instructions
- Customization options
- Troubleshooting
- Performance analysis methodology
- Understanding GuideLL M output formats

## Adding New Utilities

When adding new utility scripts:

1. Add clear docstring at the top of the file
2. Update this README with usage instructions
3. Add dependencies to requirements if needed
4. Follow existing code style and patterns
5. Consider whether it should be part of the main comparison tool vs. a separate utility
