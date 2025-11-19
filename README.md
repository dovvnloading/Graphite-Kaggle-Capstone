# **Graphite – Kaggle Capstone Edition**

### *A Visual Multi-Agent Canvas for Orchestrated AI Workflows*

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

---

## **Overview**

This repository contains the **Capstone Edition** of **Graphite**, a visual multi-agent research environment created for the **Kaggle + Google AI Agents Intensive (Nov 2025)**.

This edition is a specialized, refactored release focused on **multi-agent orchestration**, **tool interoperability**, and **research workflow observability**, tailored specifically to demonstrate the competencies required for the Capstone.

Graphite replaces the limitations of a linear chat interface with an infinite, spatial canvas where every thought, tool call, and agent operation becomes a visual node. Complex reasoning unfolds not as a message log, but as structured, branching workflows.

This edition introduces the **Agent Orchestrator**, a system-level agent capable of planning and executing complex, multi-step workflows using specialized sub-agents and tool calls. This is the central feature developed for the Capstone.

---

## **Screenshots**

### **Orchestrator → Web Tool → Desktop Document**

*The orchestrator retrieves real-time Bitcoin pricing and auto-generates a local text artifact on the user’s desktop.*

![Orchestrator Price Workflow](https://www.googleapis.com/download/storage/v1/b/kaggle-user-content/o/inbox%2F20124535%2Fc1c748250e940e8db9c5801a53a23ae7%2FScreenshot%202025-11-16%20112132.png?generation=1763327435899819\&alt=media)

---

### **Orchestrator → Web Research → PyCoder → Markdown Report**

*The orchestrator plans a multi-step workflow, gathers grounded sources, synthesizes findings, formats them via PyCoder, and outputs a final Markdown artifact.*

![Orchestrator Markdown Workflow](https://www.googleapis.com/download/storage/v1/b/kaggle-user-content/o/inbox%2F20124535%2F9523f8f02e580ab2b5a3e0f8128333df%2FScreenshot%202025-11-16%20165305.png?generation=1763330021366808\&alt=media)

---

## **Key Capstone Features**

### **✓ Multi-Agent Architecture**

Graphite demonstrates more than the minimum three agent concepts required:

* Orchestrator agent
* Sequential and parallel sub-agents
* Loop / repair agents (PyCoder self-correction cycles)
* Memory system
* Context inheritance
* Tool invocation (web search, code execution, file operations)
* Observability and execution logging

---

### **✓ Orchestrator Agent**

A high-level operator capable of:

* interpreting the user’s natural-language goal
* creating a JSON plan
* executing steps across specialized agents
* passing data through a Memory Bank
* producing structured artifacts (reports, files, outputs)

---

### **✓ Infinite Node-Based Canvas**

A PySide6-powered visual environment:

* branch any conversation
* parallel reasoning paths
* deep context lineage
* tool agents represented as visual nodes
* embedded execution logs

---

### **✓ Persistence & Memory**

Graphite stores complete session state via SQLite:

* node content
* spatial positions
* tool results
* agent logs
* graph structure

---

## **Repository Structure**

```
graphite-capstone/
│
├── graphite_core/         # Session manager, persistence, utilities
├── graphite_agents/       # Orchestrator, PyCoder, WebNode, Reasoning agents
├── graphite_ui/           # Infinite canvas, nodes, PySide6 components
├── tools/                 # Code execution, file handlers, API provider
│
├── LICENSE                # Apache 2.0
├── README.md
└── examples/
```

---

## **About This Edition**

This is the **Capstone-focused build** of Graphite. The full internal development version continues privately, while this edition distills the system into a clean architecture aligned with the course themes of:

* planning
* tooling
* memory
* observability
* multi-agent orchestration

While fully functional, this edition is provided **strictly as an educational, open-source submission**, not as a production-ready or commercial release.

---

## **License — Apache 2.0**

This Capstone Edition of Graphite is released under the **Apache License 2.0**, a widely-used open-source license that allows:

✔ Use
✔ Modification
✔ Distribution
✔ Private or commercial use
✔ Derivative works

**Provided that** you include:

* attribution to the original author (**Matthew Robert Wesney**)
* preservation of the license text
* notice of any modifications

Apache 2.0 also includes:

* explicit patent rights
* explicit limitation of liability
* explicit disclaimer of warranty

This ensures the project is open, usable, and protected in an industry-standard way suitable for software.

---

## **Author**

**Matthew Robert Wesney**

---

## **Competition Track**

**Freestyle Track — Agents Intensive Kaggle Capstone Project (Nov 2025)**

---

## **A Personal Note**

For nearly two years, Graphite has been an evolving idea — a living system shaped by curiosity, frustration with linear interfaces, and the desire to work with AI in a way that feels intuitive rather than restrictive.

When I joined the Kaggle + Google Agents Intensive, I realized it was the perfect opportunity to refactor Graphite: reorganize the architecture, expand the agent system, and build the Orchestrator as the missing core. This Capstone Edition represents that convergence — the discipline of the course, the philosophy of Graphite, and countless hours refining how humans and AI can think together.

Even in this reduced form, it reflects the same belief the full version does:
that clarity, structure, and well-designed tools can change how we work, think, and create.

---

## **Citation**

```
Matthew Wesney. Graphite – Kaggle Capstone Edition.
Kaggle Agents Intensive Capstone Project (2025).
```


