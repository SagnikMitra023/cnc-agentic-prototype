"""Pure-function tests for G-code generation. Exact string comparisons."""

import main


def gen(state):
    return main.generate_gcode(state)["gcode"]


def test_rapid_move_only(base_state):
    base_state.update({"actions": ["MOVE"], "x": 10, "y": 20, "z": 30})
    assert gen(base_state) == "G00 X10 Y20 Z30"


def test_feed_move_only(base_state):
    base_state.update({
        "actions": ["FEED_MOVE"],
        "x": 10, "y": 20, "z": 5,
        "feed_rate": 200,
    })
    assert gen(base_state) == "G01 X10 Y20 Z5 F200"


def test_feed_move_default_rate(base_state):
    base_state.update({
        "actions": ["FEED_MOVE"],
        "x": 1, "y": 2, "z": 3,
        "feed_rate": None,
    })
    assert gen(base_state) == "G01 X1 Y2 Z3 F200"  # DEFAULT_FEED_RATE = 200


def test_spindle_on_cw(base_state):
    base_state.update({
        "actions": ["SPINDLE_ON"],
        "spindle_speed": 1500,
        "spindle_direction": "CW",
    })
    assert gen(base_state) == "M03 S1500"


def test_spindle_on_ccw(base_state):
    base_state.update({
        "actions": ["SPINDLE_ON"],
        "spindle_speed": 2500,
        "spindle_direction": "CCW",
    })
    assert gen(base_state) == "M04 S2500"


def test_spindle_on_default_speed(base_state):
    base_state.update({
        "actions": ["SPINDLE_ON"],
        "spindle_speed": None,
        "spindle_direction": "CW",
    })
    assert gen(base_state) == "M03 S1000"  # DEFAULT_SPINDLE_SPEED = 1000


def test_spindle_off(base_state):
    base_state.update({"actions": ["SPINDLE_OFF"]})
    assert gen(base_state) == "M05"


def test_mixed_spindle_then_feed(base_state):
    base_state.update({
        "actions": ["SPINDLE_ON", "FEED_MOVE"],
        "x": 10, "y": 20, "z": 5,
        "spindle_speed": 1500, "spindle_direction": "CW",
        "feed_rate": 200,
    })
    assert gen(base_state) == "M03 S1500\nG01 X10 Y20 Z5 F200"


def test_mixed_rapid_then_feed(base_state):
    base_state.update({
        "actions": ["FEED_MOVE"],
        "x": 50, "y": 50, "z": 5,
        "feed_rate": 300,
    })
    assert gen(base_state) == "G01 X50 Y50 Z5 F300"


def test_number_formatting_strips_trailing_zeros(base_state):
    base_state.update({
        "actions": ["MOVE"],
        "x": 10.0, "y": 10.5, "z": 10.2500,
    })
    assert gen(base_state) == "G00 X10 Y10.5 Z10.25"


def test_invalid_state_yields_empty_gcode(base_state):
    base_state.update({"valid": False, "actions": ["MOVE"]})
    assert gen(base_state) == ""