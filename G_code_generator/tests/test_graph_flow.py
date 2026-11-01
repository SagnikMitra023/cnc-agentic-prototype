"""
End-to-end tests for the compiled LangGraph.

The LLM and the approval bridge are mocked (see conftest.py) so the
graph runs deterministically. Four terminal paths are covered:
  - execute (valid + approved)
  - cancel (valid + rejected)
  - reject  (validation failure — human approval never reached)
  - reject  (empty actions — nothing to approve)
"""

import pytest

import main as app
from tests.conftest import FakeResponse, empty_state


# ---------------------------------------------------------------
# Path 1: valid + approved → execute
# ---------------------------------------------------------------
def test_valid_approved_executes(install_mocks):
    install_mocks(
        parsed=FakeResponse(
            actions=["FEED_MOVE"],
            x=10, y=20, z=5, feed_rate=200,
        ),
        approved=True,
    )
    state = empty_state()
    state["user_command"] = "Cut to X=10 Y=20 Z=5 at F=200"

    out = app.app_graph.invoke(state, config=app.THREAD_CONFIG)
    assert out["valid"] is True
    assert out["approved"] is True
    assert out["machine_x"] == 10
    assert out["machine_y"] == 20
    assert out["machine_z"] == 5
    assert out["machine_feed_rate"] == 200
    assert out["gcode"] == "G01 X10 Y20 Z5 F200"
    assert "Feed move" in out["result"]


# ---------------------------------------------------------------
# Path 2: valid + human-rejected → cancel
# ---------------------------------------------------------------
def test_valid_rejected_cancels(install_mocks):
    install_mocks(
        parsed=FakeResponse(actions=["MOVE"], x=10, y=20, z=30),
        approved=False,
    )
    state = empty_state()
    state["user_command"] = "Move to X=10 Y=20 Z=30"

    out = app.app_graph.invoke(state, config=app.THREAD_CONFIG)
    assert out["valid"] is True
    assert out["approved"] is False
    assert out["machine_x"] == 0.0
    assert out["machine_y"] == 0.0
    assert out["machine_z"] == 0.0
    lower = out["result"].lower()
    assert "cancelled" in lower or "rejected" in lower


# ---------------------------------------------------------------
# Path 3: out-of-range → reject, approval never reached
# ---------------------------------------------------------------
def test_out_of_range_rejected_without_approval(install_mocks):
    fake = install_mocks(
        parsed=FakeResponse(actions=["MOVE"], x=200, y=20, z=30),
        approved=True,   # must not matter
    )
    state = empty_state()
    state["user_command"] = "Move to X=200 Y=20 Z=30"

    out = app.app_graph.invoke(state, config=app.THREAD_CONFIG)
    assert out["valid"] is False
    assert "X=200" in out["result"]
    assert not any(e[0] == "needs_approval" for e in fake.events)


# ---------------------------------------------------------------
# Path 4: empty LLM output → reject
# ---------------------------------------------------------------
def test_empty_actions_rejected(install_mocks):
    install_mocks(parsed=FakeResponse(actions=[]), approved=True)
    state = empty_state()
    state["user_command"] = "Tell me a joke"

    out = app.app_graph.invoke(state, config=app.THREAD_CONFIG)
    assert out["valid"] is False
    assert "No supported action" in out["result"]


# ---------------------------------------------------------------
# Path 5: hallucination guard fires before validate
# ---------------------------------------------------------------
def test_hallucination_guard_blocks_before_validate(install_mocks):
    """LLM returns z=0 for a command that only mentioned X and Y."""
    install_mocks(
        parsed=FakeResponse(actions=["MOVE"], x=10, y=20, z=0),
        approved=True,
    )
    state = empty_state()
    state["user_command"] = "Move to X=10 Y=20"

    out = app.app_graph.invoke(state, config=app.THREAD_CONFIG)
    assert out["valid"] is False
    assert "Z=0" in out["result"]
    # Confirms it was the guard, not validation, that rejected:
    # the validation-layer message would mention "require X, Y and Z".
    assert "did not state" in out["result"]


# ---------------------------------------------------------------
# Path 6: multi-move rejected by validate
# ---------------------------------------------------------------
def test_multiple_moves_rejected(install_mocks):
    install_mocks(
        parsed=FakeResponse(
            actions=["MOVE", "FEED_MOVE"],
            x=50, y=50, z=5, feed_rate=200,
        ),
        approved=True,
    )
    state = empty_state()
    state["user_command"] = "Move to X=10 Y=10 Z=10, then cut to X=50 Y=50 Z=5 at F=200"

    out = app.app_graph.invoke(state, config=app.THREAD_CONFIG)
    assert out["valid"] is False
    assert "Only one movement" in out["result"]


# ---------------------------------------------------------------
# Path 7: state is checkpointed under THREAD_CONFIG
# ---------------------------------------------------------------
def test_state_is_checkpointed(install_mocks):
    install_mocks(
        parsed=FakeResponse(actions=["MOVE"], x=10, y=20, z=30),
        approved=True,
    )
    state = empty_state()
    state["user_command"] = "Move to X=10 Y=20 Z=30"

    out = app.app_graph.invoke(state, config=app.THREAD_CONFIG)
    snap = app.app_graph.get_state(app.THREAD_CONFIG)
    assert snap.values["machine_x"] == out["machine_x"]
    assert snap.values["gcode"] == out["gcode"]