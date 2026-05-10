import json
from llm_client import chat, extract_json
from database import SessionLocal
from models.eval import EvalRun, EvalResult
from models.prompt import PromptRewrite
import structlog

log = structlog.get_logger()

META_SYSTEM = """You are a meta-agent that improves prompts by analyzing evaluation failures.

Given failing test cases and their scores, you:
1. Identify the WORST performing agent+dimension combination
2. Propose a rewritten prompt with structured diff
3. Justify the rewrite with specific evidence from failures

Respond ONLY with valid JSON:
{
  "worst_agent": "agent_id",
  "worst_dimension": "correctness|citation|contradiction|tool_efficiency|budget_compliance|critique_agreement",
  "failure_analysis": "specific analysis of why this agent+dimension is failing",
  "original_prompt_excerpt": "the relevant part of the current prompt",
  "proposed_changes": [
    {"type": "add|remove|modify", "location": "where in prompt", "before": "old text", "after": "new text", "reason": "why"}
  ],
  "expected_improvement": "what specific improvement this rewrite should produce",
  "confidence": 0.8
}"""


def run_meta_agent(eval_run_id: str) -> PromptRewrite | None:
    db = SessionLocal()
    try:
        run = db.query(EvalRun).filter(EvalRun.id == eval_run_id).first()
        if not run:
            return None

        results = db.query(EvalResult).filter(EvalResult.run_id == eval_run_id).all()
        if not results:
            return None

        # Find worst dimension
        dim_scores = {
            "correctness": [],
            "citation": [],
            "contradiction": [],
            "tool_efficiency": [],
            "budget_compliance": [],
            "critique_agreement": [],
        }
        for r in results:
            dim_scores["correctness"].append(r.correctness_score)
            dim_scores["citation"].append(r.citation_score)
            dim_scores["contradiction"].append(r.contradiction_score)
            dim_scores["tool_efficiency"].append(r.tool_efficiency_score)
            dim_scores["budget_compliance"].append(r.budget_compliance_score)
            dim_scores["critique_agreement"].append(r.critique_agreement_score)

        avg_scores = {dim: sum(scores)/len(scores) for dim, scores in dim_scores.items() if scores}
        worst_dim = min(avg_scores, key=avg_scores.get)

        # Get failing cases for context
        failing = [r for r in results if getattr(r, f"{worst_dim}_score", 1.0) < 0.5]
        failing_summary = [
            {"query": r.query, "category": r.category,
             "score": getattr(r, f"{worst_dim}_score"),
             "justification": getattr(r, f"{worst_dim}_justification")}
            for r in failing[:5]
        ]

        prompt = f"""Eval run: {eval_run_id}
Worst dimension: {worst_dim} (avg score: {avg_scores[worst_dim]:.2f})
Failing cases:
{json.dumps(failing_summary, indent=2)}

Current agent scores by dimension:
{json.dumps({k: round(v,2) for k,v in avg_scores.items()}, indent=2)}

Propose a prompt rewrite to fix the worst-performing agent."""

        raw = chat(META_SYSTEM, prompt, max_tokens=1200)
        data = json.loads(extract_json(raw))

        # Import current prompt from the identified agent
        agent_prompts = _get_agent_prompts()
        agent_id = data.get("worst_agent", "rag")
        original = agent_prompts.get(agent_id, "")

        rewrite = PromptRewrite(
            eval_run_id=eval_run_id,
            agent_id=agent_id,
            dimension=worst_dim,
            original_prompt=original,
            proposed_prompt=_apply_diff(original, data.get("proposed_changes", [])),
            diff={"changes": data.get("proposed_changes", [])},
            justification=data.get("failure_analysis", ""),
            status="pending",
        )
        db.add(rewrite)
        db.commit()
        db.refresh(rewrite)
        log.info("meta_rewrite_proposed", agent=agent_id, dimension=worst_dim)
        return rewrite

    except Exception as e:
        log.error("meta_agent_error", error=str(e))
        return None
    finally:
        db.close()


def _get_agent_prompts() -> dict[str, str]:
    """Return current system prompts for each agent."""
    from agents.orchestrator import ORCHESTRATOR_SYSTEM
    from agents.decomposition import DECOMPOSITION_SYSTEM
    from agents.rag import RAG_SYSTEM
    from agents.critique import CRITIQUE_SYSTEM
    from agents.synthesis import SYNTHESIS_SYSTEM
    return {
        "orchestrator": ORCHESTRATOR_SYSTEM,
        "decomposition": DECOMPOSITION_SYSTEM,
        "rag": RAG_SYSTEM,
        "critique": CRITIQUE_SYSTEM,
        "synthesis": SYNTHESIS_SYSTEM,
    }


def _apply_diff(original: str, changes: list[dict]) -> str:
    """Apply proposed changes to produce new prompt."""
    result = original
    for change in changes:
        if change.get("type") == "modify" and change.get("before"):
            result = result.replace(change["before"], change.get("after", ""))
        elif change.get("type") == "add":
            result += f"\n\nADDED: {change.get('after', '')}"
        elif change.get("type") == "remove" and change.get("before"):
            result = result.replace(change["before"], "")
    return result