#!/usr/bin/env python3
"""Validate a configured long context, DP2 concurrency, and mixed C8 load."""

from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import subprocess
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.benchmark_openai import BenchmarkError, Client, container_state, inventory


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "benchmarks" / "results"
TARGET_CONTEXT = 131_072
ACCEPTANCE_PROMPT_TOKENS = 130_816
MARKER_PROMPT_CASES = (32_768, 65_536, 98_304, 122_880, 130_816)
MARKER_POSITIONS = ("front", "middle", "end", "front", "end")
LONG_CONCURRENCY_PROMPT_TOKENS = 130_000
LONG_OUTPUT_TOKENS = 64
FILLER_UNIT = " x"


def marker_prompt_cases(target_context: int) -> tuple[int, ...]:
    """Return fixed long-context boundaries and a near-capacity prompt."""
    candidates = (4_096, 8_192, 16_384, 24_576, 32_768, 49_152, 65_536)
    return tuple(dict.fromkeys(
        target for target in (*candidates, target_context - 256)
        if 0 < target < target_context
    ))


def distribute_filler(count: int, position: str) -> tuple[int, int]:
    if position == "front":
        return 0, count
    if position == "middle":
        return count // 2, count - count // 2
    if position == "end":
        return count, 0
    raise ValueError(f"unsupported needle position: {position}")


def prometheus_metric(payload: str, name: str) -> float:
    total = 0.0
    for line in payload.splitlines():
        match = re.fullmatch(
            rf"{re.escape(name)}(?:\{{[^}}]*\}})?\s+([-+0-9.eE]+)(?:\s+\d+)?",
            line,
        )
        if match:
            total += float(match.group(1))
    return total


def parse_kv_cache_tokens(logs: str, ranks: int) -> list[int]:
    values = [int(value.replace(",", "")) for value in re.findall(
        r"GPU KV cache size:\s+([\d,]+) tokens", logs
    )]
    return values[-ranks:]


def reasoning_delta(delta: dict[str, Any]) -> str:
    return delta.get("reasoning") or delta.get("reasoning_content") or ""


def collapsed_output(content: str) -> bool:
    """Detect the observed repeated-token corruption without storing response text."""
    compact = "".join(content.split())
    if len(compact) >= 4 and len(set(compact)) == 1:
        return True
    words = content.split()
    return len(words) >= 4 and len(set(words)) <= 2


def probe_quality_ok(row: dict[str, Any]) -> bool:
    return bool(
        row.get("ok")
        and row.get("marker_ok")
        and row.get("finite_logprobs")
        and not row.get("collapsed_output")
        and not row.get("think_tag_visible")
        and not row.get("reasoning_content_present")
    )


def runtime_mode(values: dict[str, Any], container: str) -> dict[str, Any]:
    instance = next(
        (row for row in values.get("vllm_server_instances", []) if row["name"] == container),
        {},
    )
    return {
        "xpu_graph_enabled": bool(instance.get(
            "enable_xpu_graph", values.get("vllm_server_enable_xpu_graph", True)
        )),
        "enforce_eager": bool(instance.get(
            "enforce_eager", values.get("vllm_server_enforce_eager", False)
        )),
        "compilation_config": instance.get(
            "compilation_config", values.get("vllm_server_compilation_config", "")
        ),
        "mamba_cache_dtype": instance.get(
            "mamba_cache_dtype", values.get("vllm_server_mamba_cache_dtype", "auto")
        ),
        "mamba_ssm_cache_dtype": instance.get(
            "mamba_ssm_cache_dtype", values.get("vllm_server_mamba_ssm_cache_dtype", "auto")
        ),
    }


def result_passes(
    result: dict[str, Any],
    target_context: int = TARGET_CONTEXT,
    acceptance_prompt_tokens: int = ACCEPTANCE_PROMPT_TOKENS,
    acceptance_output_tokens: int = 256,
) -> bool:
    metadata = result["metadata"]
    stable = (
        metadata["container_before"]["restart_count"]
        == metadata["container_after"]["restart_count"]
        and not metadata["container_after"]["oom_killed"]
    )
    cache_ok = (
        len(metadata["kv_cache_tokens_per_rank"]) >= 2
        and min(metadata["kv_cache_tokens_per_rank"]) >= target_context
    )
    marker_ok = all(probe_quality_ok(row) for row in result["marker_cases"])
    acceptance_ok = (
        probe_quality_ok(result["acceptance_case"])
        and result["acceptance_case"].get("prompt_tokens") == acceptance_prompt_tokens
        and result["acceptance_case"].get("output_tokens") == acceptance_output_tokens
    )
    c2_ok = all(
        len(round_rows) == 2 and all(probe_quality_ok(row) for row in round_rows)
        for round_rows in result["long_c2_rounds"]
    )
    mixed_ok = (
        len(result["mixed_c8"]) == 8
        and all(probe_quality_ok(row) for row in result["mixed_c8"])
    )
    return stable and cache_ok and marker_ok and acceptance_ok and c2_ok and mixed_ok


class LongContextClient:
    def __init__(self, client: Client, model: str) -> None:
        self.client = client
        self.model = model

    def token_count(self, content: str) -> int:
        response = self.client.json("POST", "/tokenize", {
            "model": self.model,
            "messages": [{"role": "user", "content": content}],
            "add_generation_prompt": True,
            "chat_template_kwargs": {"enable_thinking": False},
        })
        tokens = response.get("tokens") or response.get("token_ids")
        if not isinstance(tokens, list):
            raise BenchmarkError("tokenize endpoint returned no token list")
        return len(tokens)

    def fitted_prompt(self, target_tokens: int, marker: str, position: str) -> str:
        instruction = (
            "Read the document, remember its SECRET_CODE, and answer the final question "
            "with exactly that code and no other text.\nDOCUMENT START\n"
        )
        needle = f"\nSECRET_CODE: {marker}\n"
        question = "\nDOCUMENT END\nWhat is the SECRET_CODE? Answer with the code only."
        fixed = instruction + needle + question
        fixed_tokens = self.token_count(fixed)
        if fixed_tokens >= target_tokens:
            raise BenchmarkError("target token count is too small for the probe")
        filler_count = target_tokens - fixed_tokens
        for _ in range(12):
            before, after = distribute_filler(filler_count, position)
            prompt = instruction + FILLER_UNIT * before + needle + FILLER_UNIT * after + question
            actual = self.token_count(prompt)
            if actual == target_tokens:
                return prompt
            filler_count += target_tokens - actual
            if filler_count < 0:
                break
        raise BenchmarkError(
            f"could not construct exact {target_tokens}-token prompt for {position} needle"
        )

    def stream_chat(
        self,
        content: str,
        max_tokens: int,
        *,
        ignore_eos: bool = False,
    ) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": content}],
            "temperature": 0,
            "seed": 0,
            "max_tokens": max_tokens,
            "ignore_eos": ignore_eos,
            "stream": True,
            "stream_options": {"include_usage": True},
            "logprobs": True,
            "top_logprobs": 1,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        request = urllib.request.Request(
            self.client.base_url + "/v1/chat/completions",
            data=json.dumps(payload).encode(),
            method="POST",
            headers={
                "Authorization": f"Bearer {self.client.key}",
                "Content-Type": "application/json",
            },
        )
        started = time.perf_counter()
        first_token_at: float | None = None
        content_chunks: list[str] = []
        reasoning_chunks: list[str] = []
        usage: dict[str, Any] = {}
        finish_reason: str | None = None
        token_logprobs: list[float] = []
        try:
            with urllib.request.urlopen(request, timeout=3600) as response:
                for raw in response:
                    line = raw.decode().strip()
                    if not line.startswith("data: ") or line == "data: [DONE]":
                        continue
                    event = json.loads(line[6:])
                    if event.get("usage"):
                        usage = event["usage"]
                    choices = event.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    for token in (choices[0].get("logprobs") or {}).get("content") or []:
                        value = token.get("logprob")
                        if isinstance(value, (int, float)):
                            token_logprobs.append(float(value))
                    content_delta = delta.get("content") or ""
                    reasoning_chunk = reasoning_delta(delta)
                    if content_delta or reasoning_chunk:
                        first_token_at = first_token_at or time.perf_counter()
                    content_chunks.append(content_delta)
                    reasoning_chunks.append(reasoning_chunk)
                    finish_reason = choices[0].get("finish_reason") or finish_reason
        except (urllib.error.URLError, json.JSONDecodeError) as error:
            raise BenchmarkError(f"long-context stream failed: {error}") from error
        ended = time.perf_counter()
        if first_token_at is None:
            raise BenchmarkError("long-context stream returned no output")
        prompt_tokens = int(usage.get("prompt_tokens", 0))
        output_tokens = int(usage.get("completion_tokens", 0))
        ttft_ms = (first_token_at - started) * 1000
        e2e_ms = (ended - started) * 1000
        return {
            "ok": True,
            "prompt_tokens": prompt_tokens,
            "output_tokens": output_tokens,
            "ttft_ms": ttft_ms,
            "e2e_ms": e2e_ms,
            "prompt_tps": prompt_tokens / (ttft_ms / 1000),
            "output_tps": output_tokens / max((ended - first_token_at), 1e-9),
            "finish_reason": finish_reason,
            "content": "".join(content_chunks),
            "reasoning_content_present": bool("".join(reasoning_chunks)),
            "finite_logprobs": bool(token_logprobs) and all(
                math.isfinite(value) for value in token_logprobs
            ),
        }


def safe_probe(
    probe: Any,
    marker: str | None = None,
    *,
    exact_marker: bool = True,
) -> dict[str, Any]:
    try:
        row = probe()
        if marker is not None:
            row["marker"] = marker
            content = row.get("content", "").strip()
            row["marker_ok"] = content == marker if exact_marker else marker in content
            row["think_tag_visible"] = "<think>" in row.get("content", "")
            row["collapsed_output"] = collapsed_output(content)
        row.pop("content", None)
        return row
    except Exception as error:  # Keep a failure artifact without response bodies or credentials.
        return {"ok": False, "marker_ok": False, "error": f"{type(error).__name__}: {error}"}


def read_container_logs(container: str) -> str:
    process = subprocess.run(
        ["ansible", "ubuntu-gpu", "-m", "shell", "-a", f"docker logs {container} 2>&1"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return process.stdout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="dp2_intel_mtp3_128k_c8")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--container", default="vllm-server")
    parser.add_argument("--target-context", type=int)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument(
        "--prompt-tokens", type=int, nargs="+",
        help="override marker prompt lengths for a focused diagnostic",
    )
    parser.add_argument(
        "--probe-only", action="store_true",
        help="run marker accuracy probes only; reserve C2/C8 for the final candidate",
    )
    args = parser.parse_args()

    values = inventory(args.profile)
    target_context = args.target_context or int(values["vllm_server_context_size"])
    acceptance_output_tokens = 256
    acceptance_prompt_tokens = target_context - acceptance_output_tokens
    marker_cases_config = tuple(args.prompt_tokens or marker_prompt_cases(target_context))
    if any(target <= 0 or target >= target_context for target in marker_cases_config):
        raise BenchmarkError(f"invalid marker cases for target context {target_context}")
    marker_positions = ("front", "middle", "end")
    long_concurrency_prompt_tokens = target_context - 1_024
    client = Client(f"http://{values['llm_runtime_bind_address']}:{args.port}", values["llm_api_key"])
    model = client.json("GET", "/v1/models")["data"][0]["id"]
    long_client = LongContextClient(client, model)
    before = container_state(args.container)
    metrics_before = client.text("/metrics")
    cache_tokens = parse_kv_cache_tokens(read_container_logs(args.container), 2)

    marker_cases: list[dict[str, Any]] = []
    for target in marker_cases_config:
        for repetition in range(args.repetitions):
            position = marker_positions[repetition % len(marker_positions)]
            marker = f"B70_NEEDLE_{target}_{position.upper()}_{repetition + 1}"
            print(f"marker {target} {position} {repetition + 1}/{args.repetitions}", flush=True)
            prompt = long_client.fitted_prompt(target, marker, position)
            row = safe_probe(lambda prompt=prompt: long_client.stream_chat(prompt, 64), marker)
            row.update({
                "target_prompt_tokens": target,
                "needle_position": position,
                "repetition": repetition + 1,
            })
            marker_cases.append(row)

    if args.probe_only:
        after = container_state(args.container)
        metrics_after = client.text("/metrics")
        result = {
            "metadata": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "profile": args.profile,
                "model": model,
                "target_context": target_context,
                "kv_cache_dtype": values.get("vllm_server_kv_cache_dtype", "auto"),
                "runtime_mode": runtime_mode(values, args.container),
                "kv_cache_tokens_per_rank": cache_tokens,
                "container_before": before,
                "container_after": after,
                "preemptions_delta": prometheus_metric(
                    metrics_after, "vllm:num_preemptions_total"
                ) - prometheus_metric(metrics_before, "vllm:num_preemptions_total"),
            },
            "marker_cases": marker_cases,
        }
        result["passed"] = (
            min(cache_tokens or [0]) >= target_context
            and before["restart_count"] == after["restart_count"]
            and not after["oom_killed"]
            and all(
                probe_quality_ok(row)
                for row in marker_cases
            )
        )
        serialized = json.dumps(result, indent=2, sort_keys=True)
        if values["llm_api_key"] in serialized:
            raise BenchmarkError("refusing to persist API key")
        output = args.output or RESULTS / (
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "-vllm-long-context-probe.json"
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(serialized + "\n")
        print(json.dumps({
            "passed": result["passed"],
            "output": str(output.resolve().relative_to(ROOT)),
            "kv_cache_tokens_per_rank": cache_tokens,
            "preemptions_delta": result["metadata"]["preemptions_delta"],
        }))
        return 0 if result["passed"] else 1

    print(f"{target_context} combined-token acceptance", flush=True)
    acceptance_marker = f"B70_ACCEPTANCE_{target_context}"
    acceptance_prompt = long_client.fitted_prompt(
        acceptance_prompt_tokens, acceptance_marker, "middle"
    )
    acceptance_case = safe_probe(
        lambda: long_client.stream_chat(
            acceptance_prompt, acceptance_output_tokens, ignore_eos=True
        ),
        acceptance_marker,
        exact_marker=False,
    )

    long_markers = ("B70_C2_ALPHA", "B70_C2_BRAVO")
    long_prompts = tuple(
        long_client.fitted_prompt(long_concurrency_prompt_tokens, marker, position)
        for marker, position in zip(long_markers, ("front", "end"), strict=True)
    )
    long_c2_rounds: list[list[dict[str, Any]]] = []
    for repetition in range(1, 3):
        print(f"long C2 round {repetition}/2", flush=True)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = {
                pool.submit(long_client.stream_chat, prompt, LONG_OUTPUT_TOKENS): marker
                for prompt, marker in zip(long_prompts, long_markers, strict=True)
            }
            rows = [safe_probe(future.result, marker) for future, marker in futures.items()]
        long_c2_rounds.append(rows)

    print("mixed C8", flush=True)
    short_specs = [(f"B70_SHORT_{index}", "middle") for index in range(6)]
    short_prompts = [
        long_client.fitted_prompt(512, marker, position)
        for marker, position in short_specs
    ]
    mixed_jobs = [
        (prompt, marker, LONG_OUTPUT_TOKENS)
        for prompt, marker in zip(long_prompts, long_markers, strict=True)
    ] + [
        (prompt, marker, 64)
        for prompt, (marker, _) in zip(short_prompts, short_specs, strict=True)
    ]
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {
            pool.submit(long_client.stream_chat, prompt, output_tokens): marker
            for prompt, marker, output_tokens in mixed_jobs
        }
        mixed_c8 = [safe_probe(future.result, marker) for future, marker in futures.items()]

    after = container_state(args.container)
    metrics_after = client.text("/metrics")
    preemptions_before = prometheus_metric(metrics_before, "vllm:num_preemptions_total")
    preemptions_after = prometheus_metric(metrics_after, "vllm:num_preemptions_total")
    result = {
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "profile": args.profile,
            "model": model,
            "target_context": target_context,
            "kv_cache_dtype": values.get("vllm_server_kv_cache_dtype", "auto"),
            "runtime_mode": runtime_mode(values, args.container),
            "kv_cache_tokens_per_rank": cache_tokens,
            "container_before": before,
            "container_after": after,
            "preemptions_delta": preemptions_after - preemptions_before,
        },
        "marker_cases": marker_cases,
        "acceptance_case": acceptance_case,
        "long_c2_rounds": long_c2_rounds,
        "mixed_c8": mixed_c8,
    }
    result["passed"] = result_passes(
        result,
        target_context,
        acceptance_prompt_tokens,
        acceptance_output_tokens,
    )
    serialized = json.dumps(result, indent=2, sort_keys=True)
    if values["llm_api_key"] in serialized:
        raise BenchmarkError("refusing to persist API key")
    output = args.output or RESULTS / (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-vllm-long-context.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(serialized + "\n")
    c2_ttft = [row["ttft_ms"] for batch in long_c2_rounds for row in batch if row.get("ok")]
    print(json.dumps({
        "passed": result["passed"],
        "output": str(output.resolve().relative_to(ROOT)),
        "kv_cache_tokens_per_rank": cache_tokens,
        "c2_median_ttft_ms": statistics.median(c2_ttft) if c2_ttft else None,
        "preemptions_delta": result["metadata"]["preemptions_delta"],
    }))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
