# **WorkflowGenie**

### Multi-Agent Productivity Orchestrator Powered by Gemini

WorkflowGenie is a structured, JSON-first multi-agent system that extracts tasks, builds schedules, generates reminders, and produces weekly summaries using an LLM-backed workflow.
It automates personal productivity and produces deterministic JSON outputs suitable for reliable downstream processing and ADK-based evaluation.

---

## 📌 **Kaggle Track Selection**

**Track:** *Concierge Agents*
Category: Systems that automate everyday personal workflows using multiple agents and strict tool interactions.

---

## 📝 **Overview**

Given a natural-language instruction such as:

> “I need to finish my internship form, study React for 2 hours, and email my professor before 5 PM.”

WorkflowGenie automatically:

1. Extracts actionable tasks
2. Plans a structured schedule
3. Creates reminders
4. Generates a weekly report
5. Returns a clean JSON response (and optionally displays a UI)

All LLM outputs are **strict JSON**, enforced through prompt engineering and automatic JSON repair.

---

## 🧠 **Architecture Overview**

### **1. Multi-Agent System**

Four independent agents cooperate through well-defined JSON interfaces:

#### **Task Extractor Agent**

Converts free-text input into structured tasks:

```json
[
  {"title": "...", "due": "ISO or null", "priority": "High|Medium|Low"}
]
```

#### **Planner Agent**

Generates a structured daily schedule:

```json
{
  "events": [
    {
      "title": "...",
      "start_time": "2025-11-25T09:00:00",
      "duration_mins": 60,
      "notes": ""
    }
  ],
  "assumptions": []
}
```

    server_flask.py
    legacy/static/
      index.html
      app.js
      style.css

  ## Architecture Diagram

  An architecture diagram illustrating the multi-agent flow is included below.

  ![WorkflowGenie Architecture](legacy/static/flowchart.png)

#### **Reporter Agent**

Produces a weekly summary in strict JSON format.

---

## 🛠 **Tools (Act on the World)**

Located in `/tools/`:

* **CalendarTool** – stores and manages scheduled events
* **ReminderTool** – creates and stores reminders

Both tools operate purely on JSON-compatible dictionaries.

---

## 💾 **Memory System**

Located in `/state/memory_store.py`.

* Powered by **TinyDB**
* Stores tasks, reminders, and events
* `TaskMemory.clear()` (alias for `clear_db()`) fully resets the state
* Legacy UI includes a “Clear DB” button for convenient resets

---

## 📐 **JSON-First LLM Design**

Every agent follows:

* Deterministic, schema-bound prompts
* `temperature = 0.0`
* Strict JSON-only responses
* Parsed using `safe_parse_json()`
* Automatic recovery from imperfect JSON

This ensures consistent downstream processing and robustness across models.

---

## 🧩 **ADK Concepts Implemented (Kaggle Requirements)**

Your project includes:

* ✔ Multi-agent orchestration pipeline
* ✔ Agent → Tool interactions
* ✔ Persistent session memory
* ✔ JSON-first context engineering
* ✔ Structured agent evaluation
* ✔ Logging and observability
* ✔ ADK-style workflow (`adk_app.main.run`)

Fully aligned with the ADK Concierge Agent rubric.

---

## ⚙ **Environment Setup**

### **1. Create a Virtual Environment**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### **2. Run ADK-Style Simulation (Recommended)**

```
python -m adk_app.simulate
```

Works without an API key (deterministic offline mode).

### **3. (Optional) Run Legacy Flask UI**

```powershell
python legacy/server_flask.py
```

Then open:

```
http://127.0.0.1:8080
```

### **4. Environment Variables**

PowerShell:

```powershell
$env:GEMINI_API_KEY="your_gemini_api_key"
```

Or create `.env`:

```
GEMINI_API_KEY=your_gemini_api_key
```

If no key is provided, WorkflowGenie runs in **offline deterministic mode**.

---

## 🧪 **Testing & Validation**

### Lint / Auto-Fix

```powershell
ruff check --fix .
```

### Run Simulation

```powershell
python -m adk_app.simulate
```

### Legacy UI Verification

```powershell
python legacy/server_flask.py
```

Verify static files load correctly using DevTools Network tab.

---

## 🗂 **File Structure**

```
workflowgenie/
│
├── adk_app/                  # ADK-compatible workflow
│   ├── agents.py
│   ├── tools.py
│   ├── workflow.py
│   └── simulate.py
│
├── adk/                      # Local ADK shim (used when real ADK not installed)
│   ├── agent.py
│   ├── tools.py
│   └── workflow.py
│
├── agents/                   # Core agent implementations (async)
├── tools/                    # Action tools
├── state/                    # TinyDB memory
├── utils.py                  # JSON parsing utilities
├── llm.py                    # Gemini wrapper + offline fallback
├── requirements.txt
├── .gitignore
├── README.md
│
└── legacy/                   # Optional local web UI
    ├── server_flask.py
    └── static/
        ├── index.html
        ├── app.js
        └── style.css
```

---

## 🚀 **Why WorkflowGenie Is Valuable**

* JSON-only, deterministic outputs
* Practical: automates real daily planning workflows
* Modular: easy to add new agents or tools
* Robust: handles imperfect LLM output automatically
* ADK-ready: clean pipeline, evaluatable, multi-agent

---

## 🔮 **Future Enhancements**

* Google Calendar API integration
* Weekly planner and multi-day workflow
* Vectorized long-term memory
* Cloud Run / Agent Engine deployment

---

## 📦 **Submission Summary**

Includes:

* README.md (this document)
* requirements.txt
* Dockerfile
* ADK application (`adk_app/`)
* Local ADK shim (`adk/`)
* Core agents & tools
* Legacy UI for optional testing

