#!/usr/bin/env python3
"""Extract per-benchmark timings from benchmarks.json and add to test-metadata.json"""

import json
import sys
from pathlib import Path


def main():
    if len(sys.argv) != 3:
        print("Usage: extract_benchmark_timings.py <benchmarks.json> <test-metadata.json>")
        sys.exit(1)

    benchmarks_file = Path(sys.argv[1])
    metadata_file = Path(sys.argv[2])

    try:
        # Read benchmarks.json
        with open(benchmarks_file, 'r') as f:
            bench_data = json.load(f)

        # Read current metadata
        with open(metadata_file, 'r') as f:
            metadata = json.load(f)

        # Extract rates from args
        rates = bench_data.get('args', {}).get('rate', [])

        # Extract timing info from benchmarks
        benchmark_timings = []
        total_duration = 0
        for i, benchmark in enumerate(bench_data.get('benchmarks', [])):
            duration = benchmark['duration']
            total_duration += duration
            timing = {
                'benchmark_index': i,
                'rate': rates[i] if i < len(rates) else None,
                'duration_seconds': duration,
                'warmup_duration_seconds': benchmark['warmup_duration'],
                'cooldown_duration_seconds': benchmark['cooldown_duration'],
                'start_time': benchmark['start_time'],
                'end_time': benchmark['end_time'],
                'successful_requests': benchmark['scheduler_state']['successful_requests'],
                'total_requests': benchmark['scheduler_state']['processed_requests']
            }
            benchmark_timings.append(timing)

        # Calculate total test duration
        hours = int(total_duration // 3600)
        minutes = int((total_duration % 3600) // 60)
        seconds = int(total_duration % 60)
        test_duration_string = f"{hours}:{minutes:02d}:{seconds:02d}"

        # Add to metadata
        metadata['benchmark_timings'] = benchmark_timings
        metadata['test_duration_seconds'] = int(total_duration)
        metadata['test_duration'] = test_duration_string

        # Write updated metadata
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)

        print(f"✓ Added {len(benchmark_timings)} benchmark timings to "
              f"metadata")
        print(f"✓ Total test duration: {test_duration_string} "
              f"({int(total_duration)}s)")
        return 0

    except FileNotFoundError as e:
        print(f"Warning: File not found: {e.filename}")
        return 0  # Don't fail the playbook

    except Exception as e:
        print(f"Warning: Could not extract benchmark timings: {e}")
        return 0  # Don't fail the playbook


if __name__ == '__main__':
    sys.exit(main())
