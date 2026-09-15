"""Tests for multiturn and gsm8k-quality suites."""

import subprocess
import sys

import yaml

from cpueval.suite_registry import SuiteRegistry
from cpueval.paths import get_ansible_dir
from .conftest import repo_root


def _run_cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "cpueval", *args],
        capture_output=True,
        text=True,
        cwd=str(repo_root()),
    )


def test_multiturn_suite_registered():
    """Test that the multiturn suite loads with chat_multiturn default."""
    registry = SuiteRegistry()
    suite = registry.get_suite("multiturn")

    assert suite is not None
    assert suite.runner == "ansible"
    assert suite.target == "llm-benchmark-auto.yml"
    assert suite.defaults["workload_type"] == "chat_multiturn"


def test_gsm8k_quality_suite_registered():
    """Test that the gsm8k-quality suite loads with playbook target."""
    registry = SuiteRegistry()
    suite = registry.get_suite("gsm8k-quality")

    assert suite is not None
    assert suite.runner == "ansible"
    assert suite.target == "gsm8k-quality.yml"
    assert suite.defaults["gsm8k_turns_mode"] == "answer-forcing"


def test_suite_target_playbooks_exist():
    """Test that ansible suite targets resolve to existing playbooks."""
    registry = SuiteRegistry()
    for name in ("multiturn", "gsm8k-quality"):
        suite = registry.get_suite(name)
        assert suite is not None, f"missing suite: {name}"
        playbook = get_ansible_dir() / suite.target
        assert playbook.exists(), f"playbook not found for {name}: {playbook}"


def test_multiturn_dry_run_maps_workload():
    """Test multiturn dry run maps model/cores/workload to ansible vars."""
    result = _run_cli(
        "run", "--suite", "multiturn",
        "--model", "meta-llama/Llama-3.2-1B-Instruct",
        "--cores", "16",
        "--dry-run",
    )

    assert result.returncode == 0, f"STDERR: {result.stderr}"
    assert "llm-benchmark-auto.yml" in result.stdout
    assert "-e workload_type=chat_multiturn" in result.stdout
    assert "-e test_model=meta-llama/Llama-3.2-1B-Instruct" in result.stdout
    assert "-e requested_cores=16" in result.stdout


def test_multiturn_turns_flag_maps_to_guidellm_turns():
    """Test --turns passes guidellm_turns extra var to ansible."""
    result = _run_cli(
        "run", "--suite", "multiturn",
        "--model", "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
        "--cores", "16",
        "--turns", "8",
        "--dry-run",
    )

    assert result.returncode == 0, f"STDERR: {result.stderr}"
    assert "-e guidellm_turns=8" in result.stdout


def test_multiturn_requires_model():
    """Test that multiturn requires --model."""
    result = _run_cli("run", "--suite", "multiturn", "--dry-run")

    assert result.returncode == 1
    assert "--model is required" in result.stdout


def test_gsm8k_quality_dry_run_defaults():
    """Test gsm8k-quality dry run emits expected ansible extra vars."""
    result = _run_cli(
        "run", "--suite", "gsm8k-quality",
        "--model", "meta-llama/Llama-3.2-1B-Instruct",
        "--cores", "16",
        "--dry-run",
    )

    assert result.returncode == 0, f"STDERR: {result.stderr}"
    assert "gsm8k-quality.yml" in result.stdout
    assert "-e gsm8k_turns_mode=answer-forcing" in result.stdout
    assert "-e test_model=meta-llama/Llama-3.2-1B-Instruct" in result.stdout
    assert "-e requested_cores=16" in result.stdout


def test_gsm8k_quality_turns_mode_and_num_problems():
    """Test --turns-mode and --num-problems override suite defaults."""
    result = _run_cli(
        "run", "--suite", "gsm8k-quality",
        "--model", "meta-llama/Llama-3.2-1B-Instruct",
        "--cores", "16",
        "--turns-mode", "guided-steps",
        "--num-problems", "200",
        "--dry-run",
    )

    assert result.returncode == 0, f"STDERR: {result.stderr}"
    assert "-e gsm8k_turns_mode=guided-steps" in result.stdout
    assert "-e gsm8k_num_problems=200" in result.stdout


def test_invalid_turns_mode_rejected():
    """Test that an invalid --turns-mode exits with an error."""
    result = _run_cli(
        "run", "--suite", "gsm8k-quality",
        "--model", "meta-llama/Llama-3.2-1B-Instruct",
        "--turns-mode", "not-a-mode",
        "--dry-run",
    )

    assert result.returncode == 1
    assert "Invalid --turns-mode" in result.stdout


def test_gsm8k_quality_requires_model():
    """Test that gsm8k-quality requires --model."""
    result = _run_cli("run", "--suite", "gsm8k-quality", "--dry-run")

    assert result.returncode == 1
    assert "--model is required" in result.stdout


def test_multiturn_workload_defined_in_inventory():
    """Test chat_multiturn/gsm8k_quality workloads exist in test-workloads.yml."""
    workloads_file = (
        repo_root()
        / "automation/test-execution/ansible/inventory/group_vars/all/test-workloads.yml"
    )
    with open(workloads_file) as f:
        data = yaml.safe_load(f)

    configs = data["test_configs"]
    assert "chat_multiturn" in configs
    multiturn = configs["chat_multiturn"]
    assert multiturn["turns"] >= 2
    assert multiturn["prefix_tokens"] > 0
    assert multiturn["backend"] == "openai-chat"

    assert "gsm8k_quality" in configs
    assert configs["gsm8k_quality"]["backend"] == "openai-chat"
