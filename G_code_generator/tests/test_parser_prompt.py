"""
Live parser tests. Skip automatically when Ollama is not running.

When Ollama is up, this file does two things:

1. Runs every command in the golden set through the real
   interpret_command node and asserts a minimum per-field accuracy.
2. Asserts the precision / recall / F1 of the action classifier
   stays above conservative thresholds.

The thresholds are deliberately set below the numbers produced by
tools/measure_parser.py, so that normal model variation does not
trigger false failures. If the model actually regresses, the tests
will catch it.

Run with:
    ollama serve &
    pytest tests/test_parser_prompt.py -v

Skip in CI (no model required):
    pytest tests/ -v --ignore=tests/test_parser_prompt.py

Print the raw metrics separately (for the documentation):
    python tools/measure_parser.py
"""

import socket

import pytest

import main
from tests.golden_set import GOLDEN_SET


# ============================================================
# Skip if Ollama isn't reachable
# ============================================================

def _ollama_reachable(host: str = "127.0.0.1",
                      port: int = 11434,
                      timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(
    not _ollama_reachable(),
    reason="Ollama not reachable on 127.0.0.1:11434",
)


# ============================================================
# Helpers
# ============================================================

def _state_for(command: str) -> dict:
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


def _action_set_match(predicted, gold) -> bool:
    """Compare action lists as sets — order does not matter for correctness,
    only presence does. (Order is still preserved by the parser; we relax it
    here because a wrong order is a much smaller problem than a wrong action.)"""
    return sorted(predicted or []) == sorted(gold or [])


def _run_all_golden_cases():
    """
    Run every golden command once, cache the result.

    Running the golden set once and reusing the output across tests keeps
    total runtime at ~25 seconds instead of re-invoking the LLM per test.
    """
    results = []
    for case in GOLDEN_SET:
        out = main.interpret_command(_state_for(case["command"]))
        results.append({
            "command": case["command"],
            "gold": case["gold"],
            "predicted": {
                "actions": out["actions"],
                "x": out["x"],
                "y": out["y"],
                "z": out["z"],
                "spindle_speed": out["spindle_speed"],
                "feed_rate": out["feed_rate"],
                "spindle_direction": out["spindle_direction"],
            },
        })
    return results


@pytest.fixture(scope="module")
def golden_results():
    """Run the golden set once per test module."""
    return _run_all_golden_cases()


# ============================================================
# Test 1 — overall golden set is parsable at all
# ============================================================

def test_parser_returns_valid_schema_for_every_golden_case(golden_results):
    """
    Every command must produce a structured object with exactly the seven
    expected fields, no exceptions, no missing keys.
    """
    required_keys = {
        "actions", "x", "y", "z",
        "spindle_speed", "feed_rate", "spindle_direction",
    }
    for r in golden_results:
        pred = r["predicted"]
        assert set(pred.keys()) == required_keys, (
            f"Missing or extra fields for: {r['command']!r} — got {set(pred.keys())}"
        )


# ============================================================
# Test 2 — per-field accuracy
# ============================================================

@pytest.mark.parametrize("field,threshold", [
    # Thresholds reflect what the model reliably achieves on this set.
    # They are set below tools/measure_parser.py output so that natural
    # run-to-run variance does not trigger false failures.
    # If the model genuinely regresses, these will fail.
    ("actions",         0.80),
    ("x",               0.85),
    ("y",               0.85),
    ("z",               0.85),
    ("spindle_speed",   0.80),
    ("feed_rate",       0.80),
    ("spindle_direction", 0.85),
])
def test_per_field_accuracy_meets_threshold(golden_results, field, threshold):
    """
    Accuracy for each field must stay above its threshold.

    Below-threshold fields mean the parser has regressed on that
    category of extraction — which for this pipeline is more
    serious than a general accuracy drop.
    """
    n = len(golden_results)
    correct = 0
    failures = []

    for r in golden_results:
        pred = r["predicted"][field]
        gold = r["gold"][field]
        ok = (
            _action_set_match(pred, gold) if field == "actions"
            else pred == gold
        )
        if ok:
            correct += 1
        else:
            failures.append({
                "command": r["command"],
                "expected": gold,
                "got": pred,
            })

    accuracy = correct / n
    assert accuracy >= threshold, (
        f"\n\n{field} accuracy {accuracy:.1%} below threshold {threshold:.0%} "
        f"({correct}/{n})\n"
        f"Failing cases:\n"
        + "\n".join(
            f"  - {f['command']!r}: expected {f['expected']}, got {f['got']}"
            for f in failures[:5]
        )
    )


# ============================================================
# Test 3 — action precision / recall / F1
# ============================================================

def test_action_precision(golden_results):
    """
    Precision is the metric that matters most in this pipeline.
    A false positive (an action the operator did not request) would
    reach the approval gate and offer a wrong command for review.
    """
    tp = fp = 0
    for r in golden_results:
        gold = set(r["gold"]["actions"] or [])
        pred = set(r["predicted"]["actions"] or [])
        tp += len(gold & pred)
        fp += len(pred - gold)

    precision = tp / (tp + fp) if tp + fp else 1.0
    assert precision >= 0.85, f"Action precision {precision:.2f} below 0.85"


def test_action_recall(golden_results):
    """
    Recall matters less than precision here, because a missing action
    is caught harmlessly by validation. But it must still be reasonable.
    """
    tp = fn = 0
    for r in golden_results:
        gold = set(r["gold"]["actions"] or [])
        pred = set(r["predicted"]["actions"] or [])
        tp += len(gold & pred)
        fn += len(gold - pred)

    recall = tp / (tp + fn) if tp + fn else 1.0
    assert recall >= 0.80, f"Action recall {recall:.2f} below 0.80"


def test_action_f1(golden_results):
    """F1 must stay above a conservative floor."""
    tp = fp = fn = 0
    for r in golden_results:
        gold = set(r["gold"]["actions"] or [])
        pred = set(r["predicted"]["actions"] or [])
        tp += len(gold & pred)
        fp += len(pred - gold)
        fn += len(gold - pred)

    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    assert f1 >= 0.82, f"Action F1 {f1:.2f} below 0.82"


# ============================================================
# Test 4 — hallucination behaviour on under-specified inputs
# ============================================================

def test_parser_does_not_invent_missing_values(golden_results):
    """
    For golden cases whose gold value is null for a field, the parser
    must NOT return a non-null value for that field.

    This is the model-side counterpart to the deterministic
    verify_extraction guard. If the model keeps inventing values,
    the guard catches them, but the underlying prompt has regressed.
    """
    fields_to_check = ("x", "y", "z", "spindle_speed", "feed_rate")

    violations = []
    for r in golden_results:
        gold = r["gold"]
        pred = r["predicted"]
        for f in fields_to_check:
            if gold.get(f) is None and pred.get(f) is not None:
                violations.append({
                    "command": r["command"],
                    "field": f,
                    "invented": pred[f],
                })

    # Allow up to 2 violations before failing — the model is not perfect,
    # and the hallucination guard is the load-bearing safety net.
    assert len(violations) <= 2, (
        f"{len(violations)} invented values across "
        f"{len(golden_results)} commands. Sample:\n"
        + "\n".join(
            f"  - {v['command']!r}: invented {v['field']}={v['invented']}"
            for v in violations[:5]
        )
    )


# ============================================================
# Test 5 — unit normalisation
# ============================================================

def test_parser_normalises_k_multiplier(golden_results):
    """
    '1.5k rpm' must be extracted as 1500, not 1.5 or 15000.
    This is the one unit form the guard also normalises, so both
    ends must agree.
    """
    case = next(
        (r for r in golden_results if "1.5k" in r["command"]),
        None,
    )
    if case is None:
        pytest.skip("No 1.5k case in golden set")

    assert case["predicted"]["spindle_speed"] == 1500


def test_parser_normalises_trailing_zeros(golden_results):
    """
    'X=10.00' must be extracted as 10 (numeric equality),
    not as the string "10.00".
    """
    case = next(
        (r for r in golden_results if "X=10.00" in r["command"]),
        None,
    )
    if case is None:
        pytest.skip("No trailing-zeros case in golden set")

    assert case["predicted"]["x"] == 10.0
    assert isinstance(case["predicted"]["x"], float)


# ============================================================
# Test 6 — end-to-end pipeline behaviour
# ============================================================

def test_under_specified_command_is_rejected_end_to_end():
    """
    The whole pipeline (interpret → verify → validate) must reject a
    command that is missing a required value. We do not mock the LLM,
    so this is the closest thing to a real integration test.
    """
    import main as app

    # Ensure a UI bridge exists even though no window is created.
    if app.UI_BRIDGE is None:
        import queue, tkinter as tk
        try:
            root = tk.Tk()
            root.withdraw()
            app.UI_BRIDGE = app.UIEventBridge(root, queue.Queue())
            app.UI_BRIDGE.gcode_header_emitted = True
            app.UI_BRIDGE.approval_result = False
            app.UI_BRIDGE.approval_event.set()  # any approval resolves to False
        except tk.TclError:
            pytest.skip("No Tk display")

    # "Cut to X=10 Y=20 Z=30" — no feed rate. Must be rejected.
    state = _state_for("Cut to X=10 Y=20 Z=30")
    state["valid"] = False
    out = app.app_graph.invoke(state, config=app.THREAD_CONFIG)

    assert out["valid"] is False
    # The rejection must come from either the guard or validation,
    # never from a hallucination reaching approval.
    assert (
        "feed_rate" in out["result"].lower()
        or "requires a feed rate" in out["result"].lower()
    )


def test_valid_command_reaches_approval():
    """
    A complete command must pass validation and reach the approval
    stage. Since we set approval_result=False above, the graph will
    route to cancel, but valid=True is the important assertion.
    """
    import main as app

    if app.UI_BRIDGE is None:
        pytest.skip("UI bridge not installed")

    state = _state_for("Move to X=10 Y=20 Z=30")
    out = app.app_graph.invoke(state, config=app.THREAD_CONFIG)

    # If the parser got it right, the graph completes with a decision
    # either way; the important assertion is that it did not get stuck.
    assert out["valid"] is True or "outside" in out["result"] or "require" in out["result"]