#!/usr/bin/env python3
"""Hash deterministic OpenAI chat outputs for MTP on/off comparison."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from scripts.benchmark_openai import Client, inventory


PROMPTS = {
    "marker": "Reply with exactly B70_DETERMINISTIC_OK and nothing else.",
    "korean": "대한민국의 수도를 한 단어로 답하세요.",
    "code": "Return only a Python expression that sums integers from 1 through 10.",
    "reasoning": "What is 37 * 19? Return only the integer.",
}


def digest(value: object) -> str:
    wire = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(wire.encode()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True)
    parser.add_argument("--port", type=int, default=8081)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--compare", type=Path)
    args = parser.parse_args()

    inv = inventory(args.profile)
    client = Client(f"http://{inv['llm_runtime_bind_address']}:{args.port}", inv["llm_api_key"])
    model = client.json("GET", "/v1/models")["data"][0]["id"]
    hashes: dict[str, str] = {}
    for name, prompt in PROMPTS.items():
        response = client.json("POST", "/v1/chat/completions", {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "seed": 0,
            "max_tokens": 128,
        })
        choice = response["choices"][0]
        hashes[name] = digest({"message": choice["message"], "finish_reason": choice["finish_reason"]})

    result = {"profile": args.profile, "temperature": 0, "seed": 0, "hashes": hashes}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    if args.compare:
        expected = json.loads(args.compare.read_text())["hashes"]
        if hashes != expected:
            mismatches = sorted(name for name in hashes if hashes[name] != expected.get(name))
            print(f"deterministic output mismatch: {', '.join(mismatches)}")
            return 1
        print(f"all {len(hashes)} deterministic output hashes match")
    else:
        print(f"captured {len(hashes)} deterministic output hashes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
