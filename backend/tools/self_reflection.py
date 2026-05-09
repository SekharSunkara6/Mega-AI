import time
from schemas.context import SharedContext

FAILURE_CONTRACT = {
    "empty":     {"contradictions": [], "summary": "No prior outputs found."},
    "malformed": {"contradictions": [], "summary": "Invalid context provided."},
}

def self_reflect(context: SharedContext, agent_id: str) -> dict:
    start = time.time()
    if not context:
        return {**FAILURE_CONTRACT["malformed"], "latency_ms": 0}

    prior_outputs = [
        {"agent": aid, "content": str(out.content)[:500]}
        for aid, out in context.agent_outputs.items()
    ]
    if not prior_outputs:
        return {**FAILURE_CONTRACT["empty"], "latency_ms": 0}

    # Simple contradiction detection: look for negations
    contradictions = []
    texts = [o["content"] for o in prior_outputs]
    for i, t1 in enumerate(texts):
        for j, t2 in enumerate(texts):
            if i >= j:
                continue
            words1 = set(t1.lower().split())
            words2 = set(t2.lower().split())
            negations = {"not", "never", "no", "cannot", "false"}
            if words1 & negations and (words1 & words2 - negations):
                contradictions.append({
                    "agents": [prior_outputs[i]["agent"], prior_outputs[j]["agent"]],
                    "hint": "Potential negation conflict detected"
                })

    latency = (time.time() - start) * 1000
    return {
        "prior_outputs": prior_outputs,
        "contradictions": contradictions,
        "summary": f"Reviewed {len(prior_outputs)} agent outputs. Found {len(contradictions)} potential contradictions.",
        "latency_ms": latency,
    }