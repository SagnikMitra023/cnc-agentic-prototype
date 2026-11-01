"""
Live parser evaluation script.

Runs the golden set through the real LLM and prints:

    - latency: p50, p95, max (ms)
    - per-field extraction accuracy
    - action-level precision / recall / F1

The numbers produced by this script are the numbers that belong in
the metrics section (page 3.5) of the technical document.

Usage:
    ollama serve &
    python tools/measure_parser.py

Requires:
    tests/golden_set.py    (the hand-built evaluation set)
    main.py                (with interpret_command)
    Ollama running on 127.0.0.1:11434 with llama3.2:3b pulled
"""

import json
import sys
import time
from pathlib import Path

# Make the project root importable
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import main  # noqa: E402
from tests.golden_set import GOLDEN_SET  # noqa: E402


# Fields we measure. Kept in a stable order for reproducible output.
FIELDS = (
    "actions",
    "x",
    "y",
    "z",
    "spindle_speed",
    "feed_rate",
    "spindle_direction",
)


# ============================================================
# Helpers
# ============================================================

def empty_state(command: str) -> dict:
    """Build a fresh MachineState for one parser invocation."""
    return {
        "user_command": command,
        "actions": [],
        "x": None, "y": None, "z": None,
        "spindle_speed": None, "feed_rate": None,
        "valid": True, "validation_message": "",
        "approved": False,
        "machine_x": 0.0, "machine_y": 0.0, "machine_z": 0.0,
        "machine_spindle_speed": 0.0, "machine_feed_rate": 200.0,
        "spindle_on": False, "spindle_direction": None,
        "machine_spindle_direction": None,
        "gcode": "", "result": "",
    }


def action_set_match(predicted, gold) -> bool:
    """Compare action lists as sets — order is preserved by the parser,
    but a wrong order is a smaller problem than a wrong action."""
    return sorted(predicted or []) == sorted(gold or [])


# ============================================================
# Evaluation
# ============================================================

def run():
    print(f"Golden set size: {len(GOLDEN_SET)}")
    if not GOLDEN_SET:
        print("ERROR: golden set is empty — nothing to evaluate.")
        return 1

    # Warm-up: the first call to the LLM loads the model and is much
    # slower than steady-state. We exclude it from latency stats.
    print("Warming up...")
    for case in GOLDEN_SET[:2]:
        main.interpret_command(empty_state(case["command"]))

    latencies = []
    per_field_correct = {f: 0 for f in FIELDS}
    per_field_total = {f: 0 for f in FIELDS}

    # For action-level precision / recall / F1
    tp = fp = fn = 0

    # Also collect per-case failure detail so the output is useful
    # when a field regresses.
    failures = {f: [] for f in FIELDS}

    print("\nRunning evaluation...")
    for case in GOLDEN_SET:
        t0 = time.perf_counter()
        out = main.interpret_command(empty_state(case["command"]))
        latencies.append(time.perf_counter() - t0)

        gold = case["gold"]

        for f in FIELDS:
            per_field_total[f] += 1
            if f == "actions":
                ok = action_set_match(out["actions"], gold["actions"])
            else:
                ok = out[f] == gold[f]

            if ok:
                per_field_correct[f] += 1
            else:
                failures[f].append({
                    "command": case["command"],
                    "expected": gold[f],
                    "got": out[f],
                })

        # Action-level P/R/F1
        g = set(gold["actions"] or [])
        p = set(out["actions"] or [])
        tp += len(g & p)
        fp += len(p - g)
        fn += len(g - p)

    latencies.sort()
    n = len(latencies)

    # ---------------- Latency ----------------
    print("\n=== Latency ===")
    p50 = latencies[n // 2] * 1000
    p95 = latencies[int(n * 0.95)] * 1000
    max_ms = latencies[-1] * 1000
    print(f"p50 = {p50:.0f} ms")
    print(f"p95 = {p95:.0f} ms")
    print(f"max = {max_ms:.0f} ms")

    # ---------------- Per-field accuracy ----------------
    print("\n=== Per-field accuracy ===")
    per_field_summary = {}
    for f in FIELDS:
        correct = per_field_correct[f]
        total = per_field_total[f]
        acc = correct / total if total else 0.0
        per_field_summary[f] = {
            "correct": correct,
            "total": total,
            "accuracy": round(acc, 4),
        }
        print(f"{f:20s} {acc * 100:5.1f}%  ({correct}/{total})")
        if failures[f]:
            for fail in failures[f][:3]:   # show up to 3 examples per field
                print(f"    FAIL: {fail['command']!r}")
                print(f"          expected {fail['expected']!r}, "
                      f"got {fail['got']!r}")

    # ---------------- Action P/R/F1 ----------------
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = (2 * precision * recall / (precision + recall)
          if precision + recall else 0.0)

    print("\n=== Action precision / recall / F1 ===")
    print(f"precision = {precision:.3f}")
    print(f"recall    = {recall:.3f}")
    print(f"F1        = {f1:.3f}")

    # ---------------- Save machine-readable summary ----------------
    summary = {
        "n": n,
        "latency_ms": {
            "p50": round(p50),
            "p95": round(p95),
            "max": round(max_ms),
        },
        "per_field_accuracy": {
            f: per_field_summary[f]["accuracy"] for f in FIELDS
        },
        "action": {
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(f1, 3),
        },
    }

    out_path = ROOT / "tests" / "metrics.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2))
    print(f"\nSaved: {out_path.relative_to(ROOT)}")

    return 0


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":
    sys.exit(run())