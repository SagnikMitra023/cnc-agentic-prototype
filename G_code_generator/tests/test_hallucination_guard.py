"""
Tests for verify_extraction. Covers the two properties the guard must
guarantee:

1. No false rejections of legitimate values (numeric formatting,
   the '1.5k' multiplier, unit normalisation).
2. No false acceptances (a value returned for a field the operator
   did not name, or a value that collides with a different field).
"""

import pytest

import main


def guard(text, **returned):
    """Run verify_extraction and return the result dict."""
    state = {
        "user_command": text,
        "x": returned.get("x"),
        "y": returned.get("y"),
        "z": returned.get("z"),
        "spindle_speed": returned.get("spindle_speed"),
        "feed_rate": returned.get("feed_rate"),
    }
    return main.verify_extraction(state)


# ---------- passes (no false rejections) ----------

@pytest.mark.parametrize("text,kwargs", [
    ("Move to X=10 Y=20 Z=30", {"x": 10, "y": 20, "z": 30}),
    ("Move to X10 Y20 Z30",     {"x": 10, "y": 20, "z": 30}),
    ("move to x 10, y 20, z 30",{"x": 10, "y": 20, "z": 30}),
    ("Move to X=10.00 Y=20.0 Z=30.000",
     {"x": 10, "y": 20, "z": 30}),      # numeric formatting
    ("Start spindle at 1500 rpm", {"spindle_speed": 1500}),
    ("spindle speed 1500",        {"spindle_speed": 1500}),
    ("start at 1.5k rpm",         {"spindle_speed": 1500}),   # multiplier
    ("Cut to X=10 Y=20 Z=5 at F=200", {"x": 10, "y": 20, "z": 5, "feed_rate": 200}),
    ("cut at 200 mm/min",          {"feed_rate": 200}),
    ("feed rate 300",              {"feed_rate": 300}),
    # Legitimate: value appears in the right field only
    ("Move to X=10 Y=20 Z=10", {"x": 10, "y": 20, "z": 10}),
])
def test_guard_passes_legitimate_values(text, kwargs):
    out = guard(text, **kwargs)
    assert out == {}, f"Unexpected rejection: {out}"


# ---------- rejections (false acceptances closed) ----------

@pytest.mark.parametrize("text,kwargs,msg_part", [
    # Z returned but never stated
    ("Move to X=10 Y=20", {"x": 10, "y": 20, "z": 0}, "Z=0"),
    ("Move to X=10 Y=20", {"x": 10, "y": 20, "z": 30}, "Z=30"),

    # Z collides with X — old guard's false acceptance
    ("Move to X=10 Y=20 Z=30",
     {"x": 10, "y": 20, "z": 10}, "Z=10"),
    ("Move to X=0 Y=10",
     {"x": 0, "y": 10, "z": 0}, "Z=0"),
    ("Move to X=15 Y=20 Z=30",
     {"x": 15, "y": 20, "z": 15}, "Z=15"),

    # Feed_rate returned but only spindle speed was stated
    ("Start spindle at 1500 rpm, cut to X=10 Y=20 Z=5",
     {"x": 10, "y": 20, "z": 5, "spindle_speed": 1500, "feed_rate": 1500},
     "feed_rate"),
    ("Start spindle at 1500 rpm, cut to X=10 Y=20 Z=5",
     {"x": 10, "y": 20, "z": 5, "spindle_speed": 1500, "feed_rate": 200},
     "feed_rate"),

    # Spindle speed returned but never stated
    ("Start spindle clockwise", {"spindle_speed": 1500}, "spindle_speed"),

    # X returned but not stated
    ("Move to Y=20 Z=30", {"x": 0, "y": 20, "z": 30}, "X=0"),
])
def test_guard_rejects_hallucinations(text, kwargs, msg_part):
    out = guard(text, **kwargs)
    assert out["valid"] is False
    assert msg_part in out["validation_message"]