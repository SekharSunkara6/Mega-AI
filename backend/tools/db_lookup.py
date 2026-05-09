import time, re
from sqlalchemy import text
from database import SessionLocal

FAILURE_CONTRACT = {
    "timeout":   {"rows": [], "error": "DB_TIMEOUT",    "sql": None},
    "empty":     {"rows": [], "error": "NO_QUERY",      "sql": None},
    "malformed": {"rows": [], "error": "INVALID_QUERY", "sql": None},
}

ALLOWED_TABLES = {"eval_runs", "eval_results", "jobs", "agent_logs", "tool_logs"}

def nl_to_sql(natural_language: str) -> str:
    """Simple rule-based NL→SQL. In prod, use an LLM call here."""
    nl = natural_language.lower()
    if "eval" in nl and "latest" in nl:
        return "SELECT * FROM eval_runs ORDER BY created_at DESC LIMIT 5"
    if "job" in nl and "fail" in nl:
        return "SELECT * FROM jobs WHERE status='failed' ORDER BY created_at DESC LIMIT 10"
    if "tool" in nl and "slow" in nl:
        return "SELECT tool_name, AVG(latency_ms) as avg_ms FROM tool_logs GROUP BY tool_name ORDER BY avg_ms DESC"
    if "violation" in nl:
        return "SELECT * FROM agent_logs WHERE policy_violation IS NOT NULL ORDER BY created_at DESC LIMIT 20"
    return "SELECT * FROM jobs ORDER BY created_at DESC LIMIT 10"

def db_lookup(natural_language: str) -> dict:
    start = time.time()
    if not natural_language:
        return {**FAILURE_CONTRACT["empty"], "latency_ms": 0}
    try:
        sql = nl_to_sql(natural_language)
        db = SessionLocal()
        rows = db.execute(text(sql)).mappings().all()
        db.close()
        latency = (time.time() - start) * 1000
        return {"rows": [dict(r) for r in rows], "error": None,
                "sql": sql, "latency_ms": latency}
    except Exception as e:
        return {**FAILURE_CONTRACT["malformed"], "latency_ms": 0, "detail": str(e)}