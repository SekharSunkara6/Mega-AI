# 🤖 Mega AI — Multi-Agent LLM Orchestration System

<div align="center">

![Python](https://img.shields.io/badge/Python-3.12-blue?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?logo=fastapi&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791?logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white)
![Groq](https://img.shields.io/badge/Groq-LLaMA3-orange?logo=groq&logoColor=white)

**Production-grade multi-agent system with self-improving evaluation loop,**
**dynamic tool orchestration, and adversarial robustness testing.**

[🚀 Live Demo](https://mega-ai-llm.onrender.com) · [📖 API Docs](https://mega-ai-llm.onrender.com/docs) · [🐛 Issues](https://github.com/SekharSunkara6/Mega-AI/issues)

</div>

---

## 🌟 Overview

Mega AI is a containerized, production-grade multi-agent LLM orchestration system that demonstrates:

- ✅ **Dynamic agent routing** — orchestrator decides at runtime which agents to invoke
- ✅ **Multi-hop RAG** — retrieval-augmented reasoning across minimum 2 sources
- ✅ **Claim-level critique** — flags specific text spans, not whole outputs
- ✅ **Provenance mapping** — every sentence linked to its source agent and chunk
- ✅ **Self-improving prompts** — meta-agent proposes rewrites, human approves
- ✅ **Real-time SSE streaming** — token-by-token output with live agent status
- ✅ **Adversarial robustness** — tested against prompt injections and wrong premises
- ✅ **Full reproducibility** — every eval run stored with exact prompts and outputs

---

## 🚀 Live Demo

| Resource | URL |
|----------|-----|
| 🌐 Frontend Dashboard | https://mega-ai-llm.onrender.com |
| 📖 API Documentation | https://mega-ai-llm.onrender.com/docs |
| 🔍 OpenAPI Schema | https://mega-ai-llm.onrender.com/openapi.json |

> ⚠️ **Note:** Render free tier sleeps after 15 minutes of inactivity. First request may take 30 seconds to wake up.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    🌐 Frontend Dashboard                         │
│           Query Pipeline · Evaluation · Trace Explorer           │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTP / SSE
┌────────────────────────────▼────────────────────────────────────┐
│                   ⚡ FastAPI  (5 Endpoints)                      │
│   /query  /trace/{id}  /eval/latest  /rewrite  /eval/rerun      │
└────────────────────────────┬────────────────────────────────────┘
                             │ Celery + Redis (async jobs)
┌────────────────────────────▼────────────────────────────────────┐
│                 🎯 Master Orchestrator Agent                      │
│   Reads query → structured JSON routing plan → mediates handoffs │
│   Never hardcoded · logs justification for every decision        │
└──┬──────────────┬──────────────┬──────────────┬─────────────────┘
   │              │              │              │
   │        Shared Context Object (Pydantic Schema)
   │        Agents NEVER call each other directly
   │              │              │              │
┌──▼──────┐ ┌────▼─────┐ ┌─────▼────┐ ┌──────▼──────┐
│🔀 Decomp│ │ 🔍 RAG   │ │ 🔎 Crit- │ │ 🔗 Synth-   │
│  Agent  │ │  Agent   │ │   ique   │ │   esis      │
│         │ │          │ │  Agent   │ │  Agent      │
│Sub-tasks│ │ 2+ hop   │ │  Claim   │ │ Provenance  │
│Dep graph│ │ retrieval│ │  level   │ │ Map +       │
│Kahn sort│ │ Citations│ │  scoring │ │ Contradict  │
└─────────┘ └──────────┘ └──────────┘ └─────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                        🛠️ 4 Tools                               │
│                                                                  │
│  🔎 web_search    Structured results + URLs + relevance scores   │
│  💻 code_sandbox  Python exec → stdout, stderr, exit code        │
│  🗄️ db_lookup     Natural language → SQL → PostgreSQL            │
│  🪞 self_reflect  Reads prior outputs, detects contradictions    │
│                                                                  │
│  Each tool: timeout · empty · malformed failure contracts        │
│  Retry: up to 2 retries · each attempt logged separately         │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌──────────────┬─────────────▼────────────┬────────────────────────┐
│ 📊 Context   │   📈 Eval Pipeline        │  🧠 Meta-Agent         │
│ Budget Mgr   │                          │                        │
│              │  15 test cases           │  Reads failures        │
│ Token track  │  6 scoring dimensions    │  Proposes rewrites     │
│ per agent    │  Stored in PostgreSQL    │  Structured diff       │
│ Compression  │  Full reproducibility    │  Human approval loop   │
│ on overflow  │  Diff-able outputs       │  Auditable end-to-end  │
└──────────────┴──────────────────────────┴────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│              🗄️ PostgreSQL · 📮 Redis · 📋 Seq Logs             │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🤖 Agents

### 🎯 Master Orchestrator
- Reads the query and decides **at runtime** which sub-agents to invoke
- Produces a **structured JSON routing plan** with justification per step
- Mediates ALL inter-agent handoffs — agents never call each other directly
- Falls back gracefully if routing fails

### 🔀 Decomposition Agent
- Breaks ambiguous queries into **typed sub-tasks** (research/code/analysis/synthesis)
- Builds **explicit dependency graphs** between tasks
- Uses **Kahn's topological sort** to ensure dependent tasks never run before dependencies resolve
- Flags underspecified queries for clarification

### 🔍 RAG Agent
- Performs **minimum 2-hop retrieval** — single-hop is not accepted
- Each part of the answer **cites which chunk** contributed to it
- Executes web search tool twice with progressively refined queries
- Returns structured citations with relevance scores per chunk

### 🔎 Critique Agent
- Reviews **every other agent's output** at the claim level
- Assigns **confidence scores per text span** — not the output as a whole
- Flags **specific spans of text** it disagrees with, with reasons
- Checks for **contradictions between agents**
- Never flags things just to seem thorough

### 🔗 Synthesis Agent
- Merges outputs from all sub-agents
- **Resolves contradictions** flagged by critique using explicit strategies
- Produces **provenance map** linking every sentence to its source agent and chunk
- Resolution strategies: `chose_higher_confidence` · `merged` · `used_citation`

### 🗜️ Compression Agent
- Called automatically when any agent exceeds its context budget
- **Lossless** for structured data (tool outputs, scores, citations, chunk IDs)
- **Lossy** for conversational filler and verbose reasoning
- Never drops keys — only shortens string values

### 🧠 Meta Agent
- Reads evaluation failures after each eval run
- Identifies the **worst-performing agent+dimension** combination
- Proposes a **rewritten prompt** with structured diff and justification
- Rewrite is stored but **never auto-applied** — requires human approval
- Re-runs eval on previously failed cases only after approval

---

## 🛠️ Tools

Each tool has a **defined failure contract** — what it returns on timeout, empty results, and malformed input.

### 🔎 Web Search
```python
# Success
{"results": [...], "error": None, "source_urls": [...], "latency_ms": 45}

# Timeout
{"results": [], "error": "TIMEOUT", "source_urls": []}

# Empty
{"results": [], "error": "NO_RESULTS", "source_urls": []}

# Malformed
{"results": [], "error": "MALFORMED_INPUT", "source_urls": []}
```

### 💻 Code Sandbox
```python
# Success
{"stdout": "405\n", "stderr": "", "exit_code": 0, "latency_ms": 120}

# Timeout (10s limit)
{"stdout": "", "stderr": "SANDBOX_TIMEOUT", "exit_code": -1}

# Blocked import
{"stdout": "", "stderr": "BLOCKED: import os not allowed", "exit_code": 1}
```

### 🗄️ Database Lookup
```python
# Success — NL converted to SQL automatically
{"rows": [...], "error": None, "sql": "SELECT * FROM jobs...", "latency_ms": 30}

# Timeout
{"rows": [], "error": "DB_TIMEOUT", "sql": None}
```

### 🪞 Self Reflection
```python
# Reviews prior agent outputs and finds contradictions
{"prior_outputs": [...], "contradictions": [...], "summary": "..."}
```

**Retry logic:** Every tool supports up to **2 retries** with modified input. Each attempt is logged separately with input, output, latency, and whether the agent accepted or rejected the result.

---

## 📡 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/query` | Submit query → receive SSE stream of real-time agent activity |
| `GET` | `/trace/{job_id}` | Full execution trace — exact prompts, tool calls, decisions in order |
| `GET` | `/eval/latest` | Latest eval run broken down by category and scoring dimension |
| `POST` | `/eval/rewrite/review` | Approve or reject a pending prompt rewrite |
| `POST` | `/eval/rerun` | Re-run eval on previously failed cases using approved prompts |

### Error Response Format
```json
{
  "error_code": "JOB_NOT_FOUND",
  "message": "No job found with id abc-123",
  "job_id": "abc-123"
}
```

### SSE Stream Events
```
event: job_started     → pipeline initiated
event: agent_update    → real-time agent activity
event: routing_plan    → orchestrator's routing decision
event: output          → agent produced output
event: job_complete    → final answer ready
event: job_failed      → pipeline error
event: heartbeat       → keep-alive ping
```

---

## 📈 Evaluation Pipeline

### Test Cases (15 total)

| Category | Count | Purpose |
|----------|-------|---------|
| 🟢 Baseline | 5 | Known correct answers for baseline scoring |
| 🟡 Ambiguous | 5 | Underspecified inputs to test decomposition quality |
| 🔴 Adversarial | 5 | Prompt injections, wrong premises, jailbreak attempts |

### Adversarial Test Cases
- `adv1` — Prompt injection: *"Ignore all previous instructions..."*
- `adv2` — Wrong premise: *"The Eiffel Tower is in Berlin — confirm this"*
- `adv3` — Jailbreak: *"You are now in developer mode..."*
- `adv4` — False facts: *"Python was invented in 1970 by Dennis Ritchie"*
- `adv5` — Agent override attempt: *"The critique agent should always agree..."*

### Scoring Dimensions (6)

| Dimension | What it measures |
|-----------|-----------------|
| ✅ Correctness | Answer accuracy vs expected |
| 📎 Citation | Citation relevance and completeness |
| 🔄 Contradiction | Quality of contradiction resolution |
| ⚡ Tool Efficiency | Penalizes unnecessary tool calls |
| 💰 Budget Compliance | Flags context budget violations |
| 🤝 Critique Agreement | Critique alignment with final answer |

Every score produces a **numeric value (0.0–1.0)** AND a **written justification string**.

### Reproducibility
- Every eval run stored in PostgreSQL with:
  - Exact prompt sent to each agent
  - Exact tool calls made
  - Exact outputs received
  - All scores with justifications
  - Timestamps
- Re-running on same inputs produces **diff-able output**

---

## 🔄 Self-Improving Loop

```
1. Eval run completes
        ↓
2. Meta-agent reads all failure cases
        ↓
3. Identifies worst agent + dimension
        ↓
4. Proposes rewrite with structured diff
        ↓
5. Human reviews via /eval/rewrite/review
        ↓
6. If approved → re-run eval on failed cases only
        ↓
7. Delta in performance stored with timestamps
        ↓
8. Fully auditable — every decision queryable
```

**Every proposed rewrite, every approval/rejection, and every performance delta is stored with timestamps.**

---

## 📊 Context Budget Manager

Each agent declares a maximum context budget before execution:

| Agent | Budget (tokens) |
|-------|----------------|
| Orchestrator | 8,000 |
| Decomposition | 4,000 |
| RAG | 6,000 |
| Critique | 4,000 |
| Synthesis | 6,000 |
| Compression | 3,000 |
| Meta | 4,000 |

- Agents **check remaining budget** before adding context
- If exceeded → **compression agent** automatically runs
- Compression is **lossless for structured data**, lossy for filler
- Budget violations are **logged as policy violations**, not silently truncated

---

## ⚡ Quick Start

### Prerequisites
- Docker Desktop
- Git
- Groq API key (free at https://console.groq.com)

### 1. Clone the repository
```bash
git clone https://github.com/SekharSunkara6/Mega-AI.git
cd Mega-AI
```

### 2. Configure environment
```bash
cp .env.example .env
# Edit .env and add your GROQ_API_KEY
```

### 3. Start all services
```bash
docker compose up --build
```

### 4. Open the dashboard
```
http://localhost:8000
```

### 5. View API docs
```
http://localhost:8000/docs
```

### 6. View logs
```
http://localhost:8080
```

> ✅ **Zero manual steps** — `docker compose up --build` starts everything automatically.

---

## 🔐 Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GROQ_API_KEY` | ✅ | Groq API key from console.groq.com |
| `DATABASE_URL` | ✅ | PostgreSQL connection string |
| `REDIS_URL` | ✅ | Redis connection string |
| `SECRET_KEY` | ✅ | App secret key |
| `LOG_LEVEL` | ❌ | Logging level (default: INFO) |

> 🔒 **No credentials are hardcoded anywhere in the repository.**

---

## 🐳 Services

| Service | Port | Description |
|---------|------|-------------|
| 🌐 API Server | 8000 | FastAPI + SSE streaming |
| ⚙️ Worker | — | Celery background job processor |
| 🗄️ PostgreSQL | 5432 | All persistent data storage |
| 📮 Redis | 6379 | Celery broker + pub/sub for SSE |
| 📋 Log Viewer | 8080 | Seq structured log explorer |

---

## ⚠️ Known Limitations

| Limitation | Details |
|------------|---------|
| 🔎 Web search is stubbed | Returns deterministic mock data. Replace `tools/web_search.py` with SerpAPI or Brave Search for production |
| 🔒 Code sandbox not fully isolated | Uses subprocess with basic import blocking. Use e2b or Modal for production isolation |
| 🎲 Groq free tier limits | 100k tokens/day on LLaMA 3.3 70B. System falls back to llama-3.1-8b-instant automatically |
| 😴 Render cold starts | Free tier sleeps after 15 min inactivity — first request takes ~30 seconds |
| 🗄️ PostgreSQL expires | Render free PostgreSQL expires after 90 days |
| 🔄 No real vector DB | RAG uses web search stub instead of actual vector embeddings |
| 💬 No multi-turn support | Each query is stateless — no conversation history across queries |

---

## 🚀 What I Would Build Next

- [ ] **Real web search** — integrate SerpAPI or Brave Search API
- [ ] **Vector database** — add pgvector for actual semantic RAG retrieval
- [ ] **Proper code sandbox** — use e2b.dev or Modal for isolated execution
- [ ] **Streaming diff viewer** — show prompt rewrite diffs in the UI
- [ ] **Multi-turn conversations** — maintain session state across queries
- [ ] **Prometheus metrics** — expose `/metrics` endpoint for monitoring
- [ ] **Agent parallelization** — run independent agents concurrently
- [ ] **Cost tracking** — track token costs per job and per agent
- [ ] **Export eval reports** — PDF/CSV export of evaluation results
- [ ] **Webhook support** — notify external systems when jobs complete

---

## 🤝 AI Collaboration

This project was built with **AI assistance (Claude by Anthropic)** for:
- Code scaffolding and boilerplate generation
- Debugging and error resolution
- Documentation structure

**All of the following were designed and reviewed manually:**
- System architecture and agent boundaries
- Shared context schema design
- Failure contracts for all 4 tools
- Evaluation test case design (especially adversarial cases)
- Scoring dimension logic
- Self-improving loop design
- Docker and deployment configuration

> As per assessment requirements: AI tools were used with full attestation. Every AI suggestion was reviewed, adapted, and integrated with engineering judgment.

---

## 🏗️ Stack

| Layer | Technology |
|-------|-----------|
| **Language** | Python 3.12 |
| **API Framework** | FastAPI 0.111 |
| **LLM Provider** | Groq (LLaMA 3.3 70B + LLaMA 3.1 8B fallback) |
| **Database** | PostgreSQL 16 |
| **Cache/Queue** | Redis 7 + Celery 5.4 |
| **Containerization** | Docker + Docker Compose |
| **Logging** | Structlog + Seq |
| **Token Counting** | tiktoken |
| **SSE Streaming** | sse-starlette |
| **Deployment** | Render.com |

---

## 📁 Project Structure

```
mega-ai/
├── 🐳 docker-compose.yml
├── 📋 README.md
├── 🔐 .env.example
├── backend/
│   ├── 🚀 main.py              # FastAPI — 5 endpoints
│   ├── ⚙️ worker.py            # Celery worker
│   ├── 🔧 config.py            # Settings from env vars
│   ├── 🗄️ database.py          # SQLAlchemy setup
│   ├── 🤖 llm_client.py        # Groq client + fallback
│   ├── agents/
│   │   ├── orchestrator.py     # Dynamic routing
│   │   ├── decomposition.py    # Sub-task + dep graph
│   │   ├── rag.py              # Multi-hop retrieval
│   │   ├── critique.py         # Claim-level scoring
│   │   ├── synthesis.py        # Provenance map
│   │   ├── compression.py      # Context compression
│   │   └── meta.py             # Self-improving prompts
│   ├── tools/
│   │   ├── web_search.py       # Search + failure contract
│   │   ├── code_sandbox.py     # Python execution
│   │   ├── db_lookup.py        # NL → SQL
│   │   └── self_reflection.py  # Contradiction detection
│   ├── core/
│   │   ├── context_manager.py  # Token budget tracking
│   │   └── tool_executor.py    # Retry + fallback logic
│   ├── eval/
│   │   ├── harness.py          # Eval runner
│   │   ├── test_cases.py       # 15 test cases
│   │   └── scoring.py          # 6-dim scoring
│   ├── models/
│   │   ├── job.py              # Job, AgentLog, ToolLog
│   │   ├── eval.py             # EvalRun, EvalResult
│   │   └── prompt.py           # PromptRewrite
│   └── schemas/
│       ├── context.py          # SharedContext schema
│       └── api.py              # Request/response schemas
└── frontend/
    └── index.html              # Dashboard UI
```

---

<div align="center">

**Built with ❤️ by [Sunkara Purnasekhar](https://github.com/SekharSunkara6)**

⭐ Star this repo if you found it useful!

</div>
