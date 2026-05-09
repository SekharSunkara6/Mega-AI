import json, hashlib
from datetime import datetime
from celery import Celery
from config import settings
from database import SessionLocal
from models.job import Job, AgentLog
from schemas.context import SharedContext
import structlog

log = structlog.get_logger()

celery_app = Celery("mega_ai", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.task_serializer = "json"
celery_app.conf.result_serializer = "json"


def _publish(redis_client, job_id: str, event: str, data: dict):
    """Push SSE event to Redis pub/sub channel."""
    payload = json.dumps({"event": event, **data})
    redis_client.publish(f"job:{job_id}", payload)


def _log_agent(db, job_id: str, agent_id: str, event_type: str,
               input_data=None, output_data=None, token_count=0, latency_ms=0.0,
               policy_violation=None):
    def _hash(d): return hashlib.sha256(json.dumps(d, default=str).encode()).hexdigest()[:12] if d else None
    entry = AgentLog(
        job_id=job_id, agent_id=agent_id, event_type=event_type,
        input_hash=_hash(input_data), output_hash=_hash(output_data),
        input_data=input_data, output_data=output_data,
        token_count=token_count, latency_ms=latency_ms,
        policy_violation=policy_violation,
    )
    db.add(entry)
    db.commit()


@celery_app.task(name="process_job")
def process_job_task(job_id: str, query: str):
    import redis as syncredis
    r = syncredis.from_url(settings.redis_url)
    db = SessionLocal()

    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        job.status = "running"
        db.commit()

        context = SharedContext(job_id=job_id, original_query=query)

        def stream_callback(event_data: dict):
            agent = event_data.get("agent", "system")
            event = event_data.get("event", "update")
            _publish(r, job_id, event, event_data)
            _log_agent(
                db, job_id, agent, event,
                output_data=event_data,
                token_count=0,
            )

        # Run the full pipeline
        from agents.orchestrator import run_orchestrator
        context = run_orchestrator(context, stream_callback=stream_callback)

        # Save results
        job.status = "done"
        job.final_answer = context.final_answer
        job.provenance_map = [p.model_dump() for p in context.provenance_map]
        job.completed_at = datetime.utcnow()
        db.commit()

        # Log any policy violations
        for violation in context.policy_violations:
            _log_agent(db, job_id, "system", "policy_violation",
                       output_data={"violation": violation}, policy_violation=violation)

        _publish(r, job_id, "job_complete", {
            "job_id": job_id,
            "final_answer": context.final_answer,
            "provenance_entries": len(context.provenance_map),
            "policy_violations": context.policy_violations,
            "budget_remaining": context.budget_remaining,
        })

        log.info("job_complete", job_id=job_id)

    except Exception as e:
        log.error("job_failed", job_id=job_id, error=str(e))
        job = db.query(Job).filter(Job.id == job_id).first()
        if job:
            job.status = "failed"
            db.commit()
        _publish(r, job_id, "job_failed", {"job_id": job_id, "error": str(e)})
    finally:
        db.close()
        r.close()


@celery_app.task(name="run_eval")
def run_eval_task(trigger: str = "manual", failed_ids: list = None, rewrite_id: str = None):
    from eval.harness import run_eval
    run_eval(trigger=trigger, failed_ids=failed_ids or [], rewrite_id=rewrite_id)