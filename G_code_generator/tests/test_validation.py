"""Table-driven tests for validate_command. Each row is one rule."""

import pytest

import main


@pytest.mark.parametrize("kwargs,expected_valid,msg_part", [
    # ---------- empty / unsupported ----------
    ({"actions": []}, False, "No supported action"),
    ({"actions": ["DWELL"]}, False, "Unsupported action"),
    ({"actions": ["MOVE", "MOVE"], "x": 10, "y": 10, "z": 10},
     False, "Repeated actions"),
    ({"actions": ["SPINDLE_ON", "SPINDLE_OFF"]},
     False, "Cannot start and stop"),

    # ---------- single-move rule ----------
    ({"actions": ["MOVE", "FEED_MOVE"],
      "x": 20, "y": 20, "z": 5, "feed_rate": 200},
     False, "Only one movement action"),

    # ---------- MOVE coordinate checks ----------
    ({"actions": ["MOVE"], "x": 10, "y": 10, "z": None},
     False, "X, Y and Z"),
    ({"actions": ["MOVE"], "x": -1, "y": 10, "z": 10},
     False, "X=-1 is outside"),
    ({"actions": ["MOVE"], "x": 10, "y": 200, "z": 10},
     False, "Y=200 is outside"),
    ({"actions": ["MOVE"], "x": 10, "y": 10, "z": 150},
     False, "Z=150 is outside"),
    ({"actions": ["MOVE"], "x": 0, "y": 0, "z": 0},
     True, "passed validation"),
    ({"actions": ["MOVE"], "x": 100, "y": 100, "z": 100},
     True, "passed validation"),

    # ---------- FEED_MOVE feed-rate checks ----------
    ({"actions": ["FEED_MOVE"], "x": 10, "y": 10, "z": 5, "feed_rate": 200},
     True, "passed validation"),
    ({"actions": ["FEED_MOVE"], "x": 10, "y": 10, "z": 5, "feed_rate": None},
     False, "FEED_MOVE requires a feed rate"),
    ({"actions": ["FEED_MOVE"], "x": 10, "y": 10, "z": 5, "feed_rate": 5},
     False, "Feed rate 5 mm/min is outside"),
    ({"actions": ["FEED_MOVE"], "x": 10, "y": 10, "z": 5, "feed_rate": 99999},
     False, "Feed rate 99999 mm/min is outside"),

    # ---------- SPINDLE_ON checks ----------
    ({"actions": ["SPINDLE_ON"], "spindle_speed": 1500, "spindle_direction": None},
     False, "clockwise or counterclockwise"),
    ({"actions": ["SPINDLE_ON"], "spindle_speed": 500, "spindle_direction": "CW"},
     False, "Spindle speed 500 RPM is outside"),
    ({"actions": ["SPINDLE_ON"], "spindle_speed": 20000, "spindle_direction": "CW"},
     False, "Spindle speed 20000 RPM is outside"),
    ({"actions": ["SPINDLE_ON"], "spindle_speed": 1000, "spindle_direction": "CW"},
     False, "Spindle speed 1000 RPM is outside"),   # strictly > 1000
    ({"actions": ["SPINDLE_ON"], "spindle_speed": 1001, "spindle_direction": "CW"},
     True, "passed validation"),
    ({"actions": ["SPINDLE_ON"], "spindle_speed": 10000, "spindle_direction": "CCW"},
     True, "passed validation"),

    # ---------- combined valid ----------
    ({"actions": ["SPINDLE_ON", "FEED_MOVE"],
      "x": 10, "y": 20, "z": 5,
      "spindle_speed": 1500, "spindle_direction": "CW",
      "feed_rate": 200},
     True, "passed validation"),
])
def test_validation_table(base_state, kwargs, expected_valid, msg_part):
    base_state.update(kwargs)
    result = main.validate_command(base_state)
    assert result["valid"] is expected_valid
    assert msg_part in result["validation_message"]