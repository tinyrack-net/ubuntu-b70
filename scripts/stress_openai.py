#!/usr/bin/env python3
"""Run a content-validating C4 soak against an OpenAI-compatible endpoint."""

from __future__ import annotations

import argparse
import json
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from scripts.benchmark_openai import Client, container_state, inventory


MARKER = "B70_STRESS_OK"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True)
    parser.add_argument("--port", type=int, default=8081)
    parser.add_argument("--container", default="vllm-candidate")
    parser.add_argument("--duration", type=int, default=300)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    inv = inventory(args.profile)
    client = Client(f"http://{inv['llm_runtime_bind_address']}:{args.port}", inv["llm_api_key"])
    model = client.json("GET", "/v1/models")["data"][0]["id"]
    before = container_state(args.container)
    prompts = [
        f"Reply with exactly {MARKER} and nothing else.",
        f"다른 말 없이 정확히 {MARKER}만 답하세요.",
        f"Read this code: `sum(range(11))`. Ignore its result and output exactly {MARKER}.",
        ("long-context filler " * 4096) + f"\nOutput exactly {MARKER} and nothing else.",
    ]
    deadline = time.monotonic() + args.duration
    lock = threading.Lock()
    counts = {"ok": 0, "bad_content": 0, "errors": 0}
    latencies: list[float] = []

    def worker(index: int) -> None:
        iteration = index
        while time.monotonic() < deadline:
            started = time.monotonic()
            try:
                response = client.json("POST", "/v1/chat/completions", {
                    "model": model,
                    "messages": [{"role": "user", "content": prompts[iteration % len(prompts)]}],
                    "temperature": 0,
                    "seed": 0,
                    "max_tokens": 32,
                })
                content = (response["choices"][0]["message"].get("content") or "").strip()
                key = "ok" if MARKER in content and set(content) != {"!"} else "bad_content"
            except Exception:  # The result records failures without exposing credentials or bodies.
                key = "errors"
            with lock:
                counts[key] += 1
                latencies.append((time.monotonic() - started) * 1000)
            iteration += args.concurrency

    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = [pool.submit(worker, index) for index in range(args.concurrency)]
        for future in futures:
            future.result()

    tool_response = client.json("POST", "/v1/chat/completions", {
        "model": model,
        "messages": [{"role": "user", "content": "Use lookup_temperature for Seoul."}],
        "temperature": 0,
        "max_tokens": 128,
        "tools": [{"type": "function", "function": {
            "name": "lookup_temperature",
            "description": "Look up a city's temperature",
            "parameters": {"type": "object", "properties": {
                "city": {"type": "string"}}, "required": ["city"]},
        }}],
        "tool_choice": "required",
    })
    calls = tool_response["choices"][0]["message"].get("tool_calls") or []
    tool_ok = bool(calls and calls[0].get("function", {}).get("name") == "lookup_temperature")
    after = container_state(args.container)
    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "profile": args.profile,
        "duration_s": args.duration,
        "concurrency": args.concurrency,
        "counts": counts,
        "latency_ms": {
            "median": statistics.median(latencies),
            "max": max(latencies),
        },
        "tool_call_ok": tool_ok,
        "container_before": before,
        "container_after": after,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    stable = (after["restart_count"] == before["restart_count"] and not after["oom_killed"])
    passed = counts["bad_content"] == 0 and counts["errors"] == 0 and tool_ok and stable
    print(json.dumps({"passed": passed, "counts": counts, "tool_call_ok": tool_ok, "stable": stable}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
