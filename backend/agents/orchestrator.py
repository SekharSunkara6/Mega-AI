import json, time, uuid
from llm_client import chat
from schemas.context import SharedContext, AgentOutput
from core.context_manager import ContextBudgetManager
from core.tool_executor import execute_tool
from tools.web_search import web_search
from tools.code_sandbox import run_code
from tools.db_lookup import db_lookup
from tools.self_reflection import self_reflect
import structlog

log = structlog.get_logger()

ORCHESTRATOR_SYSTEM = """You are a master orchestrator agent. Given a user query, you decide which sub-agents to invoke, in what order, and why.

Available sub-agents:
- decomposition: breaks complex/ambiguous queries into typed sub-tasks with dependency graphs
- rag: performs multi-hop retrieval-augmented reasoning with citations
- critique: reviews any agent output and scores claims with confidence
- synthesis: merges all outputs, resolves contradictions, produces final answer with provenance

Your response MUST be valid JSON with this exact structure:
{
  "reasoning": "step-by-step justification for routing decision",
  "routing_plan": [
    {"agent": "decomposition", "reason": "why", "context_budget": 4000},
    {"agent": "rag", "reason": "why", "context_budget": 6000},
    {"agent": "critique", "reason": "why", "context_budget": 4000},
    {"agent": "synthesis", "reason": "why", "context_budget": 6000}
  ],
  "tools_needed": ["web_search", "code_execution"],
  "complexity": "low|medium|high"
}

Rules:
- Do NOT hardcode a fixed chain. Evaluate the query and choose only needed agents.
- Simple factual queries may skip decomposition.
- Always end with synthesis if multiple agents are used.
- Always include critique before synthesis.
- Justify every routing decision explicitly."""


def run_orchestrator(context: SharedContext, stream_callback=None) -> SharedContext:
    budget = ContextBudgetManager(context)
    start = time.time()

    prompt = f"Query: {context.original_query}\n\nPrior context: {json.dumps({'sub_tasks': len(context.sub_tasks), 'outputs_so_far': list(context.agent_outputs.keys())})}"

    fits, needed = budget.check_budget("orchestrator", prompt)
    if not fits:
        log.error("orchestrator_budget_exceeded", needed=needed)
        context.policy_violations.append(f"orchestrator: prompt needs {needed} tokens, budget exceeded")
        return context

    budget.consume("orchestrator", prompt)

    if stream_callback:
        stream_callback({"agent": "orchestrator", "event": "start", "data": "Analyzing query and planning agent routing..."})

    try:
        raw = chat(ORCHESTRATOR_SYSTEM, prompt, max_tokens=1000)

        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        plan = json.loads(raw.strip())

    except (json.JSONDecodeError, Exception) as e:
        log.error("orchestrator_parse_error", error=str(e))
        # Fallback to full pipeline
        plan = {
            "reasoning": f"Fallback due to parse error: {e}",
            "routing_plan": [
                {"agent": "decomposition", "reason": "fallback", "context_budget": 4000},
                {"agent": "rag",           "reason": "fallback", "context_budget": 6000},
                {"agent": "critique",      "reason": "fallback", "context_budget": 4000},
                {"agent": "synthesis",     "reason": "fallback", "context_budget": 6000},
            ],
            "tools_needed": [],
            "complexity": "medium"
        }

    latency = (time.time() - start) * 1000
    context.agent_outputs["orchestrator"] = AgentOutput(
        agent_id="orchestrator",
        content=plan,
        token_count=needed,
    )
    context.metadata["routing_plan"] = plan["routing_plan"]
    context.metadata["orchestrator_reasoning"] = plan["reasoning"]
    context.metadata["complexity"] = plan.get("complexity", "medium")

    if stream_callback:
        stream_callback({
            "agent": "orchestrator",
            "event": "routing_plan",
            "data": plan["reasoning"],
            "plan": plan["routing_plan"],
            "budget_remaining": budget.remaining("orchestrator")
        })

    log.info("orchestrator_done", latency_ms=latency, agents_planned=len(plan["routing_plan"]))

    # Now execute each agent in order
    from agents.decomposition import run_decomposition
    from agents.rag import run_rag
    from agents.critique import run_critique
    from agents.synthesis import run_synthesis

    agent_map = {
        "decomposition": run_decomposition,
        "rag": run_rag,
        "critique": run_critique,
        "synthesis": run_synthesis,
    }

    for step in plan["routing_plan"]:
        agent_name = step["agent"]
        if stream_callback:
            stream_callback({"agent": agent_name, "event": "start", "data": f"Starting {agent_name}...", "budget_remaining": budget.remaining(agent_name)})

        fn = agent_map.get(agent_name)
        if fn:
            context = fn(context, stream_callback=stream_callback)
        else:
            log.warning("unknown_agent", agent=agent_name)

    return context