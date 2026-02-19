# Deprecated Scripts

This directory contains legacy platform comparison scripts that have been superseded by the unified comparison tool.

## Deprecated Scripts

All scripts in this directory are **deprecated** and maintained only for reference. New comparisons should use the main tool.

### Legacy Scripts:
- `analyze_sweep_curves.py` - Legacy sweep curve analysis
- `compare_platforms.py` - Legacy platform comparison
- `compare_sweep_platforms.py` - Legacy sweep platform comparison
- `create_executive_summary.py` - Legacy executive summary generation
- `create_key_findings_slide.py` - Legacy key findings slide generation
- `create_sweep_bar_charts.py` - Legacy sweep bar chart generation
- `create_sweep_unified_comparison.py` - Legacy unified comparison (2 platforms only)
- `create_unified_comparison.py` - Legacy unified comparison

## Current Tool

**Use instead:** `../create_three_platform_sweep_comparison.py`

The new unified tool provides:
- Flexible 2 or 3 platform comparisons
- Comprehensive percentile analysis (P50/P95)
- Unified sweep curves across all platforms and core counts
- Per-core comparisons
- Latency and throughput percentile distributions
- Performance summary tables

See `../README.md` for usage examples.

## Why Deprecated?

These scripts had limitations:
- Hardcoded for specific platform combinations
- Limited or no percentile analysis
- Separate scripts for 2 vs 3 platform comparisons
- Inconsistent visualization styles
- Redundant functionality across multiple scripts

The new unified tool addresses all these issues in a single, flexible script.
