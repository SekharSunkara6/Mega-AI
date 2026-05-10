import uuid, json, asyncio
from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.orm import Session

from config import settings
from database import get_db, engine, Base
from models.job import Job, AgentLog, ToolLog
from models.eval import EvalRun, EvalResult
from models.prompt import PromptRewrite
from schemas.api import QueryRequest, ApprovalRequest, ErrorResponse
from schemas.context import SharedContext
from worker import process_job_task
import structlog

log = structlog.get_logger()

# Create all tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Mega AI — Multi-Agent Orchestration System",
    description="Production-grade multi-agent LLM system with self-improving eval loop",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── ENDPOINT 1: Submit query → SSE stream ────────────────────────────────────

@app.post("/query", summary="Submit a query and receive SSE stream of agent activity")
async def submit_query(req: QueryRequest, db: Session = Depends(get_db)):
    if not req.query or not req.query.strip():
        raise HTTPException(status_code=400, detail=ErrorResponse(
            error_code="EMPTY_QUERY",
            message="Query cannot be empty",
        ).model_dump())

    job_id = str(uuid.uuid4())
    job = Job(id=job_id, query=req.query, status="pending")
    db.add(job)
    db.commit()

    log.info("job_created", job_id=job_id, query=req.query[:80])

    async def event_generator():
        yield {"event": "job_started", "data": json.dumps({
            "job_id": job_id,
            "query": req.query,
            "message": "Pipeline started"
        })}

        from agents.orchestrator import run_orchestrator
        from schemas.context import SharedContext

        context = SharedContext(job_id=job_id, original_query=req.query)
        collected_events = []

        def sync_callback(event_data: dict):
            collected_events.append(event_data)

        import concurrent.futures
        import asyncio

        loop = asyncio.get_event_loop()
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

        future = loop.run_in_executor(
            executor,
            lambda: run_orchestrator(context, stream_callback=sync_callback)
        )

        # Keep streaming events while pipeline runs
        last_sent = 0
        while not future.done():
            await asyncio.sleep(0.3)
            while last_sent < len(collected_events):
                event = collected_events[last_sent]
                last_sent += 1
                yield {
                    "event": event.get("event", "agent_update"),
                    "data": json.dumps(event)
                }
            # Send heartbeat to keep connection alive
            yield {
                "event": "heartbeat",
                "data": json.dumps({"status": "running"})
            }

        # Flush remaining events
        try:
            final_context = await future
        except Exception as e:
            yield {"event": "job_failed", "data": json.dumps({
                "job_id": job_id, "error": str(e)
            })}
            job.status = "failed"
            db.commit()
            return

        while last_sent < len(collected_events):
            event = collected_events[last_sent]
            last_sent += 1
            yield {
                "event": event.get("event", "agent_update"),
                "data": json.dumps(event)
            }

        # Save to DB
        try:
            job.status = "done"
            job.final_answer = final_context.final_answer
            job.provenance_map = [p.model_dump() for p in final_context.provenance_map]
            job.completed_at = datetime.utcnow()
            db.commit()
        except Exception as e:
            log.error("db_save_error", error=str(e))

        yield {"event": "job_complete", "data": json.dumps({
            "job_id": job_id,
            "final_answer": final_context.final_answer,
            "provenance_entries": len(final_context.provenance_map),
            "policy_violations": final_context.policy_violations,
            "budget_remaining": final_context.budget_remaining,
        })}

    return EventSourceResponse(event_generator(), ping=15)

# ─── ENDPOINT 2: Get full execution trace ─────────────────────────────────────

@app.get("/trace/{job_id}", summary="Retrieve full execution trace for a completed job")
def get_trace(job_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail=ErrorResponse(
            error_code="JOB_NOT_FOUND",
            message=f"No job found with id {job_id}",
            job_id=job_id,
        ).model_dump())

    agent_logs = db.query(AgentLog).filter(AgentLog.job_id == job_id).order_by(AgentLog.created_at).all()
    tool_logs  = db.query(ToolLog).filter(ToolLog.job_id == job_id).order_by(ToolLog.created_at).all()

    # Reconstruct timeline in order
    timeline = []
    for al in agent_logs:
        timeline.append({
            "type": "agent",
            "timestamp": al.created_at.isoformat(),
            "agent_id": al.agent_id,
            "event_type": al.event_type,
            "input_hash": al.input_hash,
            "output_hash": al.output_hash,
            "token_count": al.token_count,
            "latency_ms": al.latency_ms,
            "policy_violation": al.policy_violation,
            "output_preview": str(al.output_data)[:200] if al.output_data else None,
        })
    for tl in tool_logs:
        timeline.append({
            "type": "tool",
            "timestamp": tl.created_at.isoformat(),
            "agent_id": tl.agent_id,
            "tool_name": tl.tool_name,
            "attempt": tl.attempt,
            "latency_ms": tl.latency_ms,
            "accepted": tl.accepted,
            "failure_reason": tl.failure_reason,
            "input_preview": str(tl.input_data)[:100] if tl.input_data else None,
        })

    timeline.sort(key=lambda x: x["timestamp"])

    return {
        "job_id": job_id,
        "query": job.query,
        "status": job.status,
        "final_answer": job.final_answer,
        "provenance_map": job.provenance_map,
        "created_at": job.created_at.isoformat(),
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "timeline": timeline,
        "total_events": len(timeline),
    }


# ─── ENDPOINT 3: Latest eval run summary ──────────────────────────────────────

@app.get("/eval/latest", summary="Get latest eval run summary broken down by category and dimension")
def get_latest_eval(db: Session = Depends(get_db)):
    run = db.query(EvalRun).order_by(EvalRun.created_at.desc()).first()
    if not run:
        raise HTTPException(status_code=404, detail=ErrorResponse(
            error_code="NO_EVAL_RUNS",
            message="No evaluation runs found. POST /eval/run to trigger one.",
        ).model_dump())

    results = db.query(EvalResult).filter(EvalResult.run_id == run.id).all()

    def avg(vals): return round(sum(vals) / len(vals), 3) if vals else 0.0

    dims = ["correctness", "citation", "contradiction", "tool_efficiency", "budget_compliance", "critique_agreement"]
    categories = ["baseline", "ambiguous", "adversarial"]

    by_category = {}
    for cat in categories:
        cat_results = [r for r in results if r.category == cat]
        if not cat_results:
            continue
        by_category[cat] = {
            dim: {
                "score": avg([getattr(r, f"{dim}_score") for r in cat_results]),
                "justifications": [getattr(r, f"{dim}_justification") for r in cat_results[:2]],
            }
            for dim in dims
        }

    overall = {
        dim: avg([getattr(r, f"{dim}_score") for r in results])
        for dim in dims
    }

    return {
        "run_id": run.id,
        "created_at": run.created_at.isoformat(),
        "trigger": run.trigger,
        "total_cases": len(results),
        "overall_scores": overall,
        "by_category": by_category,
        "summary": run.summary,
    }


# ─── ENDPOINT 4: Approve/reject prompt rewrite ────────────────────────────────

@app.post("/eval/rewrite/review", summary="Submit human approval or rejection for a pending prompt rewrite")
def review_rewrite(req: ApprovalRequest, db: Session = Depends(get_db)):
    rewrite = db.query(PromptRewrite).filter(PromptRewrite.id == req.rewrite_id).first()
    if not rewrite:
        raise HTTPException(status_code=404, detail=ErrorResponse(
            error_code="REWRITE_NOT_FOUND",
            message=f"No rewrite found with id {req.rewrite_id}",
        ).model_dump())

    if rewrite.status != "pending":
        raise HTTPException(status_code=409, detail=ErrorResponse(
            error_code="ALREADY_REVIEWED",
            message=f"Rewrite already {rewrite.status}",
        ).model_dump())

    rewrite.status = "approved" if req.approved else "rejected"
    rewrite.reviewed_at = datetime.utcnow()
    db.commit()

    log.info("rewrite_reviewed", rewrite_id=req.rewrite_id, status=rewrite.status)

    return {
        "rewrite_id": req.rewrite_id,
        "status": rewrite.status,
        "agent_id": rewrite.agent_id,
        "dimension": rewrite.dimension,
        "reviewed_at": rewrite.reviewed_at.isoformat(),
        "message": f"Rewrite {'approved — trigger /eval/rerun to test it' if req.approved else 'rejected'}",
    }

@app.post("/eval/run", summary="Trigger a fresh eval run directly")
def trigger_fresh_eval(db: Session = Depends(get_db)):
    import threading
    from eval.harness import run_eval

    def run_in_background():
        try:
            run_eval(trigger="manual")
        except Exception as e:
            log.error("eval_failed", error=str(e))

    thread = threading.Thread(target=run_in_background, daemon=True)
    thread.start()

    return {
        "message": "Eval started in background",
        "status": "running",
        "note": "Click Refresh in 3-5 minutes to see results"
    }

# ─── ENDPOINT 5: Trigger targeted re-eval ─────────────────────────────────────

@app.post("/eval/rerun", summary="Re-run eval on previously failed cases using latest approved prompts")
def trigger_rerun(db: Session = Depends(get_db)):
    from eval.harness import run_eval

    # Get latest approved rewrite
    approved = db.query(PromptRewrite).filter(
        PromptRewrite.status == "approved"
    ).order_by(PromptRewrite.reviewed_at.desc()).first()

    if not approved:
        raise HTTPException(status_code=404, detail=ErrorResponse(
            error_code="NO_APPROVED_REWRITES",
            message="No approved rewrites found. Review a pending rewrite first via /eval/rewrite/review",
        ).model_dump())

    # Get previously failed cases
    last_run = db.query(EvalRun).order_by(EvalRun.created_at.desc()).first()
    failed_ids = []
    if last_run:
        failed_results = db.query(EvalResult).filter(
            EvalResult.run_id == last_run.id,
            EvalResult.correctness_score < 0.5
        ).all()
        failed_ids = [r.test_case_id for r in failed_results]

    from worker import run_eval_task
    task = run_eval_task.delay(trigger="rerun", failed_ids=failed_ids, rewrite_id=approved.id)

    return {
        "message": "Re-eval started",
        "task_id": task.id,
        "rewrite_applied": approved.id,
        "agent": approved.agent_id,
        "failed_cases_count": len(failed_ids),
    }


# ─── Health check ─────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "version": "1.0.0"}


# ─── Serve frontend ───────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def serve_frontend():
    with open("/app/index.html") as f:
        return f.read()