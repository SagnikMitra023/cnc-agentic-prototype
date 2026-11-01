"""
Generate the architecture diagram for the technical document.

Produces figure_1_architecture.jpg in the project root.

Requires: matplotlib (already installed for the app).

Usage:
    python tools/generate_diagram.py
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")   # non-interactive backend; no window needed
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch


ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "figure_1_architecture.jpg"


# ---------- Colours ----------
C_LLM     = "#D9EAD3"   # green  — LLM-driven nodes
C_PYTHON  = "#FFF2CC"   # yellow — deterministic Python nodes
C_GATE    = "#FCE5CD"   # orange — approval gate
C_REJECT  = "#F4CCCC"   # red    — terminal rejection nodes
C_EXEC    = "#D9EAD3"   # green  — execution (same as LLM, terminal)
C_BRIDGE  = "#DDEBF7"   # blue   — UI bridge / boundary boxes
C_CONTAINER = "#F5F5F5" # near-white — LangGraph container fill
C_EDGE    = "#333333"
C_TEXT    = "#000000"


def _box(ax, x, y, w, h, text, fill, fontsize=11, bold=False):
    """Draw a rounded box with centred text."""
    patch = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.02,rounding_size=0.15",
        linewidth=1.2, edgecolor=C_EDGE, facecolor=fill,
        zorder=2,
    )
    ax.add_patch(patch)
    ax.text(
        x + w / 2, y + h / 2, text,
        ha="center", va="center",
        fontsize=fontsize, color=C_TEXT,
        fontweight="bold" if bold else "normal",
        zorder=3,
    )


def _arrow(ax, x1, y1, x2, y2, label=None, style="-|>", dashed=False,
           label_offset=(0, 0), label_fontsize=9):
    """Draw an arrow between two points with optional label."""
    arrow = FancyArrowPatch(
        (x1, y1), (x2, y2),
        arrowstyle=style,
        mutation_scale=16,
        linewidth=1.2,
        color=C_EDGE,
        linestyle="--" if dashed else "-",
        zorder=1,
    )
    ax.add_patch(arrow)
    if label:
        mx = (x1 + x2) / 2 + label_offset[0]
        my = (y1 + y2) / 2 + label_offset[1]
        ax.text(
            mx, my, label,
            ha="center", va="center",
            fontsize=label_fontsize, color=C_EDGE,
            bbox=dict(boxstyle="round,pad=0.2",
                      facecolor="white", edgecolor="none", alpha=0.85),
            zorder=4,
        )


def build_diagram():
    fig, ax = plt.subplots(figsize=(16, 10), dpi=160)
    ax.set_xlim(0, 16)
    ax.set_ylim(0, 10)
    ax.axis("off")

    # ================================================================
    # Top: Operator (Tk UI)
    # ================================================================
    _box(ax, 6.5, 9.0, 3.0, 0.7, "Operator (Tk UI)", C_BRIDGE,
         fontsize=13, bold=True)
    ax.text(10.0, 9.35, "Tk main loop\n(50 ms poller)", fontsize=9,
            color="#666666", ha="left", va="center", style="italic")

    # ================================================================
    # Middle: LangGraph container
    # ================================================================
    container = FancyBboxPatch(
        (0.4, 3.2), 15.2, 5.2,
        boxstyle="round,pad=0.05,rounding_size=0.2",
        linewidth=1.5, edgecolor="#2E5395", facecolor=C_CONTAINER,
        zorder=0,
    )
    ax.add_patch(container)
    ax.text(0.6, 8.15,
            'LangGraph State Machine  —  thread_id = "cnc_operator_1"',
            fontsize=11, color="#2E5395", fontweight="bold",
            ha="left", va="center", zorder=1)
    ax.text(0.6, 3.55, "worker thread", fontsize=9,
            color="#666666", ha="left", va="center", style="italic")

    # ================================================================
    # Row of nodes inside the container
    # Layout (left to right): interpret, verify, validate, generate_gcode
    # ================================================================
    node_w, node_h = 2.0, 0.85
    y_row = 6.0

    # interpret
    _box(ax, 1.0, y_row, node_w, node_h,
         "interpret\n(LLM)", C_LLM, fontsize=11, bold=True)
    # verify
    _box(ax, 3.6, y_row, node_w, node_h,
         "verify\n(guard)", C_PYTHON, fontsize=11, bold=True)
    # validate
    _box(ax, 6.2, y_row, node_w, node_h,
         "validate\n(rules)", C_PYTHON, fontsize=11, bold=True)
    # generate_gcode
    _box(ax, 8.8, y_row, node_w, node_h,
         "generate_gcode", C_PYTHON, fontsize=11, bold=True)
    # human_approval
    _box(ax, 11.4, y_row, node_w, node_h,
         "human_approval", C_GATE, fontsize=11, bold=True)

    # ================================================================
    # Bottom row: reject, cancel, execute
    # ================================================================
    y_bottom = 4.2
    # reject (under validate, terminal)
    _box(ax, 6.2, y_bottom, node_w, node_h,
         "reject", C_REJECT, fontsize=11, bold=True)
    # execute (right of human_approval)
    _box(ax, 13.8, y_row + 0.0, 1.6, node_h,
         "execute", C_EXEC, fontsize=11, bold=True)
    # cancel (below execute)
    _box(ax, 13.8, y_bottom, 1.6, node_h,
         "cancel", C_REJECT, fontsize=11, bold=True)

    # ================================================================
    # Bottom: UIEventBridge
    # ================================================================
    _box(ax, 5.0, 1.8, 6.0, 0.8,
         "UIEventBridge   —   queue  +  threading.Event",
         C_BRIDGE, fontsize=12, bold=True)

    # ================================================================
    # Arrows — main pipeline
    # ================================================================
    # Operator → interpret
    _arrow(ax, 8.0, 9.0, 2.0, 6.85)

    # interpret → verify
    _arrow(ax, 3.0, y_row + node_h / 2, 3.6, y_row + node_h / 2)

    # verify → validate
    _arrow(ax, 5.6, y_row + node_h / 2, 6.2, y_row + node_h / 2)

    # validate → generate_gcode (valid)
    _arrow(ax, 8.2, y_row + node_h / 2, 8.8, y_row + node_h / 2,
           label="valid", label_offset=(0, 0.2))

    # generate_gcode → human_approval
    _arrow(ax, 10.8, y_row + node_h / 2, 11.4, y_row + node_h / 2)

    # human_approval → execute (approved)
    _arrow(ax, 13.4, y_row + node_h / 2, 13.8, y_row + node_h / 2,
           label="approved", label_offset=(0, 0.2))

    # human_approval → cancel (rejected)
    _arrow(ax, 12.4, y_row, 13.9, y_bottom + node_h,
           label="rejected", label_offset=(0.5, 0.0))

    # validate → reject (invalid)
    _arrow(ax, 7.2, y_row, 7.2, y_bottom + node_h,
           label="invalid", label_offset=(0.4, 0.0))

    # ================================================================
    # Bridge connections (dashed)
    # ================================================================
    # human_approval → bridge (needs_approval)
    _arrow(ax, 12.4, y_row, 9.5, 2.6,
           label="needs_approval", dashed=True,
           label_offset=(0.6, 0.15))

    # execute → bridge (gcode)
    _arrow(ax, 14.6, y_row, 11.0, 2.6,
           label="gcode", dashed=True,
           label_offset=(0.2, 0.25))

    # bridge → Operator (approval result, back to top)
    _arrow(ax, 5.0, 2.2, 7.5, 9.0,
           label="approval result", dashed=True,
           label_offset=(-1.5, 0.0))

    # ================================================================
    # Title
    # ================================================================
    ax.text(8.0, 0.6,
            "Figure 1 — Agentic pipeline architecture",
            ha="center", va="center", fontsize=12, style="italic",
            color="#444444")

    plt.tight_layout()
    fig.savefig(OUTPUT, format="jpg", dpi=200,
                bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"Saved: {OUTPUT}")


if __name__ == "__main__":
    build_diagram()