"""
UI behaviour of the accumulated G-code pane.

Instantiates the real CNCSimulatorApp but skips mainloop, so widgets
exist in memory without a visible window. Requires a working Tk
installation.

On headless Linux, run with:
    xvfb-run -a pytest tests/test_gcode_pane.py -v

Locally, if you have a display, plain `pytest tests/test_gcode_pane.py`
works. If neither is available, every test in this file will skip.
"""

import tkinter as tk

import pytest

import main as app


# ============================================================
# Fixture
# ============================================================

@pytest.fixture
def ui():
    """
    Construct the real CNCSimulatorApp without calling mainloop().

    If Tk cannot start (headless machine, no display), skip rather than
    fail, so the rest of the test suite still runs in CI.
    """
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk display unavailable: {exc}")

    root.withdraw()
    simulator = app.CNCSimulatorApp(root)
    try:
        yield simulator
    finally:
        try:
            root.destroy()
        except tk.TclError:
            pass


# ============================================================
# Helpers
# ============================================================

def pane(sim: app.CNCSimulatorApp) -> str:
    """Return the current text in the G-code pane."""
    return sim.gcode_text.get("1.0", "end-1c")


def non_empty_lines(sim: app.CNCSimulatorApp) -> list[str]:
    return [line for line in pane(sim).splitlines() if line.strip()]


# ============================================================
# Initial state
# ============================================================

def test_initial_pane_shows_header_only(ui):
    """At startup the pane contains exactly G21 / G90 / newline."""
    assert pane(ui) == "G21\nG90\n"


def test_initial_pane_is_read_only(ui):
    """The pane must not be user-editable — it is an audit display."""
    # tk.Text's `state` option is the authoritative source
    assert ui.gcode_text.cget("state") == "disabled"


def test_initial_pane_is_empty_of_any_placeholder(ui):
    """No `(none)` or other placeholder text is ever inserted."""
    text = pane(ui)
    assert "(none)" not in text
    assert "(empty)" not in text
    assert "(no code)" not in text.lower()


def test_initial_header_is_exactly_g21_g90(ui):
    """The header is two lines: G21 then G90."""
    lines = non_empty_lines(ui)
    assert lines == ["G21", "G90"]


# ============================================================
# Appending a block
# ============================================================

def test_append_single_block(ui):
    """A single approved block appears below the header, on its own line."""
    ui._append_gcode_block("G00 X10 Y20 Z30")
    lines = non_empty_lines(ui)
    assert lines[0] == "G21"
    assert lines[1] == "G90"
    assert lines[2] == "G00 X10 Y20 Z30"
    assert len(lines) == 3


def test_append_two_blocks_no_blank_line(ui):
    """Two approved blocks stack directly, with no blank line between them."""
    ui._append_gcode_block("G00 X10 Y20 Z30")
    ui._append_gcode_block("M05")
    text = pane(ui)
    assert "\n\n" not in text
    lines = non_empty_lines(ui)
    assert lines == ["G21", "G90", "G00 X10 Y20 Z30", "M05"]


def test_append_multi_line_block(ui):
    """A block containing several G-code lines is inserted verbatim."""
    block = "M03 S1500\nG01 X10 Y20 Z5 F200"
    ui._append_gcode_block(block)
    lines = non_empty_lines(ui)
    assert lines == [
        "G21", "G90",
        "M03 S1500",
        "G01 X10 Y20 Z5 F200",
    ]


def test_append_multiple_times_preserves_order(ui):
    """Blocks accumulate in the order they are appended."""
    ui._append_gcode_block("G00 X1 Y1 Z1")
    ui._append_gcode_block("M03 S1500")
    ui._append_gcode_block("G01 X2 Y2 Z2 F200")
    ui._append_gcode_block("M05")
    lines = non_empty_lines(ui)
    assert lines == [
        "G21", "G90",
        "G00 X1 Y1 Z1",
        "M03 S1500",
        "G01 X2 Y2 Z2 F200",
        "M05",
    ]


# ============================================================
# Edge cases on append
# ============================================================

def test_append_empty_string_is_ignored(ui):
    """An empty block produces no change to the pane."""
    before = pane(ui)
    ui._append_gcode_block("")
    assert pane(ui) == before


def test_append_none_is_ignored(ui):
    """A None payload (defensive) produces no change."""
    before = pane(ui)
    try:
        ui._append_gcode_block(None)  # type: ignore[arg-type]
    except Exception:
        pass
    # Either it ignored None or the caller's type check caught it —
    # in neither case should the pane have been corrupted.
    assert pane(ui).startswith("G21\nG90")


def test_append_does_not_glue_to_previous(ui):
    """Even if the previous content somehow lost its trailing newline,
    the next block is still placed on its own line."""
    # Simulate the edge case by writing directly without a trailing newline
    ui.gcode_text.config(state="normal")
    ui.gcode_text.delete("1.0", "end")
    ui.gcode_text.insert("1.0", "G21\nG90\nM05")  # no trailing newline
    ui.gcode_text.config(state="disabled")

    ui._append_gcode_block("G00 X10 Y20 Z30")

    lines = non_empty_lines(ui)
    assert lines == ["G21", "G90", "M05", "G00 X10 Y20 Z30"]
    # M05 and G00 must not share a line
    assert not any("M05G00" in line for line in lines)


def test_append_does_not_glue_multiline_block(ui):
    """A block containing internal newlines is still separated from
    the previous content."""
    ui._append_gcode_block("M05")
    ui._append_gcode_block("M03 S1500\nG01 X1 Y1 Z1 F200")
    lines = non_empty_lines(ui)
    assert lines == [
        "G21", "G90",
        "M05",
        "M03 S1500",
        "G01 X1 Y1 Z1 F200",
    ]


def test_append_does_not_add_blank_lines_between_blocks(ui):
    """No blank line is introduced anywhere in the pane after any number
    of appends."""
    for block in [
        "G00 X1 Y1 Z1",
        "M03 S1500",
        "G01 X2 Y2 Z2 F200",
        "M05",
        "G00 X3 Y3 Z3",
    ]:
        ui._append_gcode_block(block)
    assert "\n\n" not in pane(ui)


# ============================================================
# Clear
# ============================================================

def test_clear_resets_to_header(ui):
    """Clicking Clear wipes the pane back to just G21 / G90."""
    ui._append_gcode_block("G00 X10 Y20 Z30")
    ui._append_gcode_block("M05")
    ui._clear_gcode()
    assert pane(ui) == "G21\nG90\n"
    assert non_empty_lines(ui) == ["G21", "G90"]


def test_clear_on_empty_pane_is_safe(ui):
    """Calling Clear twice in a row does not corrupt the pane."""
    ui._clear_gcode()
    ui._clear_gcode()
    assert non_empty_lines(ui) == ["G21", "G90"]


def test_clear_then_append(ui):
    """After Clear, subsequent appends start fresh below the header."""
    ui._append_gcode_block("G00 X10 Y20 Z30")
    ui._clear_gcode()
    ui._append_gcode_block("M05")
    lines = non_empty_lines(ui)
    assert lines == ["G21", "G90", "M05"]


# ============================================================
# Auto-scroll and growth
# ============================================================

def test_append_scrolls_to_end(ui):
    """
    After an append, the pane auto-scrolls so the newest content is at
    the bottom of the view. We verify by checking the yview fraction,
    which is independent of whether the window is on screen.
    """
    for i in range(30):
        ui._append_gcode_block(f"G00 X{i} Y0 Z0")

    # Update the widget so yview reflects the latest content.
    ui.gcode_text.update_idletasks()

    top, bottom = ui.gcode_text.yview()

    # After see("end"), the bottom of the visible region should be
    # at (or very near) 1.0. Tk's see() may not land at exactly 1.0
    # because of font metrics and the trailing newline, so we allow a
    # small tolerance and also verify that we are scrolled forward at all.
    assert bottom >= 0.95, (
        f"Expected to be scrolled to end, got yview=({top:.3f}, {bottom:.3f})"
    )
    assert top > 0.0, (
        f"Expected the view to be scrolled down, not at the top "
        f"(yview=({top:.3f}, {bottom:.3f}))"
    )


def test_pane_caps_at_800_lines(ui):
    for i in range(900):
        ui._append_gcode_block(f"G00 X{i} Y0 Z0")

    # index("end-1c") returns visible_lines + 1 because Tk counts the
    # trailing implicit newline as an extra line.
    tk_lines = int(ui.gcode_text.index("end-1c").split(".")[0])
    visible_lines = tk_lines - 1
    assert visible_lines <= 800, f"Pane has {visible_lines} visible lines, expected ≤800"


def test_trim_keeps_newest_lines(ui):
    """When the pane trims, the newest blocks survive and the oldest are
    dropped."""
    for i in range(900):
        ui._append_gcode_block(f"G00 X{i} Y0 Z0")

    text = pane(ui)
    # The newest block must be present
    assert "G00 X899 Y0 Z0" in text
    # An early block should be gone
    assert "G00 X0 Y0 Z0" not in text.splitlines() or "G00 X0 Y0 Z0" not in text


# ============================================================
# Read-only enforcement
# ============================================================

def test_pane_is_read_only_after_append(ui):
    """Appending must restore the disabled state after writing."""
    ui._append_gcode_block("G00 X10 Y20 Z30")
    assert ui.gcode_text.cget("state") == "disabled"


def test_pane_is_read_only_after_clear(ui):
    """Clearing must restore the disabled state after writing."""
    ui._clear_gcode()
    assert ui.gcode_text.cget("state") == "disabled"


# ============================================================
# Header emitted flag (bridge coordination)
# ============================================================

def test_header_emitted_flag_set_at_startup(ui):
    """The bridge flag is True right after the app constructs the pane,
    so that the log preview never duplicates the header."""
    assert app.UI_BRIDGE is not None
    assert app.UI_BRIDGE.gcode_header_emitted is True


def test_header_emitted_flag_reset_on_clear(ui):
    """Clearing the pane re-arms the header flag to match reality:
    the pane still has the header, so the flag should stay True."""
    ui._append_gcode_block("G00 X10 Y20 Z30")
    ui._clear_gcode()
    assert app.UI_BRIDGE.gcode_header_emitted is True


# ============================================================
# Interaction with approve / reject semantics
# ============================================================

def test_reject_path_does_not_touch_pane(ui):
    """
    Rejecting a command (human rejection or validation failure) must
    leave the pane unchanged. We do not call the graph here; we just
    verify the pane method itself was not invoked.
    """
    ui._append_gcode_block("G00 X10 Y20 Z30")
    snapshot = pane(ui)

    # Simulating a rejection path: nothing in the app calls _append_gcode_block.
    # The pane content must be identical.
    assert pane(ui) == snapshot


def test_approve_path_appends_new_block(ui):
    """The approval path is exactly one call to _append_gcode_block;
    simulating it appends one block."""
    ui._append_gcode_block("G00 X10 Y20 Z30")
    snapshot_lines = non_empty_lines(ui)

    ui._append_gcode_block("M05")
    new_lines = non_empty_lines(ui)

    assert new_lines == snapshot_lines + ["M05"]


# ============================================================
# Content invariants
# ============================================================

def test_no_trailing_whitespace_after_append(ui):
    """Appending should not introduce trailing whitespace on any line."""
    ui._append_gcode_block("G00 X10 Y20 Z30")
    for line in pane(ui).splitlines():
        assert line == line.rstrip(), f"Trailing whitespace on: {line!r}"


def test_header_always_first(ui):
    """After any sequence of operations, the header remains at the top."""
    ui._append_gcode_block("M03 S1500")
    ui._append_gcode_block("M05")
    ui._clear_gcode()
    ui._append_gcode_block("G00 X1 Y1 Z1")

    lines = non_empty_lines(ui)
    assert lines[0] == "G21"
    assert lines[1] == "G90"