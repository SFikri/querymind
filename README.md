# QueryMind 🔍
### Natural Language Data Analyst · Medicare Intelligence Swarm

> *"What if anyone could interrogate a 50M-row healthcare dataset just by asking a question?"*

**Track B — Quantitative Forge · Gemini Nexus: The Agentverse Boss Raid 2026**
Built by: Syed Fikri Syaddad for Gemini Nexus The Agentverse and 

---

## What It Does

QueryMind is an autonomous multi-agent swarm that lets anyone ask questions about US Medicare public data in plain English — and receive:
- An auto-generated, validated BigQuery SQL query
- A plain-English insight summary
- A rendered chart (bar, line, pie, or table)
- A complete **agent thinking log** showing every reasoning step

The system handles errors autonomously: if the SQL fails, the recovery loop retries with a corrected query — without any human intervention.

---

## System Architecture — A2A Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                        User (Streamlit UI)                       │
│               "Which states spend most on Medicare?"             │
└─────────────────────────┬───────────────────────────────────────┘
                          │ natural language question
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│              Orchestrator (ADK SequentialAgent)                  │
│         Gemini 2.5 Flash · Vertex AI · thinking traces          │
│   ┌──────────────────┐          ┌──────────────────────────┐    │
│   │  ADK Safety      │          │  MCP Server (FastMCP)    │    │
│   │  Guardrails      │◄────────►│  BigQuery tool calls     │    │
│   │  (block writes)  │          │  get_schema / run_sql    │    │
│   └──────────────────┘          └──────────────────────────┘    │
│                                                                  │
│   Step 1: schema_fetcher ──► discovers tables + columns          │
│                                                                  │
│   Step 2: sql_recovery_loop (ADK LoopAgent, max 3 retries)       │
│     ├── sql_generator  ──► NL → BigQuery SQL                     │
│     └── query_executor ──► runs SQL via MCP                      │
│           │ FAIL → loop back to sql_generator with error msg     │
│           │ SUCCESS → exit loop                                   │
│                                                                  │
│   Step 3: narrator ──► rows → insight summary + chart spec       │
└─────────────────────────┬───────────────────────────────────────┘
                          │ JSON: summary + chart + key_finding
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│              Streamlit UI (deployed on Cloud Run)                │
│   Left panel: chart + narrative    Right panel: thinking log     │
└─────────────────────────────────────────────────────────────────┘
```

---

## Agent Profiles

| Agent | Type | Role | Recovery behaviour |
|---|---|---|---|
| `schema_fetcher` | ADK Agent | Calls `get_dataset_schema()` via MCP. Outputs column/table map for downstream agents. | Stateless; re-runs on orchestrator retry. |
| `sql_generator` | ADK Agent | Receives user question + schema + (optionally) prior error. Outputs a valid BigQuery SELECT. | On retry, receives the executor's error message and corrects the SQL accordingly. |
| `query_executor` | ADK Agent | Calls `run_bigquery_sql()` via MCP. Signals `EXECUTION_SUCCESS` or `EXECUTION_FAILED: <reason>`. | Failure signal triggers LoopAgent to re-run `sql_generator`. |
| `sql_recovery_loop` | ADK LoopAgent | Wraps `sql_generator` + `query_executor`. Iterates up to 3× until success or max retries. | **Core agentic recovery** — demonstrates autonomous error handling with reasoning traces. |
| `narrator` | ADK Agent | Receives result rows. Outputs structured JSON: `summary`, `key_finding`, `chart` spec. | Falls back to table display if chart spec is malformed. |
| `querymind_orchestrator` | ADK SequentialAgent | Top-level coordinator. Runs agents in order, passing context between steps. | Captures full thinking trace for display in UI. |

---

## Tech Stack

| Layer | Technology |
|---|---|
| LLM | Gemini 2.5 Flash (Vertex AI) |
| Agent framework | Google ADK (SequentialAgent, LoopAgent, Agent) |
| Tool protocol | MCP via FastMCP (StdioServerParameters) |
| Data | BigQuery — `bigquery-public-data.cms_medicare` |
| Safety | ADK input guardrails — blocks INSERT/UPDATE/DELETE/DROP |
| Frontend | Streamlit + Plotly |
| Deployment | Cloud Run (asia-southeast1) |

**Sessions covered:** S3 (MCP), S4 (ADK guardrails), S6 (ADK + BigQuery), S8 (multi-agent patterns — Sequential, Loop)

---

## Setup Instructions

### Prerequisites
- Python 3.11+
- GCP project with BigQuery API and Vertex AI API enabled
- `gcloud` CLI authenticated (`gcloud auth application-default login`)

### Local run

```bash
# 1. Clone
git clone https://github.com/<your-username>/querymind
cd querymind

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set your GCP project
export GOOGLE_CLOUD_PROJECT="your-project-id"

# 4. Run
streamlit run app.py
```

Open http://localhost:8501

### Cloud Run deployment

```bash
chmod +x deploy.sh
./deploy.sh your-gcp-project-id
```

### Environment variables

| Variable | Description |
|---|---|
| `GOOGLE_CLOUD_PROJECT` | Your GCP project ID |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to service account JSON (if not using ADC) |

---

## Demo Queries

These three questions are designed to showcase the full pipeline in 150 seconds:

1. **"Which states had the highest average Medicare payment per beneficiary?"**
   — triggers bar chart, shows state-level ranking

2. **"What are the top 10 procedures by total payment amount?"**
   — triggers recovery loop if column names differ, shows self-correction

3. **"Show me inpatient discharge volume by state."**
   — triggers line/bar chart, shows the narrator's insight summary

---

## Project Structure

```
querymind/
├── app.py              # Streamlit UI (chart + thinking log panels)
├── agents.py           # ADK agents: orchestrator, SQL gen, recovery loop, narrator
├── mcp_server.py       # FastMCP server exposing BigQuery as MCP tools
├── requirements.txt    # Python dependencies
├── Dockerfile          # Cloud Run container
└── deploy.sh           # One-command Cloud Run deploy
```

---

## Key Design Decisions

**Why MCP for BigQuery?** Using FastMCP wraps BigQuery as a proper tool call rather than a hardcoded SDK call. This means any ADK agent — or future external agent — can call it via the standard protocol. It also cleanly separates the data layer from the reasoning layer.

**Why a LoopAgent for recovery?** SQL generation over an unfamiliar schema fails on first attempt more often than not. The LoopAgent pattern (from S8) means the system is genuinely autonomous — it reads its own error, reasons about the fix, and retries. This is what "agentic agency" means in practice.

**Why show thinking logs?** The judging rubric rewards visible reasoning traces. The UI explicitly surfaces every agent step so judges — and users — can see the system thinking, not just the output.

---

*Built in 24 hours · Gemini Nexus: The Agentverse · GDG UTM + GDG George Town · March 2026*
