import json, time
from llm_client import chat, extract_json
from schemas.context import SharedContext, AgentOutput, CritiqueResult, ClaimScore
from core.context_manager import ContextBudgetManager
import structlog

log = structlog.get_logger()

CRITIQUE_SYSTEM = """You are a critique agent. Your job is to review agent outputs and score individual claims — NOT the output as a whole.

You MUST flag specific text spans you disagree with, not just give an overall rating.

Respond ONLY with valid JSON:
{
  "reviews": [
    {
      "agent_reviewed": "rag",
      "claim_scores": [
        {
          "span": "exact text span from the output",
          "confidence": 0.95,
          "flag": null
        },
        {
          "span": "another claim that seems wrong",
          "confidence": 0.3,
          "flag": "This claim is unsubstantiated — no citation supports it"
        }
      ],
      "overall_confidence": 0.75,
      "summary": "brief overall assessment"
    }
  ],
  "contradictions_found": [
    {
      "span_a": "claim from agent X",
      "span_b": "contradicting claim from agent Y",
      "agents": ["rag", "decomposition"],
      "severity": "high|medium|low"
    }
  ]
}

Rules:
- Confidence < 0.5 means the claim should be flagged
- You MUST check for contradictions between different agents
- Be specific — cite the exact span of text you're critiquing
- Do not flag things just to seem thorough — only flag genuine concerns"""


def run_critique(context: SharedContext, stream_callback=None) -> SharedContext:
    budget = ContextBudgetManager(context)

    # Gather all prior agent outputs to review
    outputs_to_review = {
        aid: str(out.content)[:800]
        for aid, out in context.agent_outputs.items()
        if aid not in ("orchestrator", "critique")
    }

    if not outputs_to_review:
        log.warning("critique_no_outputs")
        return context

    prompt = f"""Original query: {context.original_query}

Agent outputs to critique:
{json.dumps(outputs_to_review, indent=2)}

Review each agent's output at the claim level. Flag specific spans. Check for contradictions between agents."""

    fits, needed = budget.check_budget("critique", prompt)
    if not fits:
        context.policy_violations.append(f"critique: budget exceeded ({needed} tokens)")
        return context

    budget.consume("critique", prompt)
    start = time.time()

    try:
        raw = chat(CRITIQUE_SYSTEM, prompt, max_tokens=1500)
        data = json.loads(extract_json(raw))

        critique_results = []
        for review in data.get("reviews", []):
            claim_scores = [
                ClaimScore(
                    span=cs["span"],
                    confidence=cs["confidence"],
                    flag=cs.get("flag")
                )
                for cs in review.get("claim_scores", [])
            ]
            critique_results.append(CritiqueResult(
                agent_reviewed=review["agent_reviewed"],
                claim_scores=claim_scores,
                overall_confidence=review.get("overall_confidence", 0.5)
            ))

        context.critique_results = critique_results
        context.metadata["contradictions"] = data.get("contradictions_found", [])

    except Exception as e:
        log.error("critique_error", error=str(e))
        data = {"reviews": [], "contradictions_found": []}

    latency = (time.time() - start) * 1000
    flagged = sum(
        1 for cr in context.critique_results
        for cs in cr.claim_scores if cs.flag
    )

    context.agent_outputs["critique"] = AgentOutput(
        agent_id="critique",
        content=data,
        token_count=needed,
    )

    if stream_callback:
        stream_callback({
            "agent": "critique",
            "event": "output",
            "data": f"Reviewed {len(context.critique_results)} agents. Flagged {flagged} claims.",
            "flagged_claims": flagged,
            "contradictions": len(context.metadata.get("contradictions", [])),
            "budget_remaining": budget.remaining("critique")
        })

    log.info("critique_done", flagged=flagged, latency_ms=latency)
    return context