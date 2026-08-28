#!/usr/bin/env python3
"""Benchmark the live llama.cpp HTTP API without restarting the service."""

from __future__ import annotations

import json
import re
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "benchmarks" / "results"
LATEST_REPORT = ROOT / "benchmarks" / "latest.md"
PROMPT_CASES = (128, 512, 2048)
GENERATION_CASES = (128, 256)
REPETITIONS = 5
CHAT_REPETITIONS = 3


class BenchmarkError(RuntimeError):
    """A benchmark precondition or request failed."""


class LlamaClient:
    def __init__(self, base_url: str, api_key: str, timeout: int = 3600) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def request(self, method: str, path: str, payload: Any | None = None) -> tuple[Any, float]:
        data = None if payload is None else json.dumps(payload).encode()
        headers = {"Authorization": f"Bearer {self.api_key}"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            f"{self.base_url}{path}", data=data, headers=headers, method=method
        )
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read())
        except (urllib.error.URLError, json.JSONDecodeError) as error:
            raise BenchmarkError(f"{method} {path} failed: {error}") from error
        return body, (time.perf_counter() - started) * 1000


def load_inventory() -> dict[str, Any]:
    process = subprocess.run(
        ["ansible-inventory", "--host", "ubuntu-gpu"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    inventory = resolve_inventory_refs(json.loads(process.stdout))
    required = ("llama_api_key", "llama_bind_address", "llama_port", "llama_model_file")
    missing = [name for name in required if not inventory.get(name)]
    if missing:
        raise BenchmarkError(f"inventory is missing required values: {', '.join(missing)}")
    return inventory


def resolve_inventory_refs(inventory: dict[str, Any]) -> dict[str, Any]:
    resolved = dict(inventory)
    for name, value in list(inventory.items()):
        if isinstance(value, str):
            match = re.fullmatch(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}", value)
            if match and match.group(1) in inventory:
                resolved[name] = inventory[match.group(1)]
    return resolved


def git_sha() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()


def container_state() -> dict[str, Any]:
    process = subprocess.run(
        ["ansible", "ubuntu-gpu", "-m", "command", "-a", "docker inspect llama-server"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    marker = ">>\n"
    if marker not in process.stdout:
        raise BenchmarkError("could not parse docker inspect output")
    inspected = json.loads(process.stdout.split(marker, 1)[1])[0]
    state = inspected["State"]
    return {
        "status": state["Status"],
        "health": state.get("Health", {}).get("Status"),
        "oom_killed": state["OOMKilled"],
        "restart_count": inspected["RestartCount"],
        "image_id": inspected["Image"],
    }


def preflight(client: LlamaClient) -> tuple[dict[str, Any], dict[str, Any]]:
    health, _ = client.request("GET", "/health")
    if health.get("status") != "ok":
        raise BenchmarkError(f"server is not healthy: {health}")
    slots, _ = client.request("GET", "/slots")
    if any(slot.get("is_processing") for slot in slots):
        raise BenchmarkError("server is currently processing another request")
    props, _ = client.request("GET", "/props")
    return props, container_state()


def build_token_corpus(client: LlamaClient, minimum: int) -> list[int]:
    phrase = "benchmark alpha beta gamma delta epsilon zeta eta theta "
    tokenized, _ = client.request("POST", "/tokenize", {"content": phrase * (minimum // 4 + 64)})
    tokens = tokenized.get("tokens", [])
    if len(tokens) < minimum:
        raise BenchmarkError(f"tokenizer returned only {len(tokens)} tokens; need {minimum}")
    return tokens


def synthetic_request(
    client: LlamaClient,
    tokens: list[int],
    prompt_n: int,
    generation_n: int,
) -> tuple[dict[str, Any], float]:
    return client.request(
        "POST",
        "/completion",
        {
            "prompt": tokens[:prompt_n],
            "n_predict": generation_n,
            "cache_prompt": False,
            "ignore_eos": True,
            "temperature": 0,
            "seed": 42,
        },
    )


def sample_record(
    case: str,
    kind: str,
    repetition: int,
    response: dict[str, Any],
    wall_ms: float,
    requested_prompt_n: int | None,
    requested_generation_n: int | None,
) -> dict[str, Any]:
    timings = response.get("timings") or {}
    usage = response.get("usage") or {}
    return {
        "case": case,
        "kind": kind,
        "repetition": repetition,
        "requested_prompt_n": requested_prompt_n,
        "requested_generation_n": requested_generation_n,
        "wall_ms": wall_ms,
        "finish_reason": (response.get("choices") or [{}])[0].get("finish_reason"),
        "prompt_n": timings.get("prompt_n", usage.get("prompt_tokens")),
        "cache_n": timings.get("cache_n", 0),
        "predicted_n": timings.get("predicted_n", usage.get("completion_tokens")),
        "prompt_ms": timings.get("prompt_ms"),
        "predicted_ms": timings.get("predicted_ms"),
        "prompt_tps": timings.get("prompt_per_second"),
        "predicted_tps": timings.get("predicted_per_second"),
    }


def validate_samples(samples: list[dict[str, Any]]) -> None:
    if not samples:
        raise BenchmarkError("benchmark produced no samples")
    for sample in samples:
        if sample["kind"] in {"prompt", "generation"} and sample["cache_n"] != 0:
            raise BenchmarkError(f"{sample['case']} unexpectedly reused {sample['cache_n']} tokens")
        if sample["kind"] == "generation" and sample["predicted_n"] != sample["requested_generation_n"]:
            raise BenchmarkError(
                f"{sample['case']} generated {sample['predicted_n']} tokens, "
                f"expected {sample['requested_generation_n']}"
            )
        if sample["kind"] != "prompt" and (
            not isinstance(sample.get("predicted_tps"), (int, float))
            or sample["predicted_tps"] <= 0
        ):
            raise BenchmarkError(f"{sample['case']} returned invalid generation TPS")
        if not isinstance(sample.get("prompt_tps"), (int, float)) or sample["prompt_tps"] <= 0:
            raise BenchmarkError(f"{sample['case']} returned invalid prompt TPS")


def metric_stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {}
    return {
        "mean": statistics.mean(values),
        "median": statistics.median(values),
        "stdev": statistics.stdev(values) if len(values) > 1 else 0.0,
        "min": min(values),
        "max": max(values),
    }


def summarize_results(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for sample in samples:
        grouped[sample["case"]].append(sample)
    summary = []
    for case, case_samples in grouped.items():
        summary.append(
            {
                "case": case,
                "kind": case_samples[0]["kind"],
                "samples": len(case_samples),
                "prompt_tps": metric_stats([float(item["prompt_tps"]) for item in case_samples]),
                "predicted_tps": metric_stats([float(item["predicted_tps"]) for item in case_samples]),
                "wall_ms": metric_stats([float(item["wall_ms"]) for item in case_samples]),
            }
        )
    return summary


def render_markdown(result: dict[str, Any], result_path: Path) -> str:
    metadata = result["metadata"]
    lines = [
        "# Latest API TPS benchmark",
        "",
        f"- Run: `{metadata['run_id']}`",
        f"- Git: `{metadata['git_sha']}`",
        f"- Model: `{metadata['model_file']}`",
        f"- Backend/context/parallel: `{metadata['backend']}` / `{metadata['context_size']}` / `{metadata['parallel']}`",
        f"- Raw result: [`{result_path.name}`](results/{result_path.name})",
        "",
        "| Case | Kind | N | Prompt t/s mean | Decode t/s mean | Wall ms median |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for item in result["summary"]:
        lines.append(
            f"| {item['case']} | {item['kind']} | {item['samples']} | "
            f"{item['prompt_tps']['mean']:.2f} | {item['predicted_tps']['mean']:.2f} | "
            f"{item['wall_ms']['median']:.2f} |"
        )
    lines.extend(
        [
            "",
            "Synthetic cases disable prompt caching. Chat cases use the OpenAI-compatible route and report actual generated token counts.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    inventory = load_inventory()
    base_url = f"http://{inventory['llama_bind_address']}:{inventory['llama_port']}"
    client = LlamaClient(base_url, inventory["llama_api_key"])
    props, state_before = preflight(client)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    tokens = build_token_corpus(client, max(PROMPT_CASES))
    samples: list[dict[str, Any]] = []

    print("Warming up the live API...", flush=True)
    for _ in range(2):
        synthetic_request(client, tokens, 64, 32)

    for prompt_n in PROMPT_CASES:
        case = f"pp{prompt_n}"
        for repetition in range(1, REPETITIONS + 1):
            print(f"{case} {repetition}/{REPETITIONS}", flush=True)
            response, wall_ms = synthetic_request(client, tokens, prompt_n, 1)
            samples.append(sample_record(case, "prompt", repetition, response, wall_ms, prompt_n, 1))

    for generation_n in GENERATION_CASES:
        case = f"tg{generation_n}"
        for repetition in range(1, REPETITIONS + 1):
            print(f"{case} {repetition}/{REPETITIONS}", flush=True)
            response, wall_ms = synthetic_request(client, tokens, 64, generation_n)
            samples.append(
                sample_record(case, "generation", repetition, response, wall_ms, 64, generation_n)
            )

    for repetition in range(1, CHAT_REPETITIONS + 1):
        print(f"chat128 {repetition}/{CHAT_REPETITIONS}", flush=True)
        response, wall_ms = client.request(
            "POST",
            "/v1/chat/completions",
            {
                "model": inventory["llama_model_file"],
                "messages": [
                    {"role": "system", "content": f"Benchmark run {run_id}, sample {repetition}."},
                    {"role": "user", "content": "Explain in Korean why reproducible benchmarks matter."},
                ],
                "max_tokens": 128,
                "cache_prompt": False,
                "temperature": 0,
                "seed": 42,
            },
        )
        samples.append(sample_record("chat128", "chat", repetition, response, wall_ms, None, 128))

    validate_samples(samples)
    state_after = container_state()
    if state_after["restart_count"] != state_before["restart_count"] or state_after["oom_killed"]:
        raise BenchmarkError("container restarted or was OOM-killed during the benchmark")

    metadata = {
        "run_id": run_id,
        "git_sha": git_sha(),
        "model_file": inventory["llama_model_file"],
        "model_revision": inventory.get("llama_model_revision"),
        "model_checksum": inventory.get("llama_model_checksum"),
        "backend": inventory.get("llama_backend"),
        "context_size": inventory.get("llama_context_size"),
        "parallel": inventory.get("llama_parallel"),
        "image": inventory.get("llama_intel_image"),
        "server_build": props.get("build_info"),
        "model_alias": props.get("model_alias"),
        "model_ftype": props.get("model_ftype"),
        "modalities": props.get("modalities"),
        "container_before": state_before,
        "container_after": state_after,
    }
    result = {"metadata": metadata, "summary": summarize_results(samples), "samples": samples}
    serialized = json.dumps(result, indent=2, sort_keys=True)
    if inventory["llama_api_key"] in serialized:
        raise BenchmarkError("refusing to persist a result containing the API key")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    result_path = RESULTS_DIR / f"{run_id}-api.json"
    result_path.write_text(serialized + "\n")
    LATEST_REPORT.parent.mkdir(parents=True, exist_ok=True)
    LATEST_REPORT.write_text(render_markdown(result, result_path))
    print(f"Wrote {result_path.relative_to(ROOT)}")
    print(f"Wrote {LATEST_REPORT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BenchmarkError, subprocess.CalledProcessError) as error:
        print(f"benchmark failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
