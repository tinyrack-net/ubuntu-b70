#!/usr/bin/env python3
"""Compare paired vLLM OpenAI benchmarks with XPU Graph on and off."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any


def percent_change(candidate: float, baseline: float) -> float:
    if baseline == 0:
        raise ValueError("cannot compare against a zero baseline")
    return (candidate / baseline - 1.0) * 100.0


def load_run(path: Path, expected_graph: bool) -> dict[str, Any]:
    result = json.loads(path.read_text())
    metadata = result["metadata"]
    instances = metadata["environment"]["instances"]
    if len(instances) != 1:
        raise ValueError(f"{path}: expected exactly one vLLM instance")
    graph = bool(instances[0]["xpu_graph_enabled"])
    if graph != expected_graph:
        raise ValueError(f"{path}: xpu_graph_enabled={graph}, expected {expected_graph}")
    return result


def extract_metrics(result: dict[str, Any]) -> dict[str, float]:
    metrics: dict[str, float] = {}
    for row in result["summary"]:
        case = row["case"]
        if case.startswith("pp"):
            metrics[f"{case}_prompt_tps"] = float(row["prompt_tps"]["median"])
        elif case.startswith("tg"):
            metrics[f"{case}_decode_tps"] = float(row["decode_tps"]["median"])
    for row in result["concurrency"]:
        prefix = f"c{int(row['concurrency'])}"
        metrics[f"{prefix}_output_tps"] = float(row["output_tps"])
        metrics[f"{prefix}_ttft_ms"] = float(row["ttft_ms"]["median"])
        metrics[f"{prefix}_tpot_ms"] = float(row["tpot_ms"]["median"])
    return metrics


def median_metrics(results: list[dict[str, Any]]) -> dict[str, float]:
    extracted = [extract_metrics(result) for result in results]
    keys = set(extracted[0])
    if any(set(row) != keys for row in extracted[1:]):
        raise ValueError("benchmark metric sets do not match")
    return {
        key: statistics.median(row[key] for row in extracted)
        for key in sorted(keys)
    }


def classify(changes: dict[str, float]) -> str:
    tps_loss = max(0.0, -changes["c1_output_tps"], -changes["c8_output_tps"])
    ttft_increase = max(0.0, changes["c1_ttft_ms"], changes["c8_ttft_ms"])
    if tps_loss <= 5.0 and ttft_increase <= 10.0:
        return "no_material_regression"
    if tps_loss <= 15.0:
        return "tradeoff"
    return "unsuitable"


def compare(on_results: list[dict[str, Any]], off_results: list[dict[str, Any]]) -> dict[str, Any]:
    contexts = {
        int(result["metadata"]["context_size"])
        for result in (*on_results, *off_results)
    }
    if len(contexts) != 1:
        raise ValueError(f"benchmarks must use one context size, got {sorted(contexts)}")
    models = {result["metadata"]["model"] for result in (*on_results, *off_results)}
    if len(models) != 1:
        raise ValueError("benchmarks must use the same served model")
    on = median_metrics(on_results)
    off = median_metrics(off_results)
    changes = {key: percent_change(off[key], on[key]) for key in sorted(on)}
    return {
        "context_size": contexts.pop(),
        "model": models.pop(),
        "graph_on_runs": len(on_results),
        "graph_off_runs": len(off_results),
        "graph_on": on,
        "graph_off": off,
        "off_vs_on_percent": changes,
        "classification": classify(changes),
    }


def render_markdown(result: dict[str, Any]) -> str:
    rows = [
        "# XPU Graph OFF performance comparison",
        "",
        f"Context: {result['context_size']}; model: `{result['model']}`; "
        f"classification: `{result['classification']}`.",
        "",
        "| Metric | Graph ON | Graph OFF | OFF vs ON |",
        "| --- | ---: | ---: | ---: |",
    ]
    for key, on_value in result["graph_on"].items():
        rows.append(
            f"| {key} | {on_value:.2f} | {result['graph_off'][key]:.2f} | "
            f"{result['off_vs_on_percent'][key]:+.2f}% |"
        )
    return "\n".join(rows) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--on", type=Path, action="append", required=True)
    parser.add_argument("--off", type=Path, action="append", required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-markdown", type=Path, required=True)
    args = parser.parse_args()
    result = compare(
        [load_run(path, True) for path in args.on],
        [load_run(path, False) for path in args.off],
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_markdown.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    args.output_markdown.write_text(render_markdown(result))
    print(json.dumps({
        "classification": result["classification"],
        "output_json": str(args.output_json),
        "output_markdown": str(args.output_markdown),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
