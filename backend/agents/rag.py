import json, time
from anthropic import Anthropic
from config import settings
from schemas.context import SharedContext, AgentOutput, ChunkCitation
from core.context_manager import ContextBudgetManager
from core.tool_executor import execute_tool
from tools.web_search import web_search
import structlog

log = structlog.get_logger()
client = Anthropic(api_key=settings.anthropic_api_key)

RAG_SYSTEM = """You are a retrieval-augmented reasoning agent. You perform multi-hop reasoning across retrieved chunks.

CRITICAL RULES:
1. You MUST retrieve at least 2 chunks before forming any answer
2. Each part of your answer MUST cite which chunk it came from
3. Single-hop retrieval is NOT sufficient — you must reason across multiple sources
4. If chunks contradict each other, note the contradiction explicitly

Respond ONLY with valid JSON:
{
  "hop1_query": "first retrieval query",
  "hop1_findings": "what you found in hop 1",
  "hop1_chunk_id": "chunk_001",
  "hop2_query": "follow-up query based on hop 1 findings",
  "hop2_findings": "what you found in hop 2",
  "hop2_chunk_id": "chunk_002",
  "reasoning_chain": "how hop1 + hop2 together answer the question",
  "answer": "final answer with inline citations like [chunk_001] and [chunk_002]",
  "citations": [
    {"chunk_id": "chunk_001", "source": "url or source name", "text": "relevant excerpt", "relevance_score": 0.9, "contributed_to": "which part of answer"},
    {"chunk_id": "chunk_002", "source": "url or source name", "text": "relevant excerpt", "relevance_score": 0.8, "contributed_to": "which part of answer"}
  ]
}"""


def run_rag(context: SharedContext, stream_callback=None) -> SharedContext:
    budget = ContextBudgetManager(context)

    # Build prompt from sub-tasks if available
    tasks_text = ""
    if context.sub_tasks:
        tasks_text = "\n".join([f"- [{t.type}] {t.description}" for t in context.sub_tasks])

    prompt = f"""Original query: {context.original_query}

Sub-tasks to address:
{tasks_text or 'Address the query directly'}

Perform multi-hop retrieval reasoning. You MUST make at least 2 retrieval hops."""

    fits, needed = budget.check_budget("rag", prompt)
    if not fits:
        context.policy_violations.append(f"rag: budget exceeded ({needed} tokens needed)")
        return context

    budget.consume("rag", prompt)
    start = time.time()

    # Execute web search tool — hop 1
    hop1_result = execute_tool(
        job_id=context.job_id,
        agent_id="rag",
        tool_name="web_search",
        tool_fn=web_search,
        tool_input={"query": context.original_query, "max_results": 3},
        accept_fn=lambda r: r.get("error") is None and len(r.get("results", [])) > 0
    )

    # Build hop 2 query from hop 1 results
    hop1_snippets = " ".join([r.get("snippet", "") for r in hop1_result.get("results", [])])
    hop2_query = f"{context.original_query} — detailed analysis"

    hop2_result = execute_tool(
        job_id=context.job_id,
        agent_id="rag",
        tool_name="web_search",
        tool_fn=web_search,
        tool_input={"query": hop2_query, "max_results": 3},
        accept_fn=lambda r: r.get("error") is None
    )

    # Build context for LLM with both hops
    retrieval_context = f"""
HOP 1 RESULTS (query: {context.original_query}):
{json.dumps(hop1_result.get('results', []), indent=2)}

HOP 2 RESULTS (query: {hop2_query}):
{json.dumps(hop2_result.get('results', []), indent=2)}
"""

    full_prompt = f"{prompt}\n\nRetrieved chunks:\n{retrieval_context}"

    # Check budget for full prompt
    fits2, needed2 = budget.check_budget("rag", full_prompt)
    if not fits2:
        context.policy_violations.append(f"rag: retrieval context too large ({needed2} tokens)")
        # Use compressed version
        full_prompt = prompt + f"\n\nRetrieval summary: {hop1_snippets[:500]}"

    budget.consume("rag", full_prompt)

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            system=RAG_SYSTEM,
            messages=[{"role": "user", "content": full_prompt}]
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw.strip())

        citations = [
            ChunkCitation(
                chunk_id=c["chunk_id"],
                source=c.get("source", "web"),
                text=c.get("text", ""),
                relevance_score=c.get("relevance_score", 0.5)
            )
            for c in data.get("citations", [])
        ]

    except Exception as e:
        log.error("rag_error", error=str(e))
        data = {"answer": f"RAG agent encountered an error: {e}", "citations": [], "reasoning_chain": "error"}
        citations = []

    latency = (time.time() - start) * 1000
    context.agent_outputs["rag"] = AgentOutput(
        agent_id="rag",
        content=data,
        citations=citations,
        token_count=needed + needed2,
    )

    if stream_callback:
        stream_callback({
            "agent": "rag",
            "event": "output",
            "data": data.get("answer", "")[:200],
            "hops": 2,
            "citations": len(citations),
            "budget_remaining": budget.remaining("rag")
        })

    log.info("rag_done", citations=len(citations), latency_ms=latency)
    return context