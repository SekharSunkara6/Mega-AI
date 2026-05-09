import json, time
from anthropic import Anthropic
from config import settings
from schemas.context import SharedContext, AgentOutput, ProvenanceEntry
from core.context_manager import ContextBudgetManager
import structlog

log = structlog.get_logger()
client = Anthropic(api_key=settings.anthropic_api_key)

SYNTHESIS_SYSTEM = """You are a synthesis agent. You merge all agent outputs, resolve contradictions flagged by the critique agent, and produce a final answer.

CRITICAL: Every sentence in your answer must have a provenance entry linking it to its source agent and source chunk.

Respond ONLY with valid JSON:
{
  "final_answer": "complete, well-written answer to the original query",
  "contradiction_resolutions": [
    {
      "contradiction": "description of the contradiction",
      "resolution": "how you resolved it and why",
      "resolution_strategy": "chose_higher_confidence|merged|flagged_for_user|used_citation"
    }
  ],
  "provenance_map": [
    {
      "sentence": "exact sentence from final_answer",
      "source_agent": "rag|decomposition|etc",
      "source_chunk_id": "chunk_001 or null"
    }
  ],
  "confidence": 0.85,
  "caveats": ["any remaining uncertainties"]
}"""


def run_synthesis(context: SharedContext, stream_callback=None) -> SharedContext:
    budget = ContextBudgetManager(context)

    # Build comprehensive input
    all_outputs = {
        aid: out.content
        for aid, out in context.agent_outputs.items()
        if aid not in ("orchestrator", "synthesis")
    }
    contradictions = context.metadata.get("contradictions", [])
    flagged_claims = [
        {"agent": cr.agent_reviewed, "span": cs.span, "reason": cs.flag}
        for cr in context.critique_results
        for cs in cr.claim_scores
        if cs.flag
    ]

    prompt = f"""Original query: {context.original_query}

All agent outputs:
{json.dumps(all_outputs, indent=2, default=str)[:2000]}

Contradictions to resolve:
{json.dumps(contradictions, indent=2)}

Flagged claims to address:
{json.dumps(flagged_claims, indent=2)}

Produce the final answer. Resolve ALL contradictions. Map every sentence to its source."""

    fits, needed = budget.check_budget("synthesis", prompt)
    if not fits:
        context.policy_violations.append(f"synthesis: budget exceeded ({needed} tokens)")
        return context

    budget.consume("synthesis", prompt)
    start = time.time()

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            system=SYNTHESIS_SYSTEM,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw.strip())

        context.final_answer = data.get("final_answer", "")
        context.provenance_map = [
            ProvenanceEntry(
                sentence=p["sentence"],
                source_agent=p["source_agent"],
                source_chunk_id=p.get("source_chunk_id")
            )
            for p in data.get("provenance_map", [])
        ]
        context.metadata["contradiction_resolutions"] = data.get("contradiction_resolutions", [])
        context.metadata["synthesis_confidence"] = data.get("confidence", 0.0)
        context.metadata["caveats"] = data.get("caveats", [])

    except Exception as e:
        log.error("synthesis_error", error=str(e))
        # Fallback: concatenate RAG answer
        rag_out = context.agent_outputs.get("rag")
        context.final_answer = str(rag_out.content.get("answer", context.original_query)) if rag_out else f"Unable to synthesize: {e}"

    latency = (time.time() - start) * 1000
    context.agent_outputs["synthesis"] = AgentOutput(
        agent_id="synthesis",
        content={"final_answer": context.final_answer, "provenance_entries": len(context.provenance_map)},
        token_count=needed,
    )

    if stream_callback:
        stream_callback({
            "agent": "synthesis",
            "event": "output",
            "data": context.final_answer,
            "provenance_entries": len(context.provenance_map),
            "resolutions": len(context.metadata.get("contradiction_resolutions", [])),
            "budget_remaining": budget.remaining("synthesis")
        })

    log.info("synthesis_done", answer_len=len(context.final_answer or ""), latency_ms=latency)
    return context