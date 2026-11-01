"""Shared fixtures for the CNC simulator test suite."""
import queue
import sys
import threading
from pathlib import Path

import pytest

# Make the single-file app importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main as app  # noqa: E402


class FakeResponse:
    """Stand-in for a Pydantic MachineCommand returned by the LLM."""

    def __init__(self, **kw):
        self.actions = kw.get("actions", [])
        self.x = kw.get("x")
        self.y = kw.get("y")
        self.z = kw.get("z")
        self.spindle_speed = kw.get("spindle_speed")
        self.feed_rate = kw.get("feed_rate")
        self.spindle_direction = kw.get("spindle_direction")


class FakeBridge:
    """
    In-memory replacement for UIEventBridge.

    Records every emitted event, and resolves wait_for_approval()
    instantly with a pre-set answer. This is the only thing tests need
    to control the graph without a real Tk window.
    """

    def __init__(self, approval_result: bool = True):
        self.events = []
        self.gcode_header_emitted = False
        self.approval_result = approval_result

    def emit(self, event_type, payload=None):
        self.events.append((event_type, payload))

    def wait_for_approval(self, timeout=None):
        self.emit("needs_approval", None)
        return self.approval_result

    def submit_approval(self, approved):
        self.approval_result = approved

    def preview_with_header(self, gcode):
        return gcode


def empty_state():
    """A blank MachineState — the shape every test starts from."""
    return {
        "user_command": "",
        "actions": [],
        "x": None,
        "y": None,
        "z": None,
        "spindle_speed": None,
        "feed_rate": None,
        "valid": False,
        "validation_message": "",
        "approved": False,
        "machine_x": 0.0,
        "machine_y": 0.0,
        "machine_z": 0.0,
        "machine_spindle_speed": 0.0,
        "machine_feed_rate": 200.0,
        "spindle_on": False,
        "spindle_direction": None,
        "machine_spindle_direction": None,
        "gcode": "",
        "result": "",
    }


@pytest.fixture
def base_state():
    return {
        "user_command": "",
        "actions": [],
        "x": None, "y": None, "z": None,
        "spindle_speed": None, "feed_rate": None,
        "valid": True,                       # ← was False
        "validation_message": "",
        "approved": False,
        "machine_x": 0.0, "machine_y": 0.0, "machine_z": 0.0,
        "machine_spindle_speed": 0.0, "machine_feed_rate": 200.0,
        "spindle_on": False, "spindle_direction": None,
        "machine_spindle_direction": None,
        "gcode": "", "result": "",
    }


@pytest.fixture
def install_mocks(monkeypatch):
    """
    Install a fake LLM (returns a FakeResponse) and a fake bridge
    (returns a fixed approval answer). Returns the fake bridge so tests
    can inspect emitted events.
    """
    def _install(parsed, approved: bool = True):
        monkeypatch.setattr(
            app,
            "llm",
            type("FakeLLM", (), {"invoke": lambda self, prompt: parsed})(),
        )
        fake_bridge = FakeBridge(approval_result=approved)
        monkeypatch.setattr(app, "UI_BRIDGE", fake_bridge)
        return fake_bridge

    return _install