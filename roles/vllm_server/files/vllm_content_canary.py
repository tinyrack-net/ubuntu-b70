#!/usr/bin/env python3
"""Detect silent vLLM output corruption and restart after repeated failures."""

from __future__ import annotations

import argparse
import json
import subprocess
import urllib.error
import urllib.request
from pathlib import Path


def response_is_valid(content: str, marker: str) -> bool:
    normalized = content.strip()
    return marker in normalized and set(normalized) != {"!"}


def request_content(base_url: str, api_key: str, marker: str) -> str:
    models_request = urllib.request.Request(
        f"{base_url}/v1/models",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    with urllib.request.urlopen(models_request, timeout=30) as response:
        model = json.load(response)["data"][0]["id"]

    payload = json.dumps(
        {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": f"Reply with exactly {marker} and nothing else.",
                }
            ],
            "temperature": 0,
            "max_tokens": 64,
        }
    ).encode()
    completion_request = urllib.request.Request(
        f"{base_url}/v1/chat/completions",
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(completion_request, timeout=120) as response:
        body = json.load(response)
    return body["choices"][0]["message"].get("content") or ""


def update_failure_count(state_path: Path, failed: bool) -> int:
    if not failed:
        state_path.unlink(missing_ok=True)
        return 0
    try:
        previous = int(state_path.read_text().strip())
    except (FileNotFoundError, ValueError):
        previous = 0
    current = previous + 1
    state_path.write_text(f"{current}\n")
    return current


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--api-key-file", type=Path, required=True)
    parser.add_argument("--container", required=True)
    parser.add_argument("--marker", required=True)
    parser.add_argument("--failure-threshold", type=int, default=2)
    parser.add_argument("--state-file", type=Path, default=Path("/run/vllm-content-canary.failures"))
    args = parser.parse_args()

    failed = True
    try:
        api_key = args.api_key_file.read_text().strip()
        failed = not response_is_valid(
            request_content(args.base_url.rstrip("/"), api_key, args.marker),
            args.marker,
        )
    except (OSError, KeyError, IndexError, json.JSONDecodeError, urllib.error.URLError):
        failed = True

    failures = update_failure_count(args.state_file, failed)
    if failures >= args.failure_threshold:
        subprocess.run(["docker", "restart", args.container], check=True)
        args.state_file.unlink(missing_ok=True)
        print("vLLM content canary restarted the unhealthy container")
    elif failed:
        print(f"vLLM content canary failed ({failures}/{args.failure_threshold})")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
