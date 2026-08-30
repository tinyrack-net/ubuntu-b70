#!/usr/bin/env python3
"""Benchmark any OpenAI-compatible engine with client-observed streaming metrics."""

from __future__ import annotations

import json
import argparse
import math
import re
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.role_defaults import load_role_defaults

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "benchmarks" / "results"
PROMPT_CASES = (128, 512, 2048)
GENERATION_CASES = (128, 256)
REPETITIONS = 5
CONCURRENCY_REPETITIONS = 3
CONCURRENCY_LEVELS = (1, 2, 4, 8)


class BenchmarkError(RuntimeError):
    pass


def resolve_refs(values: dict[str, Any]) -> dict[str, Any]:
    def resolve(value: Any, resolving: frozenset[str] = frozenset()) -> Any:
        if isinstance(value, str):
            match = re.fullmatch(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}", value)
            if match and match.group(1) in values and match.group(1) not in resolving:
                name = match.group(1)
                return resolve(values[name], resolving | {name})
            return value
        if isinstance(value, list):
            return [resolve(item, resolving) for item in value]
        if isinstance(value, dict):
            return {key: resolve(item, resolving) for key, item in value.items()}
        return value

    return {key: resolve(value, frozenset({key})) for key, value in values.items()}


def inventory(profile: str = "inventory") -> dict[str, Any]:
    defaults_command = ["ansible-inventory", "--host", "ubuntu-gpu"]
    for role in ("llm_runtime", "llama_server", "vllm_server"):
        defaults_path = ROOT / "roles" / role / "defaults" / "main.yml"
        if defaults_path.exists():
            defaults_command.extend(["-e", f"@{defaults_path}"])
    command = ["ansible-inventory", "--host", "ubuntu-gpu"]
    profile_path = ROOT / "benchmarks" / "profiles" / f"{profile}.yml"
    if profile_path.exists():
        command.extend(["-e", f"@{profile_path}"])
    defaults_proc = subprocess.run(
        defaults_command, cwd=ROOT,
        check=True, capture_output=True, text=True,
    )
    proc = subprocess.run(
        command, cwd=ROOT,
        check=True, capture_output=True, text=True,
    )
    values = load_role_defaults(ROOT, ("llm_runtime", "llama_server", "vllm_server"))
    values.update(json.loads(defaults_proc.stdout))
    values.update(json.loads(proc.stdout))
    return resolve_refs(values)


class Client:
    def __init__(self, base_url: str, key: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.key = key

    def json(self, method: str, path: str, payload: Any | None = None) -> Any:
        data = None if payload is None else json.dumps(payload).encode()
        req = urllib.request.Request(
            self.base_url + path, data=data, method=method,
            headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=3600) as response:
                return json.loads(response.read())
        except (urllib.error.URLError, json.JSONDecodeError) as error:
            raise BenchmarkError(f"{method} {path} failed: {error}") from error

    def text(self, path: str) -> str:
        req = urllib.request.Request(
            self.base_url + path,
            headers={"Authorization": f"Bearer {self.key}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return response.read().decode()
        except urllib.error.URLError as error:
            raise BenchmarkError(f"GET {path} failed: {error}") from error

    def stream(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        wire = {key: value for key, value in payload.items() if not key.startswith("_")}
        data = json.dumps({**wire, "stream": True, "stream_options": {"include_usage": True}}).encode()
        req = urllib.request.Request(
            self.base_url + path, data=data, method="POST",
            headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"},
        )
        started = time.perf_counter()
        first: float | None = None
        last = started
        usage: dict[str, Any] = {}
        chunks = 0
        try:
            with urllib.request.urlopen(req, timeout=3600) as response:
                for raw in response:
                    line = raw.decode().strip()
                    if not line.startswith("data: ") or line == "data: [DONE]":
                        continue
                    event = json.loads(line[6:])
                    if event.get("usage"):
                        usage = event["usage"]
                    choices = event.get("choices") or []
                    text = choices[0].get("text", "") if choices else ""
                    if text:
                        now = time.perf_counter()
                        first = first or now
                        last = now
                        chunks += 1
        except (urllib.error.URLError, json.JSONDecodeError) as error:
            raise BenchmarkError(f"stream {path} failed: {error}") from error
        ended = time.perf_counter()
        if first is None:
            raise BenchmarkError("stream returned no output")
        prompt_n = int(usage.get("prompt_tokens", payload.get("_prompt_n", 0)))
        output_n = int(usage.get("completion_tokens", chunks))
        e2e_ms = (ended - started) * 1000
        ttft_ms = (first - started) * 1000
        tpot_ms = ((last - first) * 1000 / (output_n - 1)) if output_n > 1 else 0.0
        return {
            "prompt_tokens": prompt_n, "output_tokens": output_n, "chunks": chunks,
            "ttft_ms": ttft_ms, "tpot_ms": tpot_ms, "e2e_ms": e2e_ms,
            "prompt_tps": prompt_n / (ttft_ms / 1000),
            "decode_tps": (1000 / tpot_ms) if tpot_ms > 0 else 0.0,
        }


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = (len(ordered) - 1) * p / 100
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def stats(values: list[float]) -> dict[str, float]:
    return {
        "mean": statistics.mean(values), "median": statistics.median(values),
        "p95": percentile(values, 95), "min": min(values), "max": max(values),
    }


def parse_prometheus(payload: str) -> dict[str, float]:
    metrics: dict[str, float] = {}
    for line in payload.splitlines():
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([^\s{]+)(?:\{[^}]*\})?\s+([-+0-9.eE]+)(?:\s+\d+)?", line)
        if not match or "spec" not in match.group(1).lower():
            continue
        name, value = match.groups()
        metrics[name] = metrics.get(name, 0.0) + float(value)
    return metrics


def container_state(name: str) -> dict[str, Any]:
    proc = subprocess.run(
        ["ansible", "ubuntu-gpu", "-m", "command", "-a", f"docker inspect {name}"],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )
    inspected = json.loads(proc.stdout.split(">>\n", 1)[1])[0]
    state = inspected["State"]
    return {"status": state["Status"], "health": state.get("Health", {}).get("Status"),
            "oom_killed": state["OOMKilled"], "restart_count": inspected["RestartCount"],
            "image_id": inspected["Image"]}


def summarize(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for case in dict.fromkeys(item["case"] for item in samples):
        rows = [item for item in samples if item["case"] == case]
        result.append({"case": case, "n": len(rows),
                       **{metric: stats([float(row[metric]) for row in rows])
                          for metric in ("prompt_tps", "decode_tps", "ttft_ms", "tpot_ms", "e2e_ms")}})
    return result


def render_comparison(results: list[dict[str, Any]]) -> str:
    lines = ["# LLM engine benchmark", "", "Client-observed OpenAI streaming results; values are medians unless noted.", ""]
    for result in results:
        meta = result["metadata"]
        lines.extend([
            f"## {meta['engine']}", "",
            f"- Run: `{meta['run_id']}`",
            f"- Model: `{meta['model']}`",
            f"- Context: {meta['context_size']}", "",
            "| Case | Prompt tok/s | Decode tok/s | TTFT ms | TPOT ms |",
            "| --- | ---: | ---: | ---: | ---: |",
        ])
        for row in result["summary"]:
            lines.append(
                f"| {row['case']} | {row['prompt_tps']['median']:.2f} | "
                f"{row['decode_tps']['median']:.2f} | {row['ttft_ms']['median']:.2f} | "
                f"{row['tpot_ms']['median']:.2f} |"
            )
        lines.extend(["", "| Concurrency | Requests | Aggregate output tok/s | Median TTFT ms |", "| ---: | ---: | ---: | ---: |"])
        for row in result["concurrency"]:
            lines.append(
                f"| {row['concurrency']} | {row['requests']} | {row['output_tps']:.2f} | "
                f"{row['ttft_ms']['median']:.2f} |"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_comparison(current: dict[str, Any]) -> None:
    by_engine = {current["metadata"]["engine"]: current}
    for path in sorted(RESULTS.glob("*-openai.json"), reverse=True):
        candidate = json.loads(path.read_text())
        by_engine.setdefault(candidate["metadata"]["engine"], candidate)
    ordered = [by_engine[name] for name in ("llama_cpp", "vllm") if name in by_engine]
    (ROOT / "benchmarks" / "latest.md").write_text(render_comparison(ordered))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="inventory")
    parser.add_argument(
        "--target", action="append", default=[], metavar="PORT:CONTAINER",
        help="Benchmark target; repeat for replica round-robin",
    )
    return parser.parse_args()


def benchmark_environment(profile: str, inv: dict[str, Any], containers: set[str] | None = None) -> dict[str, Any]:
    values = dict(inv)
    instances = values.get("vllm_server_instances", [])
    if containers:
        instances = [item for item in instances if item["name"] in containers]
    tensor_parallel = [int(item.get("tensor_parallel_size", 1)) for item in instances]
    data_parallel = [int(item.get("data_parallel_size", 1)) for item in instances]
    topology = "data_parallel" if any(size > 1 for size in data_parallel) else (
        "tensor_parallel" if any(size > 1 for size in tensor_parallel) else (
        "replica" if len(instances) > 1 else "single_gpu"
        )
    )
    return {
        "topology": topology,
        "gpu_count": sum(tp * dp for tp, dp in zip(tensor_parallel, data_parallel, strict=True)),
        "xpu_graph_enabled": bool(instances[0].get(
            "enable_xpu_graph", values.get("vllm_server_enable_xpu_graph", True)
        )),
        "max_num_seqs": int(instances[0].get("max_num_seqs", values.get("vllm_server_max_num_seqs", 1))),
        "max_num_batched_tokens": int(instances[0].get(
            "max_num_batched_tokens", values.get("vllm_server_max_num_batched_tokens", 0)
        )),
        "prefix_caching_enabled": bool(instances[0].get(
            "enable_prefix_caching", values.get("vllm_server_enable_prefix_caching", True)
        )),
        "gpu_memory_utilization": float(instances[0].get(
            "gpu_memory_utilization", values.get("vllm_server_gpu_memory_utilization", 0)
        )),
        "instances": [
            {
                "name": item["name"],
                "port": int(item["port"]),
                "device_selector": item["device_selector"],
                "tensor_parallel_size": int(item.get("tensor_parallel_size", 1)),
                "data_parallel_size": int(item.get("data_parallel_size", 1)),
                "image": item.get("image", values.get("vllm_server_image")),
                "model": item.get("model", values.get("vllm_server_model")),
                "model_revision": item.get("model_revision", values.get("vllm_server_model_revision")),
                "kv_cache_dtype": item.get("kv_cache_dtype", values.get("vllm_server_kv_cache_dtype", "auto")),
                "max_num_batched_tokens": int(item.get(
                    "max_num_batched_tokens", values.get("vllm_server_max_num_batched_tokens", 0)
                )),
                "prefix_caching_enabled": bool(item.get(
                    "enable_prefix_caching", values.get("vllm_server_enable_prefix_caching", True)
                )),
                "xpu_graph_enabled": bool(item.get(
                    "enable_xpu_graph", values.get("vllm_server_enable_xpu_graph", True)
                )),
                "attention_backend": item.get("attention_backend", "auto"),
                "speculative_config": item.get("speculative_config"),
            }
            for item in instances
        ],
        "benchmark": {
            "prompt_token_cases": list(PROMPT_CASES),
            "generation_token_cases": list(GENERATION_CASES),
            "single_request_repetitions": REPETITIONS,
            "concurrency_levels": [
                int(level) for level in values.get(
                    "vllm_benchmark_concurrency_levels", CONCURRENCY_LEVELS
                )
            ],
            "concurrency_repetitions": CONCURRENCY_REPETITIONS,
            "concurrency_prompt_tokens": 512,
            "concurrency_output_tokens": 256,
        },
    }


def run() -> int:
    args = parse_args()
    inv = inventory(args.profile)
    concurrency_levels = tuple(
        int(level) for level in inv.get(
            "vllm_benchmark_concurrency_levels", CONCURRENCY_LEVELS
        )
    )
    key = inv["llm_api_key"]
    target_specs = args.target or [
        f"{inv['llm_runtime_port']}:{inv.get('llm_runtime_vllm_container_name', 'vllm-server')}"
    ]
    targets = []
    for spec in target_specs:
        port, container_name = spec.split(":", 1)
        targets.append({
            "port": int(port), "container": container_name,
            "client": Client(f"http://{inv['llm_runtime_bind_address']}:{port}", key),
        })
    client = targets[0]["client"]
    models = client.json("GET", "/v1/models")["data"]
    model = models[0]["id"]
    engine = inv.get("llm_runtime_engine", "vllm")
    containers = [target["container"] for target in targets]
    selected_instance = next(
        (item for item in inv.get("vllm_server_instances", []) if item["name"] == containers[0]),
        {},
    )
    before = {container: container_state(container) for container in containers}
    spec_before = parse_prometheus(client.text("/metrics"))
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    corpus = ("benchmark alpha beta gamma delta epsilon zeta eta theta " * 6000)
    try:
        tokenized = client.json("POST", "/tokenize", {"content": corpus})
    except BenchmarkError:
        tokenized = client.json("POST", "/tokenize", {"model": model, "prompt": corpus})
    tokens = tokenized.get("tokens") or tokenized.get("token_ids")
    if not tokens or len(tokens) < max(PROMPT_CASES):
        raise BenchmarkError("tokenize endpoint did not return enough token IDs")

    def request(prompt_n: int, output_n: int, nonce: int) -> dict[str, Any]:
        prompt_tokens = list(tokens[:prompt_n])
        prompt_tokens[-1] = tokens[prompt_n + nonce % 97]
        detokenized = client.json("POST", "/detokenize", {"model": model, "tokens": prompt_tokens})
        prompt = detokenized.get("content", detokenized.get("prompt"))
        if not isinstance(prompt, str):
            raise BenchmarkError("detokenize endpoint returned no prompt text")
        payload = {"model": model, "prompt": prompt, "max_tokens": output_n,
                   "temperature": 0, "seed": 42 + nonce, "ignore_eos": True,
                   "_prompt_n": prompt_n}
        wire = {key: value for key, value in payload.items() if not key.startswith("_")}
        selected = targets[nonce % len(targets)]["client"]
        measured = selected.stream("/v1/completions", {**wire, "_prompt_n": prompt_n})
        return measured

    print(f"Warming {engine}...", flush=True)
    for i in range(2):
        request(64, 32, i)
    samples: list[dict[str, Any]] = []
    nonce = 100
    for prompt_n in PROMPT_CASES:
        for rep in range(1, REPETITIONS + 1):
            print(f"pp{prompt_n} {rep}/{REPETITIONS}", flush=True)
            samples.append({"case": f"pp{prompt_n}", "repetition": rep,
                            **request(prompt_n, 1, nonce)})
            nonce += 1
    for output_n in GENERATION_CASES:
        for rep in range(1, REPETITIONS + 1):
            print(f"tg{output_n} {rep}/{REPETITIONS}", flush=True)
            samples.append({"case": f"tg{output_n}", "repetition": rep,
                            **request(64, output_n, nonce)})
            nonce += 1

    concurrency_results = []
    for concurrency in concurrency_levels:
        count = concurrency * 5
        rows = []
        output_rates = []
        request_rates = []
        durations = []
        for repetition in range(1, CONCURRENCY_REPETITIONS + 1):
            print(f"concurrency {concurrency}: round {repetition}/{CONCURRENCY_REPETITIONS}, {count} requests", flush=True)
            started = time.perf_counter()
            round_rows = []
            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                futures = [pool.submit(request, 512, 256, nonce + i) for i in range(count)]
                for future in as_completed(futures):
                    round_rows.append(future.result())
            duration = time.perf_counter() - started
            nonce += count
            rows.extend(round_rows)
            durations.append(duration)
            output_rates.append(sum(row["output_tokens"] for row in round_rows) / duration)
            request_rates.append(count / duration)
        concurrency_results.append({
            "concurrency": concurrency, "requests": count,
            "repetitions": CONCURRENCY_REPETITIONS,
            "duration_s": stats(durations),
            "request_tps": statistics.median(request_rates),
            "request_tps_stats": stats(request_rates),
            "output_tps": statistics.median(output_rates),
            "output_tps_stats": stats(output_rates),
            "ttft_ms": stats([row["ttft_ms"] for row in rows]),
            "tpot_ms": stats([row["tpot_ms"] for row in rows]),
        })

    after = {container: container_state(container) for container in containers}
    spec_after = parse_prometheus(client.text("/metrics"))
    spec_delta = {
        name: spec_after.get(name, 0.0) - spec_before.get(name, 0.0)
        for name in spec_after.keys() | spec_before.keys()
    }
    for container in containers:
        if (after[container]["restart_count"] != before[container]["restart_count"]
                or after[container]["oom_killed"]):
            raise BenchmarkError(f"{container} restarted or was OOM-killed")
    result = {"metadata": {"run_id": run_id, "engine": engine, "profile": args.profile,
                            "environment": benchmark_environment(args.profile, inv, set(containers)),
                            "targets": [{"port": target["port"], "container": target["container"]}
                                        for target in targets],
                            "model": model,
                            "context_size": selected_instance.get("context_size", inv.get("vllm_server_context_size", inv.get("llama_server_context_size"))),
                            "image": inv.get("vllm_server_image", inv.get("llama_server_intel_image")),
                            "model_revision": selected_instance.get("model_revision", inv.get("vllm_server_model_revision", inv.get("llama_server_model_revision"))),
                            "container_before": before, "container_after": after,
                            "speculative_metrics": {"before": spec_before, "after": spec_after, "delta": spec_delta}},
              "summary": summarize(samples), "concurrency": concurrency_results, "samples": samples}
    serialized = json.dumps(result, indent=2, sort_keys=True)
    if key in serialized:
        raise BenchmarkError("refusing to persist API key")
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / f"{run_id}-{engine}-openai.json"
    path.write_text(serialized + "\n")
    write_comparison(result)
    print(f"Wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(run())
    except (BenchmarkError, subprocess.CalledProcessError) as error:
        print(f"benchmark failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
