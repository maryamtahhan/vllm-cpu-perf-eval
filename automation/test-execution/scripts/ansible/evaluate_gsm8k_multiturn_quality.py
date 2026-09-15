#!/usr/bin/env python3
"""Evaluate GSM8K multi-turn accuracy against a vLLM endpoint.

Runs multi-turn conversations over /v1/chat/completions using GSM8K math
problems and scores final-answer accuracy, writing quality-results.json.

Turn modes:
    answer-forcing  3 turns: (1) solve step by step, (2) re-check the work,
                    (3) force a strict final-answer format.  Measures whether
                    the model can converge to a parseable, correct answer
                    across turns.
    guided-steps    Reference-solution steps are fed progressively as user
                    turns; the final turn asks for the strict answer format.
                    Maximizes conversation history growth - useful as a
                    regression test for multi-turn history handling and
                    KV/prefix-cache correctness.  Accuracy ceiling is near
                    100%; drops indicate correctness regressions, not model
                    capability.

Prerequisites (on the machine running this script):
    pip install datasets requests

Usage:
    # Automated (called by gsm8k-quality.yml playbook):
    python3 evaluate_gsm8k_multiturn_quality.py \\
        --endpoint http://dut:8000 \\
        --output-dir results/llm/<model>/gsm8k-quality-<run-id>/<core-config>/ \\
        --model meta-llama/Llama-3.2-1B-Instruct \\
        --test-run-id <run-id> --cores 32

    # Manual standalone, guided-steps mode, 50 problems:
    python3 evaluate_gsm8k_multiturn_quality.py \\
        --endpoint http://localhost:8000 \\
        --output-dir /tmp/gsm8k-results/ \\
        --turns-mode guided-steps --num-problems 50
"""

import argparse
import concurrent.futures
import json
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ANSWER_PATTERNS = [
    r"the final answer is[:\s]*([-+]?\$?[\d,]*\.?\d+)",
    r"the answer is[:\s]*([-+]?\$?[\d,]*\.?\d+)",
    r"\\boxed\{([-+]?\$?[\d,]*\.?\d+)\}",
    r"(?m)^\s*(?:final answer|answer)\s*[:=]?\s*([-+]?\$?[\d,]*\.?\d+)",
]
LAST_NUMBER_RE = re.compile(r"([-+]?\$?\d[\d,]*(?:\.\d+)?)")

CHECK_TURN = ("Review your work above and re-check every calculation. "
              "If a step is wrong, correct it; otherwise confirm it.")
FINAL_TURN = ("State the final numerical answer on the last line of your "
              "reply in exactly this format: The answer is X")


def _load_problems(dataset, config, split, num_problems, seed):
    """Load GSM8K problems (question, reference answer) from HuggingFace."""
    try:
        from datasets import load_dataset
    except ImportError:
        print("Error: 'datasets' package required.  pip install datasets",
              file=sys.stderr)
        sys.exit(1)

    ds = load_dataset(dataset, config, split=split, streaming=True)
    problems = [
        {"question": row["question"], "answer": row["answer"]}
        for row in ds
    ]

    if num_problems and 0 < num_problems < len(problems):
        rng = random.Random(seed)
        problems = rng.sample(problems, num_problems)

    return problems


def _gold_number(reference):
    """Extract the gold final number from a GSM8K reference answer."""
    match = re.search(r"####\s*([-+]?\$?[\d,]*\.?\d+)", reference)
    if not match:
        return None
    return _parse_number(match.group(1))


def _reference_steps(reference):
    """Split a GSM8K reference answer into step lines (dropping '#### x')."""
    steps = [line.strip() for line in reference.split("\n")]
    steps = [s for s in steps if s and not s.startswith("####")]
    return steps


def _parse_number(raw):
    """Parse a raw numeric string, tolerating $ , and trailing punctuation."""
    cleaned = raw.replace("$", "").replace(",", "").rstrip(".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _extract_answer(text):
    """Extract a predicted number from assistant text.

    Returns (value, method) where method is one of:
    'pattern' (explicit answer phrase), 'boxed', 'last_number' (fallback),
    or None when nothing parseable is found.
    """
    if not text:
        return None, None

    for pattern in ANSWER_PATTERNS:
        matches = re.findall(pattern, text, flags=re.IGNORECASE)
        if matches:
            value = _parse_number(matches[-1])
            if value is not None:
                method = "boxed" if pattern.startswith(r"\\boxed") else "pattern"
                return value, method

    numbers = LAST_NUMBER_RE.findall(text)
    for raw in reversed(numbers):
        value = _parse_number(raw)
        if value is not None:
            return value, "last_number"
    return None, None


def _build_turns(problem, turns_mode):
    """Build the list of user messages for one conversation."""
    if turns_mode == "guided-steps":
        steps = _reference_steps(problem["answer"])
        if not steps:
            steps = [problem["answer"].replace("\n", " ")]
        messages = [
            f"{problem['question']}\n\n"
            f"Here is step 1 of the solution:\n{steps[0]}\n"
            "Work out this step and report its numeric result."
        ]
        for i, step in enumerate(steps[1:-1], start=2):
            messages.append(
                f"Here is step {i} of the solution:\n{step}\n"
                "Work out this step and report the running result."
            )
        messages.append(
            f"The final step of the solution:\n{steps[-1]}\n{FINAL_TURN}."
        )
        return messages

    # answer-forcing (default): solve, verify, then force strict format
    return [
        f"{problem['question']}\n"
        "Please reason step by step and show your work.",
        CHECK_TURN,
        FINAL_TURN + ".",
    ]


def _chat(endpoint, model, messages, max_tokens, temperature, timeout,
          api_key=None):
    """Send a chat completion request; returns (content, usage)."""
    import requests as req

    url = f"{endpoint.rstrip('/')}/v1/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    resp = req.post(url, json=payload, headers=headers, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    content = data["choices"][0]["message"].get("content") or ""
    return content, data.get("usage", {})


def _run_conversation(idx, problem, args):
    """Run one multi-turn conversation and score the final answer."""
    gold = _gold_number(problem["answer"])
    record = {
        "problem_id": idx,
        "question": problem["question"],
        "gold": gold,
        "predicted": None,
        "answer_method": None,
        "correct": False,
        "turns": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "responses": [],
        "error": None,
    }

    user_turns = _build_turns(problem, args.turns_mode)
    messages = []
    try:
        for turn, user_text in enumerate(user_turns):
            messages.append({"role": "user", "content": user_text})
            content, usage = _chat(
                args.endpoint, args.model, messages,
                args.max_tokens, args.temperature, args.request_timeout,
                api_key=args.api_key,
            )
            messages.append({"role": "assistant", "content": content})
            record["responses"].append(content)
            record["turns"] = turn + 1
            record["prompt_tokens"] += usage.get("prompt_tokens", 0)
            record["completion_tokens"] += usage.get("completion_tokens", 0)
    except Exception as e:
        record["error"] = str(e)
        return record

    # Score on the final assistant message; fall back to the full transcript
    predicted, method = _extract_answer(record["responses"][-1])
    if predicted is None:
        predicted, method = _extract_answer("\n".join(record["responses"]))
    record["predicted"] = predicted
    record["answer_method"] = method
    if predicted is not None and gold is not None:
        record["correct"] = abs(predicted - gold) < 1e-6
    return record


def main():
    p = argparse.ArgumentParser(
        description="Evaluate GSM8K multi-turn accuracy",
    )
    p.add_argument("--endpoint", required=True, help="vLLM server URL")
    p.add_argument("--output-dir", required=True,
                   help="Directory for quality-results.json")
    p.add_argument("--model", default=None,
                   help="Model name (default: auto-detect from endpoint)")
    p.add_argument("--num-problems", type=int, default=0,
                   help="Problem count (0 = entire split)")
    p.add_argument("--dataset", default="openai/gsm8k")
    p.add_argument("--dataset-config", default="main")
    p.add_argument("--dataset-split", default="test")
    p.add_argument("--turns-mode", default="answer-forcing",
                   choices=["answer-forcing", "guided-steps"])
    p.add_argument("--max-tokens", type=int, default=512)
    p.add_argument("--temperature", type=float, default=0.0)
    p.add_argument("--request-timeout", type=int, default=600)
    p.add_argument("--concurrency", type=int, default=1,
                   help="Parallel conversations (default: sequential)")
    p.add_argument("--api-key", default=None, help="Bearer token if required")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--test-run-id", default=None,
                   help="Test run ID to embed in quality-results.json")
    p.add_argument("--cores", type=int, default=None,
                   help="Core count to embed in quality-results.json")

    args = p.parse_args()

    if args.model is None:
        import requests as req
        resp = req.get(f"{args.endpoint.rstrip('/')}/v1/models", timeout=30)
        resp.raise_for_status()
        args.model = resp.json()["data"][0]["id"]

    problems = _load_problems(
        args.dataset, args.dataset_config, args.dataset_split,
        args.num_problems, args.seed,
    )
    if not problems:
        print("No problems loaded.", file=sys.stderr)
        return 1

    print(f"Evaluating {len(problems)} GSM8K problems "
          f"(mode={args.turns_mode}) against {args.endpoint} ...")

    start = time.monotonic()
    records = []
    if args.concurrency > 1:
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=args.concurrency
        ) as pool:
            futures = [
                pool.submit(_run_conversation, i, prob, args)
                for i, prob in enumerate(problems)
            ]
            for done, future in enumerate(
                concurrent.futures.as_completed(futures)
            ):
                records.append(future.result())
                if (done + 1) % 10 == 0:
                    print(f"  {done + 1}/{len(problems)} done")
    else:
        for i, prob in enumerate(problems):
            records.append(_run_conversation(i, prob, args))
            if (i + 1) % 10 == 0:
                print(f"  {i + 1}/{len(problems)} done")
    duration = time.monotonic() - start

    records.sort(key=lambda r: r["problem_id"])
    scored = [r for r in records if r["error"] is None and r["gold"] is not None]
    correct = sum(1 for r in scored if r["correct"])
    errors = sum(1 for r in records if r["error"] is not None)
    unparseable = sum(
        1 for r in scored if r["predicted"] is None and not r["correct"]
    )
    accuracy = (correct / len(scored)) if scored else 0.0

    print(f"\nResults: accuracy={accuracy * 100:.1f}% "
          f"({correct}/{len(scored)} correct, {errors} request errors, "
          f"{unparseable} unparseable)  [{duration:.1f}s]")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    result = {
        "benchmark": "gsm8k-multiturn-quality",
        "accuracy": accuracy,
        "num_problems": len(problems),
        "num_scored": len(scored),
        "num_correct": correct,
        "num_request_errors": errors,
        "num_unparseable": unparseable,
        "turns_mode": args.turns_mode,
        "avg_turns": (sum(r["turns"] for r in records) / len(records))
        if records else 0,
        "total_prompt_tokens": sum(r["prompt_tokens"] for r in records),
        "total_completion_tokens": sum(r["completion_tokens"] for r in records),
        "duration_seconds": round(duration, 2),
        "model": args.model,
        "dataset": args.dataset,
        "dataset_config": args.dataset_config,
        "dataset_split": args.dataset_split,
        "seed": args.seed,
        "temperature": args.temperature,
        "max_tokens": args.max_tokens,
        "concurrency": args.concurrency,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "per_problem": records,
    }
    if args.test_run_id:
        result["test_run_id"] = args.test_run_id
    if args.cores is not None:
        result["cores"] = args.cores

    out_path = output_dir / "quality-results.json"
    with open(out_path, "w") as fh:
        json.dump(result, fh, indent=2)

    print(f"Wrote {out_path}")
    if errors and not scored:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
