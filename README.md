# **Graphite – Kaggle Capstone Edition**

### *A Visual Multi-Agent Canvas for Orchestrated AI Workflows*

[![License: CC BY-NC-ND 4.0](https://licensebuttons.net/l/by-nc-nd/4.0/80x15.png)](https://creativecommons.org/licenses/by-nc-nd/4.0/)




---

## **Overview**

This repository contains the **Capstone Edition** of **Graphite**, a visual multi-agent research environment created for the **Kaggle + Google AI Agents Intensive (Nov 2025)**.
It is a reduced, academically shareable version of the full Graphite platform — refactored specifically for the requirements of the Capstone project.

Graphite replaces the constraints of linear chat with an infinite, spatial canvas where every thought, tool call, and agent operation becomes a visual node. Complex tasks unfold as structured workflows instead of unmanageable message logs.

This release introduces the **Agent Orchestrator**, a system-level agent capable of planning and executing multi-step workflows using specialized sub-agents. The Orchestrator is the central feature developed specifically for this Capstone submission.

---

## **Screenshots (Provided to Kaggle Judges)**

### **Orchestrator → Web Tool → Desktop Document**

*The orchestrator retrieves real-time Bitcoin pricing and auto-generates a local text artifact on the user's desktop.*

![Orchestrator Price Workflow](https://www.googleapis.com/download/storage/v1/b/kaggle-user-content/o/inbox%2F20124535%2Fc1c748250e940e8db9c5801a53a23ae7%2FScreenshot%202025-11-16%20112132.png?generation=1763327435899819\&alt=media)

---

### **Orchestrator → Web Research → PyCoder → Markdown Report**

*The orchestrator plans a multi-step workflow, gathers grounded sources, synthesizes findings, formats them into Markdown via PyCoder, and outputs an artifact.*

![Orchestrator Markdown Workflow](https://www.googleapis.com/download/storage/v1/b/kaggle-user-content/o/inbox%2F20124535%2F9523f8f02e580ab2b5a3e0f8128333df%2FScreenshot%202025-11-16%20165305.png?generation=1763330021366808\&alt=media)

---

## **Key Capstone Features**

### **✓ Multi-Agent Architecture**

Graphite demonstrates more than the required three concepts:

* Orchestrator agent
* Sequential & parallel sub-agents
* Loop agents (PyCoder repair cycles)
* Memory system
* Context inheritance
* Tool invocation (web, code execution, file handling)
* Observability & logging

### **✓ Orchestrator Agent**

A high-level programmatic operator capable of:

* interpreting a user’s natural-language goal
* generating a JSON plan
* executing steps across multiple agents
* passing data via a Memory Bank
* producing artifacts (reports, files, results)

### **✓ Infinite Node-Based Canvas**

A PySide6-powered visual environment:

* branch any conversation
* parallel reasoning
* deep context lineage
* tool agents as visual elements
* execution logs embedded in nodes

### **✓ Persistence & Memory**

Graphite stores full session state using SQLite:

* node content
* position on canvas
* tool outputs
* logs
* graph structure

---

## **Repository Structure**

```
graphite-capstone/
│
├── graphite_core/         # Session manager, persistence, core utilities
├── graphite_agents/       # Orchestrator, PyCoder, WebNode, Reasoning, Memory
├── graphite_ui/           # PySide6 infinite canvas, nodes, containers
├── tools/                 # Code execution, file handlers, API provider
│
├── LICENSE                # CC BY-NC-ND 4.0 (protected release)
├── README.md              # This file
└── examples/              # Sample workflows
```

---

## **About This Edition**

This repository contains a **restricted, academically shareable version** of Graphite.
The full Graphite platform (private, ~24k LOC) remains under MIT license in its primary repo.
This Capstone edition (~7k LOC) exists for:

* evaluation by Kaggle judges
* demonstration of agentic architecture
* research transparency

It is *not* intended for reuse, incorporation, or commercial deployment.

---

## **License**

### **CC BY-NC-ND 4.0 — Attribution + NonCommercial + NoDerivatives**

This is a **protective license**.
It permits:

* viewing the code
* cloning for local evaluation
* running the application

It **does not** permit:

* commercial use
* modification
* redistribution
* derivative works
* incorporation into other software
* code extraction for training datasets
* any reuse beyond viewing + evaluating

Professionally:

> “You may look, but you may not touch.”

The full license text is provided in `/LICENSE`.

---

## **Author**

**Matthew Wesney**

---

## **Competition Track**

**Freestyle Track — Agents Intensive Kaggle Capstone Project (Nov 2025)**

---

## **A Personal Note**

For nearly two years, Graphite has been a living, evolving project—something I’ve built piece by piece, often late at night, driven by equal parts curiosity and necessity. What started as a simple attempt to break free from linear chat interfaces grew into a full visual reasoning system, an exploration of how humans and AI might collaborate more intuitively.

When I joined the Kaggle + Google Agents Intensive, I realized it was the perfect moment to refactor Graphite—strip it down, reorganize its architecture, and build the Orchestrator as the missing cornerstone. This Capstone Edition represents that convergence: the discipline of the course, the philosophy behind Graphite, and the quiet, persistent work of building something that reflects how I think and how I solve problems.

It means a great deal to me to share this version. Even in its reduced form, it carries the spirit of the full system: a belief in clarity, structure, and the power of well-designed agents working together.

---

## **Citation**

```
Matthew Wesney. Graphite – Kaggle Capstone Edition.
Kaggle Agents Intensive Capstone Project (2025).
```
