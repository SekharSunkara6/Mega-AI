import time, hashlib
from typing import Any

FAILURE_CONTRACT = {
    "timeout": {"results": [], "error": "TIMEOUT", "source_urls": []},
    "empty":   {"results": [], "error": "NO_RESULTS", "source_urls": []},
    "malformed": {"results": [], "error": "MALFORMED_INPUT", "source_urls": []},
}

# Stub data keyed by query hash for deterministic evals
STUB_RESULTS = {
    "default": [
        {"title": "Sample result 1", "url": "https://example.com/1",
         "snippet": "Relevant information about the query topic.",
         "relevance_score": 0.85},
        {"title": "Sample result 2", "url": "https://example.com/2",
         "snippet": "Additional context from a secondary source.",
         "relevance_score": 0.72},
    ]
}

def web_search(query: str, max_results: int = 5) -> dict[str, Any]:
    start = time.time()
    if not query or not isinstance(query, str):
        return {**FAILURE_CONTRACT["malformed"], "latency_ms": 0}
    if len(query.strip()) == 0:
        return {**FAILURE_CONTRACT["empty"], "latency_ms": 0}

    # Use stub — replace with real search API if desired
    key = hashlib.md5(query.encode()).hexdigest()[:6]
    results = STUB_RESULTS.get(key, STUB_RESULTS["default"])[:max_results]

    latency = (time.time() - start) * 1000
    return {
        "results": results,
        "error": None,
        "source_urls": [r["url"] for r in results],
        "query": query,
        "latency_ms": latency,
    }