# CNC Agentic Prototype

### Agentic AI-Based Natural Language Interface for CNC Machining and Intelligent Machine Control

## 1. Project Overview

The CNC Agentic Prototype is an intelligent manufacturing project focused on developing an AI-driven interface for interpreting natural-language machining instructions and translating them into structured machine-control commands.

The system integrates Large Language Models (LLMs), agentic workflows, deterministic command validation, and CNC control technologies to establish an intuitive yet controlled interaction between human operators and CNC machinery.

Developed using Python and LangGraph, the architecture separates probabilistic language interpretation from deterministic command validation and G-code generation. A Human-in-the-Loop (HITL) mechanism ensures that generated machining commands undergo approval before execution.

The current development focuses on LinuxCNC simulation testing, with further integration into robotic systems through ROS 2.

## 2. Project Objectives

- Develop an intelligent natural-language interface for CNC machining.
- Translate operator instructions into structured machining commands.
- Implement agentic workflows for instruction interpretation and state management.
- Ensure deterministic command validation and controlled G-code generation.
- Incorporate Human-in-the-Loop approval for machine operations.
- Evaluate generated G-code through LinuxCNC simulation.
- Explore integration with robotic systems and intelligent manufacturing environments.

## 3. System Architecture

The proposed architecture follows a modular workflow:

```text
           Operator Input
                 |
                 v
     Natural Language Interface
                 |
                 v
        LangGraph Agentic
             Workflow
                 |
                 v
      Instruction Interpretation
                 |
                 v
       Structured Command Model
                 |
                 v
       Deterministic Validation
                 |
                 v
       Human Approval Interface
                 |
                 v
         G-code Generation
                 |
                 v
          LinuxCNC Interface
                 |
                 v
        CNC Simulation Testing
```

The architecture distinguishes between LLM-based instruction interpretation and deterministic machine-control logic to improve predictability and control.

## 4. Technology Stack

| Component | Technology |
|---|---|
| Programming Language | Python 3.13 |
| Agentic Framework | LangGraph |
| Large Language Model | Ollama – Llama 3.2 (3B) |
| Data Validation | Pydantic |
| Workflow Management | LangGraph StateGraph |
| User Interface | Tkinter |
| Visualization | Matplotlib |
| CNC Control | LinuxCNC |
| Robotics Integration | ROS 2 |
| Testing | Pytest |
| Version Control | Git / GitLab / GitHub |

## 5. Current Implementation

### 5.1 Agentic Workflow

- LangGraph-based workflow for managing instruction-processing stages.
- State management for maintaining command execution context.
- LLM-based interpretation of natural-language machining instructions.
- Structured command generation.

### 5.2 Command Validation and Control

- Pydantic-based structured command representation.
- Deterministic validation of generated machine instructions.
- Configurable operating limits for X, Y and Z axes.
- Feed-rate and spindle-speed constraints.
- Human approval mechanism before command execution.
- Field-aware validation to prevent unsupported command parameters.

### 5.3 G-code Generation

The prototype generates structured G-code from validated machining instructions.

Currently supported operations include:

| Command | Function |
|---|---|
| MOVE | Linear axis movement |
| FEED_MOVE | Movement with specified feed rate |
| SPINDLE_ON | Spindle activation |
| SPINDLE_OFF | Spindle deactivation |

The current implementation focuses on basic linear movements and spindle control.

### 5.4 LinuxCNC Simulation Testing

Generated G-code is being tested within the LinuxCNC simulation environment.

The testing phase focuses on:

- G-code compatibility.
- Command execution behaviour.
- Validation of generated machine instructions.
- Evaluating the interface between the AI-based command-generation workflow and CNC control software.

Further development will focus on improving system integration and machine-state feedback.

### 5.5 ROS 2 Integration

The project is being extended towards integration with robotic systems using ROS 2.

The objective is to explore communication between the intelligent command-processing architecture and robotic control systems, enabling further development towards intelligent and interconnected manufacturing environments.

## 6. Repository Structure

```text
cnc-agentic-prototype/
│
├── G_code_generator/
├── tests/
├── tools/
│   ├── diagram.py
│   └── measure_parameter.py
│
├── figure_1_architecture.*
├── main.py
├── requirements.txt
├── .gitignore
└── README.md
```

*The repository structure is subject to change as development progresses.*

## 7. Installation and Setup

### Prerequisites

- Python 3.13
- Git
- Ollama
- LinuxCNC for simulation testing

### Clone the Repository

```bash
git clone git@github.com:YOUR_USERNAME/cnc-agentic-prototype.git
cd cnc-agentic-prototype
```

### Create a Virtual Environment

```bash
python -m venv .venv
```

**Windows (Git Bash):**

```bash
source .venv/Scripts/activate
```

**Linux:**

```bash
source .venv/bin/activate
```

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Configure Ollama

```bash
ollama pull llama3.2:3b
```

Ensure Ollama is running before starting the application.

### Run the Prototype

```bash
python main.py
```

*Execution instructions may require adjustment as the project entry point and environment configuration evolve.*

## 8. Testing

The project uses Pytest for testing individual components.

Run the test suite using:

```bash
pytest -v
```

LinuxCNC simulation testing is performed separately to evaluate generated G-code and its execution behaviour.

## 9. Development Roadmap

- [x] Initial LangGraph agentic workflow.
- [x] Natural-language instruction interpretation.
- [x] Structured command representation.
- [x] Deterministic command validation.
- [x] Human-in-the-Loop approval mechanism.
- [x] Basic G-code generation.
- [x] Initial LinuxCNC simulation testing.
- [ ] Expanded G-code operation support.
- [ ] Improved CNC integration and machine-state feedback.
- [ ] ROS 2 integration with robotic systems.
- [ ] Advanced machining process validation.
- [ ] Digital-twin-based simulation and monitoring.
- [ ] Closed-loop intelligent manufacturing control.

## 10. Future Research Directions

- Agentic AI for intelligent manufacturing.
- Context-aware machining instruction interpretation.
- AI-assisted process planning and optimization.
- Integration of CNC and robotic control systems.
- Digital twins for manufacturing process simulation.
- Intelligent machine monitoring and feedback.
- Human-machine collaboration in Industry 4.0 environments.

## 11. Safety Considerations

This project is an experimental research prototype.

Generated machine instructions undergo deterministic validation and human approval before execution. Simulation testing alone does not establish physical machine safety.

Physical deployment requires additional validation, machine-specific safety interlocks, collision checking, emergency-stop provisions, and controlled commissioning.

## 12. Project Status

**Status: Active Development**

The prototype is currently undergoing LinuxCNC simulation testing, with further development focused on robotic integration and intelligent manufacturing applications.

## 13. Author

**Sagnik Mitra**

Production Engineering | AI/ML | Robotics | Intelligent Manufacturing



---

*This repository documents an ongoing engineering and research project exploring the convergence of Agentic AI, CNC machining, robotics, and intelligent manufacturing.*
