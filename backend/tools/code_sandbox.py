import subprocess, time, textwrap

FAILURE_CONTRACT = {
    "timeout":   {"stdout": "", "stderr": "SANDBOX_TIMEOUT", "exit_code": -1},
    "empty":     {"stdout": "", "stderr": "NO_CODE_PROVIDED", "exit_code": -1},
    "malformed": {"stdout": "", "stderr": "MALFORMED_INPUT",  "exit_code": -1},
}

TIMEOUT_SECONDS = 10
BLOCKED = ["import os", "import sys", "open(", "__import__", "exec(", "eval("]

def run_code(code: str) -> dict:
    start = time.time()
    if not code or not isinstance(code, str):
        return {**FAILURE_CONTRACT["malformed"], "latency_ms": 0}
    code = textwrap.dedent(code).strip()
    if not code:
        return {**FAILURE_CONTRACT["empty"], "latency_ms": 0}

    # Basic safety: block dangerous imports
    for blocked in BLOCKED:
        if blocked in code:
            return {"stdout": "", "stderr": f"BLOCKED: {blocked} not allowed",
                    "exit_code": 1, "latency_ms": 0}
    try:
        result = subprocess.run(
            ["python3", "-c", code],
            capture_output=True, text=True, timeout=TIMEOUT_SECONDS
        )
        latency = (time.time() - start) * 1000
        return {"stdout": result.stdout[:2000], "stderr": result.stderr[:500],
                "exit_code": result.returncode, "latency_ms": latency}
    except subprocess.TimeoutExpired:
        return {**FAILURE_CONTRACT["timeout"], "latency_ms": TIMEOUT_SECONDS * 1000}