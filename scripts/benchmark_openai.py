#!/usr/bin/env python3
"""Benchmark any OpenAI-compatible engine with client-observed streaming metrics."""

from __future__ import annotations

import json
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


class BenchmarkError(RuntimeError):
    pass


def resolve_refs(values: dict[str, Any]) -> dict[str, Any]:
    resolved = dict(values)
    for key, value in values.items():
        if isinstance(value, str):
            match = re.fullmatch(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}", value)
            if match and match.group(1) in values:
                resolved[key] = values[match.group(1)]
    return resolved


def inventory() -> dict[str, Any]:
    proc = subprocess.run(
        ["ansible-inventory", "--host", "ubuntu-gpu"], cwd=ROOT,
        check=True, capture_output=True, text=True,
    )
    values = load_role_defaults(ROOT, ("llm_runtime", "llama_server", "vllm_server"))
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


def run() -> int:
    inv = inventory()
    key = inv["llm_api_key"]
    base = f"http://{inv['llm_runtime_bind_address']}:{inv['llm_runtime_port']}"
    client = Client(base, key)
    models = client.json("GET", "/v1/models")["data"]
    model = models[0]["id"]
    engine = inv.get("llm_runtime_engine", "vllm")
    container = (inv.get("llm_runtime_vllm_container_name", "vllm-server")
                 if engine == "vllm"
                 else inv.get("llm_runtime_llama_container_name", "llama-server"))
    before = container_state(container)
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
        measured = client.stream("/v1/completions", {**wire, "_prompt_n": prompt_n})
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
    for concurrency in (1, 2, 4):
        count = concurrency * 5
        print(f"concurrency {concurrency}: {count} requests", flush=True)
        started = time.perf_counter()
        rows = []
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = [pool.submit(request, 512, 256, nonce + i) for i in range(count)]
            for future in as_completed(futures):
                rows.append(future.result())
        duration = time.perf_counter() - started
        nonce += count
        concurrency_results.append({
            "concurrency": concurrency, "requests": count, "duration_s": duration,
            "request_tps": count / duration,
            "output_tps": sum(row["output_tokens"] for row in rows) / duration,
            "ttft_ms": stats([row["ttft_ms"] for row in rows]),
            "tpot_ms": stats([row["tpot_ms"] for row in rows]),
        })

    after = container_state(container)
    if after["restart_count"] != before["restart_count"] or after["oom_killed"]:
        raise BenchmarkError("container restarted or was OOM-killed")
    result = {"metadata": {"run_id": run_id, "engine": engine, "model": model,
                            "context_size": inv.get("vllm_server_context_size", inv.get("llama_server_context_size")),
                            "image": inv.get("vllm_server_image", inv.get("llama_server_intel_image")),
                            "model_revision": inv.get("vllm_server_model_revision", inv.get("llama_server_model_revision")),
                            "container_before": before, "container_after": after},
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
