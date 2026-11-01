"""
Golden test set for parser evaluation.

Used by tools/measure_parser.py and by tests/test_parser_prompt.py.
Each entry gives the raw operator command and the expected structured
output for every field. Missing keys in `gold` mean that field is not
part of the expected output for this case.
"""

GOLDEN_SET = [
    # ---------- straightforward positives ----------
    {
        "command": "Start the spindle clockwise at 1500 rpm",
        "gold": {
            "actions": ["SPINDLE_ON"],
            "x": None, "y": None, "z": None,
            "spindle_speed": 1500,
            "feed_rate": None,
            "spindle_direction": "CW",
        },
    },
    {
        "command": "Start the spindle counterclockwise at 2500 RPM",
        "gold": {
            "actions": ["SPINDLE_ON"],
            "x": None, "y": None, "z": None,
            "spindle_speed": 2500,
            "feed_rate": None,
            "spindle_direction": "CCW",
        },
    },
    {
        "command": "Move to X=10 Y=20 Z=30",
        "gold": {
            "actions": ["MOVE"],
            "x": 10, "y": 20, "z": 30,
            "spindle_speed": None,
            "feed_rate": None,
            "spindle_direction": None,
        },
    },
    {
        "command": "Rapid move to X10 Y20 Z30",
        "gold": {
            "actions": ["MOVE"],
            "x": 10, "y": 20, "z": 30,
            "spindle_speed": None,
            "feed_rate": None,
            "spindle_direction": None,
        },
    },
    {
        "command": "Cut to X=10 Y=20 Z=5 at F=200",
        "gold": {
            "actions": ["FEED_MOVE"],
            "x": 10, "y": 20, "z": 5,
            "spindle_speed": None,
            "feed_rate": 200,
            "spindle_direction": None,
        },
    },
    {
        "command": "Feed to X=50 Y=50 Z=0 at 300 mm/min",
        "gold": {
            "actions": ["FEED_MOVE"],
            "x": 50, "y": 50, "z": 0,
            "spindle_speed": None,
            "feed_rate": 300,
            "spindle_direction": None,
        },
    },
    {
        "command": "Stop the spindle",
        "gold": {
            "actions": ["SPINDLE_OFF"],
            "x": None, "y": None, "z": None,
            "spindle_speed": None,
            "feed_rate": None,
            "spindle_direction": None,
        },
    },

    # ---------- combined actions ----------
    {
        "command": "Start the spindle clockwise at 1500 rpm and cut to X=10 Y=20 Z=5 at F=200",
        "gold": {
            "actions": ["SPINDLE_ON", "FEED_MOVE"],
            "x": 10, "y": 20, "z": 5,
            "spindle_speed": 1500,
            "feed_rate": 200,
            "spindle_direction": "CW",
        },
    },
    {
        "command": "Move to X=10 Y=20 Z=30 and then start the spindle counterclockwise at 2000 rpm",
        "gold": {
            "actions": ["MOVE", "SPINDLE_ON"],
            "x": 10, "y": 20, "z": 30,
            "spindle_speed": 2000,
            "feed_rate": None,
            "spindle_direction": "CCW",
        },
    },
    {
        "command": "Feed to X=25 Y=25 Z=5 at F250, then stop the spindle",
        "gold": {
            "actions": ["FEED_MOVE", "SPINDLE_OFF"],
            "x": 25, "y": 25, "z": 5,
            "spindle_speed": None,
            "feed_rate": 250,
            "spindle_direction": None,
        },
    },

    # ---------- under-specified: guard / validation must reject ----------
    {
        "command": "Move to X10 Y20",
        "gold": {
            "actions": ["MOVE"],
            "x": 10, "y": 20, "z": None,   # missing Z
            "spindle_speed": None,
            "feed_rate": None,
            "spindle_direction": None,
        },
    },
    {
        "command": "Cut to X=10 Y=20 Z=30",
        "gold": {
            "actions": ["FEED_MOVE"],
            "x": 10, "y": 20, "z": 30,
            "spindle_speed": None,
            "feed_rate": None,              # missing feed
            "spindle_direction": None,
        },
    },
    {
        "command": "Start the spindle",
        "gold": {
            "actions": ["SPINDLE_ON"],
            "x": None, "y": None, "z": None,
            "spindle_speed": None,           # missing speed
            "feed_rate": None,
            "spindle_direction": None,       # missing direction
        },
    },

    # ---------- out of range (parser still extracts, validator rejects) ----------
    {
        "command": "Move to X=200 Y=20 Z=30",
        "gold": {
            "actions": ["MOVE"],
            "x": 200, "y": 20, "z": 30,
            "spindle_speed": None,
            "feed_rate": None,
            "spindle_direction": None,
        },
    },
    {
        "command": "Cut to X=10 Y=20 Z=5 at F=99999",
        "gold": {
            "actions": ["FEED_MOVE"],
            "x": 10, "y": 20, "z": 5,
            "spindle_speed": None,
            "feed_rate": 99999,
            "spindle_direction": None,
        },
    },
    {
        "command": "Start the spindle clockwise at 500 rpm",
        "gold": {
            "actions": ["SPINDLE_ON"],
            "x": None, "y": None, "z": None,
            "spindle_speed": 500,
            "feed_rate": None,
            "spindle_direction": "CW",
        },
    },

    # ---------- unsupported / adversarial ----------
    {
        "command": "Tell me a joke",
        "gold": {
            "actions": [],
            "x": None, "y": None, "z": None,
            "spindle_speed": None,
            "feed_rate": None,
            "spindle_direction": None,
        },
    },
    {
        "command": "Pause the machine",
        "gold": {
            "actions": [],
            "x": None, "y": None, "z": None,
            "spindle_speed": None,
            "feed_rate": None,
            "spindle_direction": None,
        },
    },
    {
        "command": "Move to X=10 Y=20 Z=30 and then cut to X=50 Y=50 Z=5 at F=200",
        "gold": {
            "actions": ["FEED_MOVE"],       # parser keeps only the last move
            "x": 50, "y": 50, "z": 5,
            "spindle_speed": None,
            "feed_rate": 200,
            "spindle_direction": None,
        },
    },

    # ---------- numeric formatting / multiplier ----------
    {
        "command": "Start the spindle clockwise at 1.5k rpm",
        "gold": {
            "actions": ["SPINDLE_ON"],
            "x": None, "y": None, "z": None,
            "spindle_speed": 1500,
            "feed_rate": None,
            "spindle_direction": "CW",
        },
    },
    {
        "command": "Move to X=10.00 Y=20.0 Z=30.000",
        "gold": {
            "actions": ["MOVE"],
            "x": 10.0, "y": 20.0, "z": 30.0,
            "spindle_speed": None,
            "feed_rate": None,
            "spindle_direction": None,
        },
    },
]