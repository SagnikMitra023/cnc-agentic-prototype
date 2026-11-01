from typing import Optional, Literal, TypedDict
import queue
import re
import threading
import tkinter as tk
from tkinter import ttk

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from langchain_ollama import ChatOllama
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import BaseModel, Field


# ============================================================
# 1. MACHINE CONFIGURATION
# ============================================================

XMIN, XMAX = 0, 100
YMIN, YMAX = 0, 100
ZMIN, ZMAX = 0, 100

SPINDLE_SPEED_MIN = 1000
SPINDLE_SPEED_MAX = 10000
DEFAULT_SPINDLE_SPEED = 1000

FEED_RATE_MIN = 10.0
FEED_RATE_MAX = 500.0
DEFAULT_FEED_RATE = 200.0

GCODE_PROGRAM_HEADER = "G21\nG90"


# ============================================================
# 2. MACHINE STATE
# ============================================================

class MachineState(TypedDict):
    user_command: str
    actions: list[str]
    x: Optional[float]
    y: Optional[float]
    z: Optional[float]
    spindle_speed: Optional[float]
    feed_rate: Optional[float]
    valid: bool
    validation_message: str
    approved: bool
    machine_x: float
    machine_y: float
    machine_z: float
    machine_spindle_speed: float
    machine_feed_rate: float
    spindle_on: bool
    result: str
    spindle_direction: Optional[str]
    gcode: str
    machine_spindle_direction: Optional[str]


# ============================================================
# 3. STRUCTURED LLM OUTPUT
# ============================================================

class MachineCommand(BaseModel):
    actions: list[Literal["MOVE", "FEED_MOVE", "SPINDLE_ON", "SPINDLE_OFF"]] = Field(
        default_factory=list,
        description=(
            "Every requested CNC action, in the order requested. "
            "Use an empty list if the command is unclear or unsupported."
        ),
    )
    x: Optional[float] = Field(default=None, description="Explicit X coordinate from operator.")
    y: Optional[float] = Field(default=None, description="Explicit Y coordinate from operator.")
    z: Optional[float] = Field(default=None, description="Explicit Z coordinate from operator.")
    spindle_speed: Optional[float] = Field(
        default=None, description="Explicit spindle speed from operator in RPM."
    )
    feed_rate: Optional[float] = Field(
        default=None,
        description=(
            "Explicit feed rate from operator in mm/min. "
            "Return null if not explicitly specified."
        ),
    )
    spindle_direction: Optional[Literal["CW", "CCW"]] = Field(
        default=None,
        description=(
            "Explicit spindle rotation direction: "
            "CW for clockwise, CCW for counterclockwise. "
            "Return null if not explicitly specified."
        ),
    )


# ============================================================
# 4. UI BRIDGE
# ============================================================

UI_BRIDGE: "UIEventBridge | None" = None


class UIEventBridge:
    """Thread-safe bridge between the LangGraph worker and the Tk UI."""

    def __init__(self, root: tk.Tk, event_queue: "queue.Queue"):
        self.root = root
        self.q = event_queue
        self.approval_event = threading.Event()
        self.approval_result: Optional[bool] = None
        self.gcode_header_emitted = False

    def emit(self, event_type: str, payload=None) -> None:
        self.q.put((event_type, payload))

    def wait_for_approval(self, timeout: float = 600.0) -> bool:
        self.approval_event.clear()
        self.approval_result = None
        self.emit("needs_approval", None)
        got = self.approval_event.wait(timeout=timeout)
        if not got:
            self.emit("log", "Approval timed out; command cancelled.")
            return False
        return bool(self.approval_result)

    def submit_approval(self, approved: bool) -> None:
        self.approval_result = approved
        self.approval_event.set()

    def preview_with_header(self, gcode: str) -> str:
        if not gcode:
            return gcode
        if not self.gcode_header_emitted:
            return GCODE_PROGRAM_HEADER + "\n" + gcode
        return gcode


def log(msg: str) -> None:
    if UI_BRIDGE is not None:
        UI_BRIDGE.emit("log", msg)
    else:
        print(msg)


# ============================================================
# 5. LOCAL LLM
# ============================================================

llm = ChatOllama(
    model="llama3.2:3b",
    base_url="http://127.0.0.1:11434",
    temperature=0,
    timeout=60,
)
llm = llm.with_structured_output(MachineCommand)


# ============================================================
# 6. INTERPRET OPERATOR COMMAND
# ============================================================

def interpret_command(state: MachineState):
    command = state["user_command"]

    prompt = f"""
You are a structured command parser for a VIRTUAL CNC training simulator.

Your ONLY task is to extract the operator's requested actions and
explicitly stated values into the required structured output schema.

Do not generate G-code.
Do not execute commands.
Do not validate machine limits.
Do not approve or reject commands.
Do not invent missing values.

============================================================
SUPPORTED ACTIONS
============================================================

1. MOVE
   Rapid tool movement (G00) to a specified position.

2. FEED_MOVE
   Cutting/feed move (G01) to a specified position with a feed rate.

3. SPINDLE_ON
   Start the spindle.

4. SPINDLE_OFF
   Stop the spindle.

============================================================
ACTION KEYWORD MAP
============================================================

MOVE (rapid, G00):
  "move", "go to", "position at", "rapid", "travel to",
  "jog to", "go home"
  (no feed rate keyword nearby)

FEED_MOVE (cutting, G01):
  "cut", "mill", "machine", "feed", "advance",
  "slowly move", "cut to", "machine to", "feed to"
  OR any explicit feed rate word: "F", "feed rate",
  "feedrate", "mm/min", "mm per minute"

If BOTH a move keyword and a feed rate are present, choose FEED_MOVE.
If the operator says "cut" but provides no feed rate, still choose
FEED_MOVE. Python validation will reject it for a missing feed rate;
that is the correct behaviour.

============================================================
STRICT RULE: AT MOST ONE MOVEMENT ACTION PER COMMAND
============================================================

A command may contain at most ONE movement action (MOVE or FEED_MOVE).
It may combine that single movement with spindle actions in any order.

Invalid (NEVER emit these):
- ["MOVE", "FEED_MOVE"]
- ["FEED_MOVE", "MOVE"]
- ["MOVE", "MOVE"]
- ["FEED_MOVE", "FEED_MOVE"]

If the operator requests two movements, extract ONLY the LAST one
along with any spindle actions.

============================================================
CRITICAL RULE: EXTRACT ONLY WHAT IS STATED
============================================================

Extract ONLY values that are LITERALLY present in the text.
Do NOT invent. Do NOT substitute defaults. Do NOT "help".
Return null for any value the operator did not explicitly state.
The word "null" is a valid and expected answer.

============================================================
COORDINATE EXTRACTION
============================================================

Extract X, Y, Z when explicitly provided. Formats:
  X=10, Y=20, Z=30
  X10 Y20 Z30
  move to x 10, y 20, z 30

Rules:
1. Return coordinates as numbers, not strings.
2. If a coordinate is not explicitly stated, return null for it.

============================================================
SPINDLE SPEED EXTRACTION
============================================================

The field spindle_speed is the explicitly stated speed in RPM.

Recognize: "1500 rpm", "1500 RPM", "1500 rev/min", "1.5k rpm",
"spindle speed 1500", "run at 1500".

Rules:
1. Return only the number (1500, not "1500 rpm").
2. "1.5k rpm" means 1500.
3. If no speed is stated, return null.

============================================================
FEED RATE EXTRACTION
============================================================

The field feed_rate is the explicitly stated cutting feed in mm/min.

Recognize: "F=200", "F200", "feed 200", "feed rate 200",
"200 mm/min", "200 mm per minute".

Rules:
1. Return only the number (200, not "200 mm/min").
2. If no feed rate is stated, return null.

============================================================
SPINDLE DIRECTION EXTRACTION
============================================================

Clockwise -> "CW". Counterclockwise / anticlockwise -> "CCW".
If direction is not stated, return null. Do NOT infer.

============================================================
ACTION ORDER
============================================================

Preserve the order in which actions appear in the command.

============================================================
EXAMPLES
============================================================

Example 1
Operator command:
Start the spindle clockwise at 1500 rpm
Output:
actions = ["SPINDLE_ON"]
x = null, y = null, z = null
spindle_speed = 1500
feed_rate = null
spindle_direction = "CW"

Example 2
Operator command:
Move to X=10, Y=20, Z=30
Output:
actions = ["MOVE"]
x = 10, y = 20, z = 30
spindle_speed = null
feed_rate = null
spindle_direction = null

Example 3
Operator command:
Cut to X=10 Y=20 Z=5 at a feed rate of 200 mm/min
Output:
actions = ["FEED_MOVE"]
x = 10, y = 20, z = 5
spindle_speed = null
feed_rate = 200
spindle_direction = null

Example 4
Operator command:
Start the spindle clockwise at 1500 rpm and cut to X=10 Y=20 Z=5 at F=200
Output:
actions = ["SPINDLE_ON", "FEED_MOVE"]
x = 10, y = 20, z = 5
spindle_speed = 1500
feed_rate = 200
spindle_direction = "CW"

Example 5
Operator command:
Stop the spindle
Output:
actions = ["SPINDLE_OFF"]
x = null, y = null, z = null
spindle_speed = null
feed_rate = null
spindle_direction = null

Example 6
Operator command:
Tell me a joke
Output:
actions = []
x = null, y = null, z = null
spindle_speed = null
feed_rate = null
spindle_direction = null

Example 7 — MISSING FEED RATE
Operator command:
Cut to X=10 Y=20 Z=30
Output:
actions = ["FEED_MOVE"]
x = 10, y = 20, z = 30
spindle_speed = null
feed_rate = null            <-- do not invent a feed rate
spindle_direction = null

Example 8 — MISSING SPINDLE PARAMS
Operator command:
Start the spindle
Output:
actions = ["SPINDLE_ON"]
x = null, y = null, z = null
spindle_speed = null
feed_rate = null
spindle_direction = null

Example 9 — MISSING Z
Operator command:
Move to X10 Y20
Output:
actions = ["MOVE"]
x = 10, y = 20, z = null    <-- do not invent a Z
spindle_speed = null
feed_rate = null
spindle_direction = null

============================================================
STRICTNESS RULE
============================================================

If a value is not literally present in the operator command, return
null. Returning a value not stated by the operator is a critical
error.

============================================================
FINAL INSTRUCTIONS
============================================================

Parse the operator command below using the rules and examples.

Return only the fields defined by the structured output schema:
- actions
- x
- y
- z
- spindle_speed
- feed_rate
- spindle_direction

All numeric fields must be numeric values or null.
Do not return explanatory text.
Do not substitute defaults for missing values.

Operator command:
{command}
"""

    try:
        response = llm.invoke(prompt)

        log("--- LLM INTERPRETATION ---")
        log(f"Actions: {response.actions}")
        log(f"X: {response.x}")
        log(f"Y: {response.y}")
        log(f"Z: {response.z}")
        log(f"Spindle Speed: {response.spindle_speed}")
        log(f"Feed Rate: {response.feed_rate}")
        log(f"Spindle Direction: {response.spindle_direction}")

        return {
            "actions": response.actions,
            "x": response.x,
            "y": response.y,
            "z": response.z,
            "spindle_speed": response.spindle_speed,
            "feed_rate": response.feed_rate,
            "spindle_direction": response.spindle_direction,
        }
    except Exception as e:
        log(f"LLM ERROR: {e}")
        return {
            "actions": [],
            "x": None,
            "y": None,
            "z": None,
            "spindle_speed": None,
            "feed_rate": None,
            "spindle_direction": None,
        }


# ============================================================
# 7. FIELD-AWARE HALLUCINATION GUARD
# ============================================================

_NUMBER_PATTERN = r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"


def _close(a: float, b: float, rel: float = 1e-6, abs_: float = 1e-9) -> bool:
    """Tolerant numeric equality (10 == 10.0 == 10.00)."""
    return abs(a - b) <= max(abs_, rel * max(abs(a), abs(b)))


def _extract_axis(text: str, axis: str) -> list[float]:
    """Every 'X<num>' / 'X=<num>' / 'x <num>' occurrence for the given axis."""
    pattern = re.compile(
        rf"{axis}\s*=?\s*({_NUMBER_PATTERN})",
        re.IGNORECASE,
    )
    return [float(m.group(1)) for m in pattern.finditer(text)]


def _extract_feed(text: str) -> list[float]:
    """Feed rate candidates: 'F200', 'F=200', 'feed 200', '200 mm/min'."""
    patterns = [
        re.compile(rf"\bF\s*=?\s*({_NUMBER_PATTERN})", re.IGNORECASE),
        re.compile(
            rf"\bfeed(?:\s*rate)?\s*=?\s*({_NUMBER_PATTERN})",
            re.IGNORECASE,
        ),
        re.compile(
            rf"({_NUMBER_PATTERN})\s*(?:mm\s*/\s*min|mm\s+per\s+min)",
            re.IGNORECASE,
        ),
    ]
    out = []
    for p in patterns:
        out.extend(float(m.group(1)) for m in p.finditer(text))
    return out


def _extract_speed(text: str) -> list[float]:
    """Spindle speed candidates: '1500 rpm', '1.5k rpm', 'spindle speed 1500', 'S1500'."""
    out = []

    # Multiplier form must be checked first: "1.5k rpm" -> 1500
    for m in re.finditer(
        rf"({_NUMBER_PATTERN})\s*[kK]\s*(?:rpm|rev|r\.?p\.?m\.?)",
        text,
        re.IGNORECASE,
    ):
        out.append(float(m.group(1)) * 1000.0)

    # Plain rpm forms
    plain_patterns = [
        re.compile(
            rf"({_NUMBER_PATTERN})\s*(?:rpm|r\.?p\.?m\.?|rev\s*/\s*min|revolutions?\s+per\s+minute)",
            re.IGNORECASE,
        ),
        re.compile(
            rf"\bspindle\s+speed\s*=?\s*({_NUMBER_PATTERN})",
            re.IGNORECASE,
        ),
        re.compile(rf"\bS\s*=?\s*({_NUMBER_PATTERN})", re.IGNORECASE),
    ]
    for p in plain_patterns:
        out.extend(float(m.group(1)) for m in p.finditer(text))

    return out


def verify_extraction(state: MachineState):
    """
    Field-aware guard against LLM hallucination.

    Each returned numeric value must match a value the operator stated
    for the SAME field. Two failure modes are caught:

      - False acceptance: 'Z=10' returned when only 'X=10' was stated.
      - Field mismatch:   'feed_rate=1500' returned when only spindle
                          speed was stated.

    Unit normalisation ('1.5k rpm' -> 1500, 'X=10.00' == 'X=10') prevents
    false rejections of legitimate values.
    """
    text = state["user_command"]

    x_stated = _extract_axis(text, "X")
    y_stated = _extract_axis(text, "Y")
    z_stated = _extract_axis(text, "Z")
    speed_stated = _extract_speed(text)
    feed_stated = _extract_feed(text)

    problems = []

    def check(field_name: str, returned, stated: list[float]):
        if returned is None:
            return
        try:
            v = float(returned)
        except (TypeError, ValueError):
            problems.append(f"{field_name}={returned!r} is not a number.")
            return
        if not stated:
            problems.append(
                f"{field_name}={returned} was returned, but the operator "
                f"did not state a {field_name} value in the command."
            )
            return
        if not any(_close(v, c) for c in stated):
            problems.append(
                f"{field_name}={returned} does not match any {field_name} "
                f"value stated in the command (stated: {sorted(stated)})."
            )

    check("X", state.get("x"), x_stated)
    check("Y", state.get("y"), y_stated)
    check("Z", state.get("z"), z_stated)
    check("spindle_speed", state.get("spindle_speed"), speed_stated)
    check("feed_rate", state.get("feed_rate"), feed_stated)

    if problems:
        msg = " ".join(problems)
        log("--- HALLUCINATION GUARD ---")
        log(msg)
        return {"valid": False, "validation_message": msg}

    return {}


# ============================================================
# 8. DETERMINISTIC VALIDATION
# ============================================================

def validate_command(state: MachineState):
    """
    Deterministic validation.

    If an earlier node (verify_extraction) already rejected the command,
    this function passes the rejection through instead of overwriting it.
    Otherwise it applies the six rule checks in order and returns.
    """
    # ------------------------------------------------------------
    # Pass-through: if a prior node already rejected, do not undo it.
    # ------------------------------------------------------------
    if state.get("valid") is False and state.get("validation_message"):
        return {
            "valid": False,
            "validation_message": state["validation_message"],
        }

    actions = state["actions"]
    x, y, z = state["x"], state["y"], state["z"]
    speed = state["spindle_speed"]
    feed_rate = state["feed_rate"]
    direction = state["spindle_direction"]

    def invalid(message: str):
        return {"valid": False, "validation_message": message}

    # ------------------------------------------------------------
    # 1. Actions must be non-empty
    # ------------------------------------------------------------
    if not actions:
        return invalid("No supported action was identified.")

    # ------------------------------------------------------------
    # 2. Only supported actions
    # ------------------------------------------------------------
    supported = {"MOVE", "FEED_MOVE", "SPINDLE_ON", "SPINDLE_OFF"}
    if any(a not in supported for a in actions):
        return invalid("Unsupported action detected.")

    # ------------------------------------------------------------
    # 3. No repeated actions
    # ------------------------------------------------------------
    if len(actions) != len(set(actions)):
        return invalid("Repeated actions are not supported.")

    # ------------------------------------------------------------
    # 4. Cannot start and stop the spindle in one command
    # ------------------------------------------------------------
    if "SPINDLE_ON" in actions and "SPINDLE_OFF" in actions:
        return invalid("Cannot start and stop the spindle in one command.")

    # ------------------------------------------------------------
    # 5. At most one movement action per command
    # ------------------------------------------------------------
    move_like = [a for a in actions if a in {"MOVE", "FEED_MOVE"}]
    if len(move_like) > 1:
        return invalid(
            "Only one movement action is allowed per command. "
            "Split multiple moves into separate commands."
        )

    # ------------------------------------------------------------
    # 6. MOVE / FEED_MOVE coordinate checks
    # ------------------------------------------------------------
    if move_like:
        if any(v is None for v in (x, y, z)):
            return invalid("Move commands require X, Y and Z coordinates.")
        if not (XMIN <= x <= XMAX):
            return invalid(f"X={x} is outside machine limits.")
        if not (YMIN <= y <= YMAX):
            return invalid(f"Y={y} is outside machine limits.")
        if not (ZMIN <= z <= ZMAX):
            return invalid(f"Z={z} is outside machine limits.")

    # ------------------------------------------------------------
    # 7. FEED_MOVE requires a valid feed rate
    # ------------------------------------------------------------
    if "FEED_MOVE" in actions:
        if feed_rate is None:
            return invalid("FEED_MOVE requires a feed rate.")
        if not (FEED_RATE_MIN <= feed_rate <= FEED_RATE_MAX):
            return invalid(
                f"Feed rate {feed_rate} mm/min is outside allowed limits "
                f"({FEED_RATE_MIN}–{FEED_RATE_MAX})."
            )

    # ------------------------------------------------------------
    # 8. SPINDLE_ON requires direction, and a valid speed if stated
    # ------------------------------------------------------------
    if "SPINDLE_ON" in actions:
        if direction not in {"CW", "CCW"}:
            return invalid("Specify clockwise or counterclockwise spindle direction.")
        if speed is not None:
            if not (SPINDLE_SPEED_MIN < speed <= SPINDLE_SPEED_MAX):
                return invalid(
                    f"Spindle speed {speed} RPM is outside allowed limits."
                )

    # ------------------------------------------------------------
    # All checks passed
    # ------------------------------------------------------------
    return {
        "valid": True,
        "validation_message": "All requested actions passed validation.",
    }
# ============================================================
# 9. DETERMINISTIC G-CODE GENERATION
# ============================================================

def format_gcode_number(value: float) -> str:
    return f"{value:.4f}".rstrip("0").rstrip(".")


def generate_gcode(state: MachineState):
    if not state["valid"]:
        return {"gcode": ""}

    lines = []
    for action in state["actions"]:
        if action == "MOVE":
            x = format_gcode_number(state["x"])
            y = format_gcode_number(state["y"])
            z = format_gcode_number(state["z"])
            lines.append(f"G00 X{x} Y{y} Z{z}")
        elif action == "FEED_MOVE":
            x = format_gcode_number(state["x"])
            y = format_gcode_number(state["y"])
            z = format_gcode_number(state["z"])
            rate = state["feed_rate"]
            if rate is None:
                rate = DEFAULT_FEED_RATE
            lines.append(f"G01 X{x} Y{y} Z{z} F{format_gcode_number(rate)}")
        elif action == "SPINDLE_ON":
            speed = state["spindle_speed"]
            if speed is None:
                speed = DEFAULT_SPINDLE_SPEED
            direction = state["spindle_direction"]
            if direction == "CW":
                lines.append(f"M03 S{format_gcode_number(speed)}")
            elif direction == "CCW":
                lines.append(f"M04 S{format_gcode_number(speed)}")
        elif action == "SPINDLE_OFF":
            lines.append("M05")

    return {"gcode": "\n".join(lines)}


# ============================================================
# 10. ROUTERS
# ============================================================

def validation_router(state: MachineState):
    return "approval" if state["valid"] else "reject"


def approval_router(state: MachineState):
    return "execute" if state["approved"] is True else "cancel"


# ============================================================
# 11. TERMINAL NODES
# ============================================================

def reject_command(state: MachineState):
    log("--- COMMAND REJECTED ---")
    log(f"Validation: {state['validation_message']}")
    return {
        "approved": False,
        "result": "Command rejected: " + state["validation_message"],
    }


def human_approval(state: MachineState):
    assert UI_BRIDGE is not None
    log("--- HUMAN APPROVAL REQUIRED ---")
    log(f"Validation: {state['validation_message']}")
    log(f"Requested actions (in order): {' -> '.join(state['actions'])}")
    if "MOVE" in state["actions"] or "FEED_MOVE" in state["actions"]:
        log(f"Target position: X={state['x']}, Y={state['y']}, Z={state['z']}")
    if "FEED_MOVE" in state["actions"]:
        rate = state["feed_rate"]
        if rate is None:
            rate = DEFAULT_FEED_RATE
        log(f"Feed rate: {rate} mm/min")
    if "SPINDLE_ON" in state["actions"]:
        speed = state["spindle_speed"]
        if speed is None:
            speed = DEFAULT_SPINDLE_SPEED
        log(f"Spindle will start at {speed} RPM")
    if "SPINDLE_OFF" in state["actions"]:
        log("Spindle will stop")

    if state.get("gcode"):
        log("--- G-CODE AWAITING APPROVAL ---")
        log(UI_BRIDGE.preview_with_header(state["gcode"]))

    approved = UI_BRIDGE.wait_for_approval()

    if approved:
        log("Command approved.")
        return {"approved": True, "result": "Command approved by human."}
    log("Command rejected by human.")
    return {"approved": False, "result": "Command rejected by human."}


def cancel_command(state: MachineState):
    log("--- COMMAND CANCELLED ---")
    return {"approved": False, "result": "Command cancelled by operator."}


def execute_command(state: MachineState):
    machine_x = state["machine_x"]
    machine_y = state["machine_y"]
    machine_z = state["machine_z"]
    spindle_on = state["spindle_on"]
    spindle_speed = state["machine_spindle_speed"]
    spindle_direction = state["machine_spindle_direction"]
    feed_rate = state["machine_feed_rate"]

    results = []
    for action in state["actions"]:
        if action == "MOVE":
            machine_x = state["x"]
            machine_y = state["y"]
            machine_z = state["z"]
            results.append(
                f"Rapid move to X={machine_x}, Y={machine_y}, Z={machine_z}."
            )
        elif action == "FEED_MOVE":
            machine_x = state["x"]
            machine_y = state["y"]
            machine_z = state["z"]
            feed_rate = (
                state["feed_rate"]
                if state["feed_rate"] is not None
                else DEFAULT_FEED_RATE
            )
            results.append(
                f"Feed move to X={machine_x}, Y={machine_y}, Z={machine_z} "
                f"at {feed_rate} mm/min."
            )
        elif action == "SPINDLE_ON":
            spindle_speed = (
                state["spindle_speed"]
                if state["spindle_speed"] is not None
                else DEFAULT_SPINDLE_SPEED
            )
            spindle_on = True
            spindle_direction = state["spindle_direction"]
            results.append(f"Spindle started at {spindle_speed} RPM.")
        elif action == "SPINDLE_OFF":
            spindle_on = False
            spindle_speed = 0
            spindle_direction = None
            results.append("Spindle stopped.")

    log(f"Executed actions = {state['actions']}")
    log(f"New position = X={machine_x}, Y={machine_y}, Z={machine_z}")

    if UI_BRIDGE is not None and state.get("gcode"):
        UI_BRIDGE.emit("gcode", state["gcode"])

    return {
        "machine_x": machine_x,
        "machine_y": machine_y,
        "machine_z": machine_z,
        "spindle_on": spindle_on,
        "machine_spindle_speed": spindle_speed,
        "machine_feed_rate": feed_rate,
        "machine_spindle_direction": spindle_direction,
        "result": " ".join(results) if results else "Nothing executed.",
    }


# ============================================================
# 12. BUILD LANGGRAPH
# ============================================================

def build_graph():
    g = StateGraph(MachineState)

    g.add_node("interpret", interpret_command)
    g.add_node("verify", verify_extraction)
    g.add_node("validate", validate_command)
    g.add_node("generate_gcode", generate_gcode)
    g.add_node("reject", reject_command)
    g.add_node("approval", human_approval)
    g.add_node("cancel", cancel_command)
    g.add_node("execute", execute_command)

    g.add_edge(START, "interpret")
    g.add_edge("interpret", "verify")
    g.add_edge("verify", "validate")

    g.add_conditional_edges(
        "validate",
        validation_router,
        {"approval": "generate_gcode", "reject": "reject"},
    )

    g.add_edge("generate_gcode", "approval")
    g.add_edge("reject", END)

    g.add_conditional_edges(
        "approval",
        approval_router,
        {"execute": "execute", "cancel": "cancel"},
    )

    g.add_edge("execute", END)
    g.add_edge("cancel", END)

    return g


memory = InMemorySaver()
app_graph = build_graph().compile(checkpointer=memory)

THREAD_CONFIG = {"configurable": {"thread_id": "cnc_operator_1"}}


# ============================================================
# 13. 3D VISUALIZATION HELPERS
# ============================================================

def draw_workpiece(ax):
    x0, x1 = 20, 80
    y0, y1 = 20, 80
    z0, z1 = 0, 20

    ax.plot([x0, x1, x1, x0, x0], [y0, y0, y1, y1, y0], [z0, z0, z0, z0, z0])
    ax.plot([x0, x1, x1, x0, x0], [y0, y0, y1, y1, y0], [z1, z1, z1, z1, z1])
    ax.plot([x0, x0], [y0, y0], [z0, z1])
    ax.plot([x1, x1], [y0, y0], [z0, z1])
    ax.plot([x1, x1], [y1, y1], [z0, z1])
    ax.plot([x0, x0], [y1, y1], [z0, z1])


def draw_machine(ax, machine_x, machine_y, machine_z,
                 spindle_on, spindle_speed, feed_rate,
                 status="READY"):
    ax.clear()

    ax.set_xlim(XMIN, XMAX)
    ax.set_ylim(YMIN, YMAX)
    ax.set_zlim(ZMIN, ZMAX)
    ax.set_xlabel("X Axis")
    ax.set_ylabel("Y Axis")
    ax.set_zlabel("Z Axis")
    ax.set_title("Virtual CNC Operator Training Simulator")

    draw_workpiece(ax)

    ax.scatter([machine_x], [machine_y], [machine_z], s=200)
    ax.plot([machine_x, machine_x], [machine_y, machine_y], [machine_z, 0])
    ax.text(
        machine_x, machine_y, machine_z + 5,
        f"Tool\nX={machine_x:.1f}\nY={machine_y:.1f}\nZ={machine_z:.1f}",
    )

    spindle_status = "ON" if spindle_on else "OFF"
    ax.text2D(0.02, 0.95, f"STATUS: {status}", transform=ax.transAxes)
    ax.text2D(
        0.02, 0.91,
        f"Tool Position: X={machine_x:.1f}  Y={machine_y:.1f}  Z={machine_z:.1f}",
        transform=ax.transAxes,
    )
    ax.text2D(
        0.02, 0.87,
        f"Spindle: {spindle_status} ({spindle_speed:.0f} RPM)",
        transform=ax.transAxes,
    )
    ax.text2D(
        0.02, 0.83,
        f"Feed Rate: {feed_rate:.0f} mm/min",
        transform=ax.transAxes,
    )

    ax.view_init(elev=25, azim=-60)


# ============================================================
# 14. WORKER
# ============================================================

def run_one_command(user_command: str, machine: dict) -> None:
    assert UI_BRIDGE is not None

    state: MachineState = {
        "user_command": user_command,
        "actions": [],
        "x": None,
        "y": None,
        "z": None,
        "spindle_speed": None,
        "feed_rate": None,
        "valid": False,
        "validation_message": "",
        "approved": False,
        "machine_x": machine["x"],
        "machine_y": machine["y"],
        "machine_z": machine["z"],
        "machine_spindle_speed": machine["spindle_speed"],
        "machine_feed_rate": machine["feed_rate"],
        "spindle_on": machine["spindle_on"],
        "spindle_direction": None,
        "gcode": "",
        "machine_spindle_direction": machine["spindle_direction"],
        "result": "",
    }

    try:
        final_state = app_graph.invoke(state, config=THREAD_CONFIG)
        UI_BRIDGE.emit("graph_done", final_state)
    except Exception as e:
        UI_BRIDGE.emit("error", str(e))


# ============================================================
# 15. TK APPLICATION
# ============================================================

class CNCSimulatorApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Virtual CNC Operator Training Simulator")
        self.root.geometry("1320x780")

        self.event_queue: "queue.Queue" = queue.Queue()
        self.worker: Optional[threading.Thread] = None

        self.machine = {
            "x": 0.0,
            "y": 0.0,
            "z": 0.0,
            "spindle_on": False,
            "spindle_speed": 0.0,
            "spindle_direction": None,
            "feed_rate": DEFAULT_FEED_RATE,
            "status": "READY",
        }

        self._build_ui()
        self._install_bridge()
        self._redraw()
        self._poll_events()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        main = ttk.Frame(self.root, padding=8)
        main.pack(fill="both", expand=True)

        left = ttk.Frame(main)
        left.pack(side="left", fill="both", expand=True)

        self.fig = Figure(figsize=(8, 7))
        self.ax = self.fig.add_subplot(111, projection="3d")
        self.canvas = FigureCanvasTkAgg(self.fig, master=left)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

        right = ttk.Frame(main, width=460)
        right.pack(side="right", fill="y", padx=(8, 0))
        right.pack_propagate(False)

        ttk.Label(right, text="Operator command:").pack(anchor="w")
        self.cmd_entry = ttk.Entry(right, width=46)
        self.cmd_entry.pack(fill="x", pady=(0, 6))
        self.cmd_entry.bind("<Return>", lambda e: self.on_submit())

        self.submit_btn = ttk.Button(right, text="Submit", command=self.on_submit)
        self.submit_btn.pack(fill="x")

        self.approval_frame = ttk.LabelFrame(right, text="Approval Required")
        self.approve_btn = ttk.Button(
            self.approval_frame, text="Approve (y)",
            command=lambda: self._respond_approval(True),
        )
        self.reject_btn = ttk.Button(
            self.approval_frame, text="Reject (n)",
            command=lambda: self._respond_approval(False),
        )
        self.approve_btn.pack(side="left", expand=True, fill="x", padx=2, pady=4)
        self.reject_btn.pack(side="left", expand=True, fill="x", padx=2, pady=4)

        gcode_header = ttk.Frame(right)
        gcode_header.pack(fill="x", pady=(10, 0))
        ttk.Label(gcode_header, text="Approved G-code:",
                  font=("TkDefaultFont", 10, "bold")).pack(side="left")
        ttk.Button(gcode_header, text="Clear", width=6,
                   command=self._clear_gcode).pack(side="right")

        gcode_frame = ttk.Frame(right)
        gcode_frame.pack(fill="both", expand=True, pady=(4, 0))

        self.gcode_text = tk.Text(
            gcode_frame,
            height=14,
            width=46,
            wrap="none",
            font=("Courier", 11),
            bg="#1e1e1e", fg="#d4d4d4",
            insertbackground="white",
        )
        gscroll = ttk.Scrollbar(gcode_frame, orient="vertical",
                                command=self.gcode_text.yview)
        self.gcode_text.configure(yscrollcommand=gscroll.set)
        self.gcode_text.pack(side="left", fill="both", expand=True)
        gscroll.pack(side="right", fill="y")

        ghscroll = ttk.Scrollbar(right, orient="horizontal",
                                 command=self.gcode_text.xview)
        self.gcode_text.configure(xscrollcommand=ghscroll.set)
        ghscroll.pack(fill="x")

        self._init_gcode_pane()

        ttk.Label(right, text="Log:").pack(anchor="w", pady=(10, 0))
        log_frame = ttk.Frame(right)
        log_frame.pack(fill="both", expand=True)
        self.log_text = tk.Text(log_frame, height=12, state="disabled", wrap="word")
        lscroll = ttk.Scrollbar(log_frame, orient="vertical",
                                command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=lscroll.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        lscroll.pack(side="right", fill="y")

    def _install_bridge(self):
        global UI_BRIDGE
        UI_BRIDGE = UIEventBridge(self.root, self.event_queue)
        UI_BRIDGE.gcode_header_emitted = True

    def on_submit(self):
        cmd = self.cmd_entry.get().strip()
        if not cmd:
            return
        if self.worker is not None and self.worker.is_alive():
            self._log("Previous command still running; please wait.")
            return

        self.cmd_entry.delete(0, "end")
        self._log(f"> {cmd}")
        self._set_status("PROCESSING")
        self._hide_approval()
        self.submit_btn.config(state="disabled")

        self.worker = threading.Thread(
            target=run_one_command,
            args=(cmd, dict(self.machine)),
            daemon=True,
        )
        self.worker.start()

    def _respond_approval(self, approved: bool):
        assert UI_BRIDGE is not None
        self._hide_approval()
        self._log("Approved by operator." if approved else "Rejected by operator.")
        UI_BRIDGE.submit_approval(approved)

    def _on_close(self):
        if UI_BRIDGE is not None:
            UI_BRIDGE.submit_approval(False)
        self.root.destroy()

    def _poll_events(self):
        try:
            while True:
                evt, payload = self.event_queue.get_nowait()
                self._handle_event(evt, payload)
        except queue.Empty:
            pass
        self.root.after(50, self._poll_events)

    def _handle_event(self, evt, payload):
        if evt == "log":
            self._log(payload)
        elif evt == "gcode":
            self._append_gcode_block(payload)
        elif evt == "needs_approval":
            self._show_approval()
        elif evt == "graph_done":
            self._apply_final_state(payload)
            self.submit_btn.config(state="normal")
        elif evt == "error":
            self._log(f"ERROR: {payload}")
            self._set_status("ERROR")
            self.submit_btn.config(state="normal")
            self._hide_approval()

    def _apply_final_state(self, fs):
        self.machine.update({
            "x": fs["machine_x"],
            "y": fs["machine_y"],
            "z": fs["machine_z"],
            "spindle_on": fs["spindle_on"],
            "spindle_speed": fs["machine_spindle_speed"],
            "spindle_direction": fs.get("machine_spindle_direction"),
            "feed_rate": fs.get("machine_feed_rate", DEFAULT_FEED_RATE),
        })

        if not fs["valid"]:
            status = "REJECTED"
        elif fs["approved"]:
            status = "EXECUTED"
        else:
            status = "CANCELLED"

        self._set_status(status)
        self._log("--- RESULT ---")
        self._log(fs["result"])
        self._log(
            f"Current machine position: "
            f"X={self.machine['x']}, "
            f"Y={self.machine['y']}, "
            f"Z={self.machine['z']}"
        )
        self._log(
            f"Spindle: "
            f"{'ON' if self.machine['spindle_on'] else 'OFF'} "
            f"({self.machine['spindle_speed']} RPM)"
        )
        self._log(f"Feed Rate: {self.machine['feed_rate']} mm/min")
        self._redraw()

    def _set_status(self, status: str):
        self.machine["status"] = status
        self._redraw()

    def _redraw(self):
        draw_machine(
            self.ax,
            self.machine["x"], self.machine["y"], self.machine["z"],
            self.machine["spindle_on"], self.machine["spindle_speed"],
            self.machine["feed_rate"],
            self.machine["status"],
        )
        self.canvas.draw_idle()

    def _show_approval(self):
        self.approval_frame.pack(fill="x", pady=6, after=self.submit_btn)

    def _hide_approval(self):
        self.approval_frame.pack_forget()

    def _init_gcode_pane(self):
        self.gcode_text.config(state="normal")
        self.gcode_text.delete("1.0", "end")
        self.gcode_text.insert("1.0", GCODE_PROGRAM_HEADER + "\n")
        self.gcode_text.config(state="disabled")
        if UI_BRIDGE is not None:
            UI_BRIDGE.gcode_header_emitted = True

    def _append_gcode_block(self, gcode: str):
        if not gcode:
            return

        self.gcode_text.config(state="normal")

        current = self.gcode_text.get("1.0", "end-1c")
        if current and not current.endswith("\n"):
            self.gcode_text.insert("end", "\n")

        self.gcode_text.insert("end", gcode)

        line_count = int(self.gcode_text.index("end-1c").split(".")[0])
        if line_count > 800:
            self.gcode_text.delete("1.0", f"{line_count - 800}.0")

        self.gcode_text.see("end")
        self.gcode_text.config(state="disabled")

    def _clear_gcode(self):
        self._init_gcode_pane()

    def _log(self, msg: str):
        self.log_text.config(state="normal")
        self.log_text.insert("end", str(msg) + "\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")


# ============================================================
# 16. ENTRY POINT
# ============================================================

if __name__ == "__main__":
    root = tk.Tk()
    CNCSimulatorApp(root)
    root.mainloop()