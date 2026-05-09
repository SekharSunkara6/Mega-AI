import uuid
from datetime import datetime
from database import SessionLocal
from models.eval import EvalRun, EvalResult
from models.prompt import PromptRewrite
from schemas.context import SharedContext
from eval.test_cases import TEST_CASES, TestCase
from eval.scoring import score_all
from agents.orchestrator import run_orchestrator
from agents.meta import run_meta_agent
import structlog

log = structlog.get_logger()


def run_eval(trigger: str = "manual", failed_ids: list = None, rewrite_id: str = None):
    db = SessionLocal()
    run_id = str(uuid.uuid4())
    run = EvalRun(id=run_id, trigger=trigger)
    db.add(run)
    db.commit()
    log.info("eval_run_started", run_id=run_id, trigger=trigger)

    cases = TEST_CASES
    if failed_ids:
        cases = [tc for tc in TEST_CASES if tc.id in failed_ids]

    results = []
    for tc in cases:
        log.info("eval_case", id=tc.id, category=tc.category)
        context = SharedContext(job_id=str(uuid.uuid4()), original_query=tc.query)

        try:
            context = run_orchestrator(context)
            final_answer = context.final_answer or ""
        except Exception as e:
            log.error("eval_case_error", id=tc.id, error=str(e))
            final_answer = ""

        scores = score_all(tc, context, final_answer)

        result = EvalResult(
            run_id=run_id,
            test_case_id=tc.id,
            category=tc.category,
            query=tc.query,
            final_answer=final_answer[:1000],
            exact_prompts={
                aid: str(out.content)[:300]
                for aid, out in context.agent_outputs.items()
            },
            exact_tool_calls=context.tool_call_log[:10],
            **scores,
        )
        db.add(result)
        db.commit()
        results.append(result)
        log.info("eval_case_done", id=tc.id, correctness=scores["correctness_score"])

    # Build summary
    def avg(vals): return round(sum(vals)/len(vals), 3) if vals else 0
    dims = ["correctness", "citation", "contradiction", "tool_efficiency", "budget_compliance", "critique_agreement"]
    summary = {
        "overall": {d: avg([getattr(r, f"{d}_score") for r in results]) for d in dims},
        "by_category": {},
        "total_cases": len(results),
        "run_id": run_id,
    }
    for cat in ["baseline", "ambiguous", "adversarial"]:
        cat_r = [r for r in results if r.category == cat]
        if cat_r:
            summary["by_category"][cat] = {
                d: avg([getattr(r, f"{d}_score") for r in cat_r]) for d in dims
            }

    run.summary = summary
    db.commit()
    log.info("eval_run_complete", run_id=run_id, summary=summary["overall"])

    # Trigger meta-agent to propose improvements
    run_meta_agent(run_id)

    db.close()
    return run_id