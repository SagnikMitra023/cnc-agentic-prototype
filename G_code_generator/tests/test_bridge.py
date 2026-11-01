"""
Threading semantics of UIEventBridge.

The bridge needs a dummy `root` (it is only stored, never called), so a
plain object() stands in for Tk. The approval handshake is tested with
real threads to prove it does not deadlock and respects timeouts.
"""

import queue
import threading

import pytest

import main as app


class DummyRoot:
    pass


@pytest.fixture
def bridge():
    return app.UIEventBridge(DummyRoot(), queue.Queue())


def test_submit_approval_releases_waiter(bridge):
    result = {}

    def waiter():
        result["approved"] = bridge.wait_for_approval(timeout=2.0)

    t = threading.Thread(target=waiter)
    t.start()

    evt, _ = bridge.q.get(timeout=1.0)
    assert evt == "needs_approval"

    bridge.submit_approval(True)
    t.join(timeout=2.0)

    assert not t.is_alive()
    assert result["approved"] is True


def test_rejection_returns_false(bridge):
    result = {}

    def waiter():
        result["approved"] = bridge.wait_for_approval(timeout=2.0)

    t = threading.Thread(target=waiter)
    t.start()
    bridge.q.get(timeout=1.0)  # drain needs_approval
    bridge.submit_approval(False)
    t.join(timeout=2.0)

    assert result["approved"] is False


def test_timeout_returns_false(bridge):
    approved = bridge.wait_for_approval(timeout=0.1)
    assert approved is False

    evt1, _ = bridge.q.get(timeout=1.0)
    assert evt1 == "needs_approval"

    evt2, msg = bridge.q.get(timeout=1.0)
    assert evt2 == "log"
    assert "timed out" in msg.lower()

def test_preview_with_header_once(bridge):
    bridge.gcode_header_emitted = False
    first = bridge.preview_with_header("G00 X1 Y2 Z3")
    assert first.startswith("G21\nG90\n")

    bridge.gcode_header_emitted = True
    second = bridge.preview_with_header("M05")
    assert second == "M05"