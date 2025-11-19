<div align="center"\>

# ⬡ GRAPHITE

### The Visual Operating System for AI Agents

[](https://opensource.org/licenses/Apache-2.0)
[](https://kaggle.com)
[](https://python.org)
[](https://deepmind.google/technologies/gemini/)

*A spatial, node-based research environment for orchestrating complex multi-agent workflows.*

[Overview](https://www.google.com/search?q=%23overview) • [Visuals](https://www.google.com/search?q=%23visuals) • [Architecture](https://www.google.com/search?q=%23architecture) • [Roadmap](https://www.google.com/search?q=%23roadmap) • [Citation](https://www.google.com/search?q=%23citation)

</div>

-----

## **Overview**

**Graphite** replaces the linear feed with an **infinite, node-based canvas**.

We have access to the smartest AI models in history, yet we interact with them through an interface designed for SMS texting. Trying to architect a complex software system or conduct deep market research in a linear chat window feels like trying to paint a masterpiece through a keyhole.

Graphite transforms AI interaction from a timeline into a **topology**. In Graphite, every thought, tool call, and agent interaction is a physical node that can be moved, connected, branched, and inspected.

### **The Core Innovation: The Orchestrator**

Instead of the user manually dragging nodes to build a workflow, the **Agent Orchestrator** acts as a specialized autonomous agent. You give it a high-level goal (*"Research Bitcoin's current price and write a Python script to save it to my desktop"*), and it **programmatically builds the graph for you**.

-----

## **Visuals**

### **1. Orchestrator → Web Tool → Desktop Document**
*The orchestrator retrieves real-time Bitcoin pricing and auto-generates a local text artifact on the user’s desktop.*

<div align="center">
  <img src="https://www.googleapis.com/download/storage/v1/b/kaggle-user-content/o/inbox%2F20124535%2Fc1c748250e940e8db9c5801a53a23ae7%2FScreenshot%202025-11-16%20112132.png?generation=1763327435899819&alt=media" alt="Orchestrator Price Workflow" width="100%">
</div>

<br>

### **2. Orchestrator → Web Research → PyCoder → Markdown Report**
*The orchestrator plans a multi-step workflow, gathers grounded sources, synthesizes findings, formats them via PyCoder, and outputs a final Markdown artifact.*

<div align="center">
  <img src="https://www.googleapis.com/download/storage/v1/b/kaggle-user-content/o/inbox%2F20124535%2F9523f8f02e580ab2b5a3e0f8128333df%2FScreenshot%202025-11-16%20165305.png?generation=1763330021366808&alt=media" alt="Orchestrator Markdown Workflow" width="100%">
</div>

-----

## **Architecture & Technical Breakdown**

Graphite is built on a **Parent-Child Node Architecture**. Every node inherits the conversation history of its parent, creating a directed acyclic graph (DAG) of context. The system is a robust **PyQt6 (Python)** application (\~24k LOC).

### **The Agents**

| Component | Type | Description |
| :--- | :--- | :--- |
| **Orchestrator** | `graphite_orchestrator.py` | **The Brain.** Uses a "ReAct" style loop to output structured JSON plans. It parses these plans to dynamically instantiate other nodes on the canvas. |
| **Py-Coder** | `graphite_pycoder.py` | **The Hands.** A dual-mode agent. It executes Python via a local `subprocess` sandbox, capturing `stdout` and `stderr` for debugging. |
| **Reasoning** | `graphite_reasoning.py` | **The Conscience.** Implements a "Plan → Reason → Critique" loop, visualizing the internal monologue often hidden in other apps. |

### **Key Features**

  * **Multi-Agent Architecture:** Sequential & Hierarchical orchestration where control is passed down a chain of specialized nodes.
  * **The "Memory Bank":** A physical node that stores key-value pairs (e.g., `{'bitcoin_price': '92000'}`), ensuring data persistence across the graph without polluting the context window.
  * **Tool Use (Artifacts):** Integrated `duckduckgo_search` for live data and a custom `CodeExecutionWorker` thread that runs generated Python code locally to create real files.
  * **State Serialization:** Advanced context management via SQLite (`chats.db`) allows users to close the app and resume complex multi-agent negotiations exactly where they left off.

-----

## **Reflections & The Road Ahead**

> *Systems thinking is how I make sense of the world. My obsession with autonomous agents isn't just technical—it is deeply personal. I dig into these architectures because I am driven by a need to understand the cosmos itself: to witness how order emerges from chaos, and how scattered parts coalesce into a living, breathing whole.*

If I had more time, I would take Graphite from a powerful prototype to a full-scale **Agent Operating System**. Here is the roadmap:

### **1. The "Agent Marketplace" (Dynamic Tool Loading)**

Build a plugin architecture that allows Graphite to dynamically load tools from a community marketplace. Dragging a **"Jira Node"** or **"Salesforce Node"** onto the canvas instantly gives the Orchestrator the ability to interact with those platforms without writing glue code.

### **2. Recursive Orchestration (Agents Hiring Agents)**

Implement **nested orchestration**, where an Orchestrator Node can spawn *another* Orchestrator Node as a sub-task. This allows for fractally complex workflows—one master agent delegating to sub-agents who manage coding, testing, and marketing independently.

### **3. "Live" Memory & Vector Integration**

Integrate a local vector database (like **ChromaDB**) directly into the graph. This transforms the ephemeral Memory Bank into a **long-term knowledge base** that grows alongside the user's projects.

### **4. The "Self-Evolving" Topology (Meta-Optimization)**

**The Endgame.** Implement a **Meta-Orchestrator** that watches the graph execute in real-time. If a path fails or is inefficient, the AI acts as a self-healing architect—deleting bad nodes, rewiring connections, and optimizing the topology on the fly without human intervention.

-----

## **Competition Track**

**Freestyle Track** — *Graphite doesn't just fit into a category; it is a tool for building agents in ANY category.*

### **About This Edition**

This is the **Capstone-focused build** of Graphite for the **Kaggle + Google AI Agents Intensive (Nov 2025)**. The full internal development version continues privately, while this edition distills the system into a clean architecture aligned with the course themes of planning, tooling, memory, and observability.

-----

## **License**

This project is licensed under the **Apache License 2.0**.

-----

## **Citation**

If you use concepts from Graphite in your research or development, please cite:

```
@software{wesney2025graphite,
  author = {Wesney, Matthew},
  title = {Graphite: A Visual Multi-Agent Canvas},
  note = {Kaggle Agents Intensive Capstone Project},
  year = {2025},
  url = {https://github.com/dovvnloading/Graphite}
}
```

<div align="center"\>
<sub\>Built with 🖤 by Matthew Robert Wesney</sub>
</div>
