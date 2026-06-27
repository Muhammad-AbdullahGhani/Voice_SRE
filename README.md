# Voice SRE (Agentic Infrastructure Supervisor)

This project is a Real-Time Agentic Voice Supervisor for Kubernetes cluster management and telemetry querying. It leverages FastAPI, LangGraph, LiveKit, Prometheus, and the Kubernetes Python client.

---

## Current Progress

### Phase 1: Deterministic Tooling & Infrastructure Bridge
- **FastAPI Project Structure**: Core project modules (`app/`, `tests/`) initialized.
- **Kubernetes Client Tools**: Read-only tools `get_pod_status()` and `get_node_metrics()` implemented with automatic failover to high-fidelity mock data.
- **Unit & Integration Testing**: Implemented initial endpoint and tool test cases.

### Phase 2: LangGraph Orchestration (Newly Completed)
- **LangGraph State Machine**: Designed and compiled a `StateGraph` agent supervisor in [app/agents/supervisor.py](file:///C:/Users/i222683AbdullahGhani/desktop/voice_sre/app/agents/supervisor.py).
- **Node Workflows**: Implemented a four-step loop:
  - `listen`: STT transcript capture interface.
  - `reason`: Evaluates the conversation status, invoking an LLM or fallback rule-based reasoning engine.
  - `tool_use`: Performs asynchronous Kubernetes function calling.
  - `synthesize_response`: Synthesizes final text back for the TTS engine.
- **Conversational Memory**: Integrated a checkpointer `MemorySaver` in LangGraph to persist conversation threads and manage multi-turn context (e.g., matching subsequent instructions like *"scale it up"* or *"restart it"* to the active deployment context).
- **Kubernetes Action Tools**: Expanded [app/tools/kubernetes.py](file:///C:/Users/i222683AbdullahGhani/desktop/voice_sre/app/tools/kubernetes.py) with mutate capabilities:
  - `restart_pod()`: Deletes the pod to trigger a rolling/immediate restart (with active state mutations in mock mode).
  - `scale_deployment()`: Scales replicas up or down (with high-fidelity mock pod updates in mock mode).
- **Interactive CLI Demo**: Created a text-based terminal program [cli.py](file:///C:/Users/i222683AbdullahGhani/desktop/voice_sre/cli.py) to test state transitions and memory saving interactively.
- **Orchestration Tests**: Created [tests/test_agent.py](file:///C:/Users/i222683AbdullahGhani/desktop/voice_sre/tests/test_agent.py) to ensure the LangGraph loop, memory, and mock transitions work perfectly.

---

## Directory Structure
```
voice_sre/
├── requirements.txt
├── README.md
├── cli.py                 # Text-based Supervisor CLI (Interactive Test program)
├── app/
│   ├── __init__.py
│   ├── main.py            # FastAPI Entry Point (with read and action routes)
│   ├── config.py          # App Config Manager (Pydantic settings)
│   ├── agents/
│   │   ├── __init__.py
│   │   └── supervisor.py  # LangGraph Agent State Graph & Nodes
│   └── tools/
│       ├── __init__.py
│       └── kubernetes.py  # Kubernetes Client & Tool Functions
└── tests/
    ├── __init__.py
    ├── test_k8s_tools.py  # Basic Tools Tests
    └── test_agent.py      # LangGraph Supervisor Agent Tests
```

---

## Getting Started

### 1. Prerequisites
- Python 3.13+
- (Optional) Kubernetes cluster context (e.g. Minikube, Kind, or remote cluster)

### 2. Setup Virtual Environment & Install Dependencies
```bash
python -m venv .venv
.venv\Scripts\activate  # On Windows
pip install -r requirements.txt
```

### 3. Run Interactive CLI Agent
To interactively chat with the supervisor and watch node transitions (`LISTEN -> REASON -> TOOL_USE -> REASON -> SYNTHESIZE`):
```bash
python cli.py
```
*Example queries to try:*
- `"check pods"`
- `"restart pod auth-service-9d8e7f6c-12345"`
- `"scale payment-gateway to 5"`
- `"show me the pods in production again"` (confirms scaling is saved in state!)
- `"what are the node metrics?"`

### 4. Run FastAPI Backend Server
```bash
python -m app.main
```
The server starts on [http://localhost:8000](http://localhost:8000).
- **Interactive Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Get Pods**: [http://localhost:8000/api/pods](http://localhost:8000/api/pods)
- **Get Nodes**: [http://localhost:8000/api/nodes](http://localhost:8000/api/nodes)
- **Restart Pod (POST)**: [http://localhost:8000/api/pods/restart](http://localhost:8000/api/pods/restart)
- **Scale Deployment (POST)**: [http://localhost:8000/api/deployments/scale](http://localhost:8000/api/deployments/scale)

### 5. Running Tests
Run the entire suite of FastAPI endpoint, tool, and LangGraph agent tests:
```bash
pytest
```
