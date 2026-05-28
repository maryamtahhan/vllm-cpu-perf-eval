"""vLLM server metrics parser.

This module provides shared functionality for parsing vLLM metrics from
vllm-metrics.json files. It supports both detailed statistical analysis and
simple last-sample extraction.
"""

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .json_utils import load_json_safe


class VLLMMetricsParser:
    """Parser for vLLM server-side metrics.

    Parses Prometheus-format metrics exported by vLLM server, including:
    - Resource usage (CPU, memory, KV cache)
    - Token counts (prompt, generation)
    - Latency metrics (TTFT, TPOT, E2E)
    - Cache performance (prefix cache hit rates)
    - Queue metrics (waiting, running requests)
    """

    def __init__(self, metrics_path: Union[str, Path]):
        """Initialize parser.

        Args:
            metrics_path: Path to vllm-metrics.json file
        """
        self.metrics_path = Path(metrics_path)
        self.data = load_json_safe(metrics_path, default={})
        self.samples = self.data.get("samples", [])

    def get_metric_values(
        self,
        metric_name: str,
        label_filter: Optional[Dict[str, str]] = None
    ) -> List[float]:
        """Extract all values for a metric across samples.

        Args:
            metric_name: Name of metric to extract
            label_filter: Optional label filter (e.g., {"model_name": "llama"})

        Returns:
            List of metric values across all samples
        """
        values = []
        for sample in self.samples:
            metrics = sample.get("metrics", {})
            metric_data = metrics.get(metric_name, [])

            if isinstance(metric_data, list):
                for item in metric_data:
                    if label_filter is None or (
                        isinstance(item, dict) and
                        item.get("labels", {}) == label_filter
                    ):
                        values.append(item.get("value", 0))
            elif isinstance(metric_data, (int, float)):
                values.append(metric_data)

        return values

    def get_last_value(self, metric_name: str) -> float:
        """Get value from last sample (for cumulative metrics).

        Args:
            metric_name: Name of metric to extract

        Returns:
            Metric value from last sample, or 0 if not found
        """
        if not self.samples:
            return 0

        last_sample = self.samples[-1]
        metrics_data = last_sample.get("metrics", {})
        metric_list = metrics_data.get(metric_name, [])

        if metric_list and len(metric_list) > 0:
            return metric_list[0].get("value", 0)
        return 0

    def compute_statistics(self, values: List[float]) -> Dict[str, float]:
        """Compute statistical summary from values.

        Args:
            values: List of numeric values

        Returns:
            Dict with mean, min, max, p50, p95, p99
        """
        if not values:
            return {}

        sorted_vals = sorted(values)
        n = len(sorted_vals)

        return {
            "mean": sum(values) / n,
            "min": sorted_vals[0],
            "max": sorted_vals[-1],
            "p50": sorted_vals[int(n * 0.50)],
            "p95": sorted_vals[int(n * 0.95)] if n > 1 else sorted_vals[0],
            "p99": sorted_vals[int(n * 0.99)] if n > 1 else sorted_vals[0],
        }

    def extract_histogram_stats(self, base_name: str) -> Dict[str, float]:
        """Extract summary stats from Prometheus histogram.

        Prometheus histograms are exported as multiple time series with
        _sum, _count, and _bucket suffixes. This extracts the cumulative
        sum and count from the last sample.

        Args:
            base_name: Base metric name (without _sum/_count suffix)

        Returns:
            Dict with mean, total, count
        """
        sum_metric = f"{base_name}_sum"
        count_metric = f"{base_name}_count"

        if not self.samples:
            return {}

        last_metrics = self.samples[-1].get("metrics", {})
        sum_data = last_metrics.get(sum_metric, [])
        count_data = last_metrics.get(count_metric, [])

        total_sum = 0
        total_count = 0

        if isinstance(sum_data, list):
            total_sum = sum(item.get("value", 0) for item in sum_data)
        elif isinstance(sum_data, (int, float)):
            total_sum = sum_data

        if isinstance(count_data, list):
            total_count = sum(item.get("value", 0) for item in count_data)
        elif isinstance(count_data, (int, float)):
            total_count = count_data

        if total_count > 0:
            return {
                "mean": total_sum / total_count,
                "total": total_sum,
                "count": total_count,
            }
        return {}

    def extract_all_metrics(self) -> Dict[str, Any]:
        """Extract all standard vLLM metrics with detailed statistics.

        This is the comprehensive extraction used by results processing.

        Returns:
            Dict with all server-side metrics including:
            - Resource usage (CPU, memory, KV cache)
            - Token counts
            - Latency metrics (TTFT, TPOT, E2E, queue, prefill, decode)
            - Cache performance
            - Queue metrics
        """
        if not self.samples:
            return {}

        result = {}

        # Resource usage metrics
        cpu_values = self.get_metric_values("process_cpu_seconds_total")
        if cpu_values and len(cpu_values) > 1:
            cpu_rate = (cpu_values[-1] - cpu_values[0]) / len(self.samples)
            result["server_cpu_usage_rate"] = cpu_rate

        mem_values = self.get_metric_values("process_resident_memory_bytes")
        if mem_values:
            mem_stats = self.compute_statistics(mem_values)
            result["server_memory_mean_bytes"] = mem_stats.get("mean")
            result["server_memory_max_bytes"] = mem_stats.get("max")

        kv_cache_values = self.get_metric_values("vllm:kv_cache_usage_perc")
        if kv_cache_values:
            kv_stats = self.compute_statistics(kv_cache_values)
            result["server_kv_cache_usage_mean"] = kv_stats.get("mean")
            result["server_kv_cache_usage_max"] = kv_stats.get("max")

        # Queue/Concurrency metrics
        running_values = self.get_metric_values("vllm:num_requests_running")
        if running_values:
            running_stats = self.compute_statistics(running_values)
            result["server_requests_running_mean"] = running_stats.get("mean")
            result["server_requests_running_max"] = running_stats.get("max")

        waiting_values = self.get_metric_values("vllm:num_requests_waiting")
        if waiting_values:
            waiting_stats = self.compute_statistics(waiting_values)
            result["server_requests_waiting_mean"] = waiting_stats.get("mean")
            result["server_requests_waiting_max"] = waiting_stats.get("max")

        # Cache performance (from last sample - cumulative counters)
        last_metrics = self.samples[-1].get("metrics", {})

        prefix_hits = last_metrics.get("vllm:prefix_cache_hits_total", [])
        prefix_queries = last_metrics.get("vllm:prefix_cache_queries_total", [])

        if prefix_hits and prefix_queries and isinstance(prefix_hits, list):
            total_hits = sum(item.get("value", 0) for item in prefix_hits)
            total_queries = sum(item.get("value", 0) for item in prefix_queries)

            result["server_prefix_cache_hits"] = total_hits
            result["server_prefix_cache_queries"] = total_queries
            result["server_prefix_cache_hit_rate"] = (
                total_hits / total_queries if total_queries > 0 else 0
            )

        # Preemptions
        preemptions = last_metrics.get("vllm:num_preemptions_total", [])
        if preemptions and isinstance(preemptions, list):
            result["server_num_preemptions"] = sum(
                item.get("value", 0) for item in preemptions
            )

        # Token counts
        prompt_tokens = last_metrics.get("vllm:prompt_tokens_total", [])
        if prompt_tokens and isinstance(prompt_tokens, list):
            result["server_prompt_tokens_total"] = sum(
                item.get("value", 0) for item in prompt_tokens
            )

        generation_tokens = last_metrics.get("vllm:generation_tokens_total", [])
        if generation_tokens and isinstance(generation_tokens, list):
            result["server_generation_tokens_total"] = sum(
                item.get("value", 0) for item in generation_tokens
            )

        # Server-side latency metrics (in seconds, convert to ms)
        ttft_stats = self.extract_histogram_stats("vllm:time_to_first_token_seconds")
        if ttft_stats:
            result["server_ttft_mean_ms"] = ttft_stats["mean"] * 1000

        tpot_stats = self.extract_histogram_stats(
            "vllm:request_time_per_output_token_seconds"
        )
        if tpot_stats:
            result["server_tpot_mean_ms"] = tpot_stats["mean"] * 1000

        e2e_stats = self.extract_histogram_stats("vllm:e2e_request_latency_seconds")
        if e2e_stats:
            result["server_e2e_latency_mean_ms"] = e2e_stats["mean"] * 1000

        queue_stats = self.extract_histogram_stats("vllm:request_queue_time_seconds")
        if queue_stats:
            result["server_queue_time_mean_ms"] = queue_stats["mean"] * 1000

        prefill_stats = self.extract_histogram_stats(
            "vllm:request_prefill_time_seconds"
        )
        if prefill_stats:
            result["server_prefill_time_mean_ms"] = prefill_stats["mean"] * 1000

        decode_stats = self.extract_histogram_stats(
            "vllm:request_decode_time_seconds"
        )
        if decode_stats:
            result["server_decode_time_mean_ms"] = decode_stats["mean"] * 1000

        return result

    def extract_simple_metrics(self) -> Dict[str, Any]:
        """Extract simple metrics from last sample only.

        This is the simpler extraction used by MLflow logging.

        Returns:
            Dict with server-side metrics using last sample values
        """
        if not self.samples:
            return {}

        server_metrics = {}

        # KV Cache utilization (%)
        kv_cache_usage = self.get_last_value("vllm:kv_cache_usage_perc")
        if kv_cache_usage > 0:
            server_metrics["server_kv_cache_usage_pct"] = kv_cache_usage

        # Total tokens processed
        prompt_tokens = self.get_last_value("vllm:prompt_tokens_total")
        generation_tokens = self.get_last_value("vllm:generation_tokens_total")

        if prompt_tokens > 0:
            server_metrics["server_prompt_tokens_total"] = prompt_tokens
        if generation_tokens > 0:
            server_metrics["server_generation_tokens_total"] = generation_tokens
        if prompt_tokens > 0 and generation_tokens > 0:
            server_metrics["server_total_tokens"] = prompt_tokens + generation_tokens

        # Cache hit rates
        prefix_hits = self.get_last_value("vllm:prefix_cache_hits_total")
        prefix_queries = self.get_last_value("vllm:prefix_cache_queries_total")

        if prefix_queries > 0:
            server_metrics["server_prefix_cache_hit_rate"] = (
                (prefix_hits / prefix_queries) * 100
            )

        # Request success rate
        success_total = self.get_last_value("vllm:request_success_total")
        e2e_count = self.get_last_value(
            "vllm:e2e_request_latency_seconds_count"
        )

        if e2e_count > 0:
            server_metrics["server_requests_total"] = e2e_count
            server_metrics["server_request_success_rate"] = (
                (success_total / e2e_count) * 100
            )

        # Average latencies from histogram sums and counts
        ttft_sum = self.get_last_value("vllm:time_to_first_token_seconds_sum")
        ttft_count = self.get_last_value("vllm:time_to_first_token_seconds_count")

        if ttft_count > 0:
            server_metrics["server_ttft_avg_ms"] = (ttft_sum / ttft_count) * 1000

        # E2E latency
        e2e_sum = self.get_last_value("vllm:e2e_request_latency_seconds_sum")
        if e2e_count > 0:
            server_metrics["server_e2e_latency_avg_s"] = e2e_sum / e2e_count

        # Prefill time
        prefill_sum = self.get_last_value("vllm:request_prefill_time_seconds_sum")
        prefill_count = self.get_last_value(
            "vllm:request_prefill_time_seconds_count"
        )

        if prefill_count > 0:
            server_metrics["server_prefill_time_avg_s"] = prefill_sum / prefill_count

        # Decode time
        decode_sum = self.get_last_value("vllm:request_decode_time_seconds_sum")
        decode_count = self.get_last_value(
            "vllm:request_decode_time_seconds_count"
        )

        if decode_count > 0:
            server_metrics["server_decode_time_avg_s"] = decode_sum / decode_count

        # TPOT
        tpot_sum = self.get_last_value(
            "vllm:request_time_per_output_token_seconds_sum"
        )
        tpot_count = self.get_last_value(
            "vllm:request_time_per_output_token_seconds_count"
        )

        if tpot_count > 0:
            server_metrics["server_tpot_avg_s"] = tpot_sum / tpot_count

        return server_metrics


def parse_vllm_metrics(vllm_metrics_path: Union[str, Path]) -> Dict[str, Any]:
    """Parse vLLM metrics file (backward compatibility wrapper).

    Args:
        vllm_metrics_path: Path to vllm-metrics.json file

    Returns:
        Dict with aggregated server-side metrics
    """
    if not vllm_metrics_path or not Path(vllm_metrics_path).exists():
        print(
            f"Warning: vLLM metrics file not found at {vllm_metrics_path}",
            file=sys.stderr
        )
        return {}

    parser = VLLMMetricsParser(vllm_metrics_path)
    return parser.extract_all_metrics()
