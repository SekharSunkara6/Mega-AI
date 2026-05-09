import time, hashlib, json
from typing import Callable, Any
from database import SessionLocal
from models.job import ToolLog
import structlog

log = structlog.get_logger()
MAX_RETRIES = 2

def execute_tool(
    job_id: str,
    agent_id: str,
    tool_name: str,
    tool_fn: Callable,
    tool_input: dict,
    accept_fn: Callable[[dict], bool] | None = None,
) -> dict[str, Any]:
    """
    Run a tool with up to MAX_RETRIES retries.
    accept_fn: given the tool output, returns True if agent accepts it.
    Each attempt is logged separately.
    """
    db = SessionLocal()
    last_result = {}

    for attempt in range(1, MAX_RETRIES + 2):
        start = time.time()
        try:
            result = tool_fn(**tool_input)
        except Exception as e:
            result = {"error": f"EXCEPTION:{e}", "rows": [], "results": []}

        latency = (time.time() - start) * 1000
        accepted = accept_fn(result) if accept_fn else (result.get("error") is None)

        tlog = ToolLog(
            job_id=job_id, agent_id=agent_id,
            tool_name=tool_name, attempt=attempt,
            input_data=tool_input, output_data=result,
            latency_ms=latency, accepted=accepted,
            failure_reason=result.get("error") if not accepted else None,
        )
        db.add(tlog)
        db.commit()

        log.info("tool_call", tool=tool_name, attempt=attempt,
                 accepted=accepted, latency=latency)

        if accepted:
            db.close()
            return result

        if attempt <= MAX_RETRIES:
            # Modify input for retry: append retry hint
            tool_input = {**tool_input, "_retry": attempt}
            log.warning("tool_retry", tool=tool_name, attempt=attempt)

        last_result = result

    db.close()
    log.error("tool_exhausted", tool=tool_name, last_error=last_result.get("error"))
    return last_result  # Orchestrator must handle this failure