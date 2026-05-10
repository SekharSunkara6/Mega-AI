import json, time
from llm_client import chat, extract_json
from schemas.context import SharedContext, AgentOutput, SubTask
from core.context_manager import ContextBudgetManager
import structlog

log = structlog.get_logger()

DECOMPOSITION_SYSTEM = """You are a decomposition agent. Break the given query into typed sub-tasks with explicit dependency graphs.

Respond ONLY with valid JSON:
{
  "sub_tasks": [
    {
      "id": "t1",
      "description": "specific actionable task description",
      "type": "research|code|analysis|synthesis",
      "dependencies": [],
      "rationale": "why this sub-task is needed"
    },
    {
      "id": "t2",
      "description": "another task",
      "type": "analysis",
      "dependencies": ["t1"],
      "rationale": "depends on t1 because..."
    }
  ],
  "dependency_graph_explanation": "plain English explanation of the execution order"
}

Rules:
- Tasks with dependencies MUST NOT execute until dependencies resolve
- Assign realistic types: research (needs info), code (needs execution), analysis (needs reasoning), synthesis (merges results)
- For simple queries, 2-3 tasks is fine. Complex queries may need 4-5.
- Be specific — vague task descriptions are not acceptable"""


def run_decomposition(context: SharedContext, stream_callback=None) -> SharedContext:
    budget = ContextBudgetManager(context)

    prompt = f"""Query to decompose: {context.original_query}

Orchestrator reasoning: {context.metadata.get('orchestrator_reasoning', 'N/A')}
Complexity: {context.metadata.get('complexity', 'medium')}"""

    fits, needed = budget.check_budget("decomposition", prompt)
    if not fits:
        context.policy_violations.append(f"decomposition: budget exceeded ({needed} tokens needed)")
        return context

    budget.consume("decomposition", prompt)
    start = time.time()

    try:
        raw = chat(DECOMPOSITION_SYSTEM, prompt, max_tokens=1000)
        data = json.loads(extract_json(raw))

        sub_tasks = [
            SubTask(
                id=t["id"],
                description=t["description"],
                type=t["type"],
                dependencies=t.get("dependencies", []),
                status="pending"
            )
            for t in data["sub_tasks"]
        ]

        # Resolve execution order respecting dependencies
        resolved = _topological_sort(sub_tasks)
        for task in resolved:
            task.status = "done"  # Mark as planned/resolved

        context.sub_tasks = resolved

    except Exception as e:
        log.error("decomposition_error", error=str(e))
        # Fallback: single task
        context.sub_tasks = [SubTask(id="t1", description=context.original_query, type="research", dependencies=[], status="done")]
        data = {"dependency_graph_explanation": f"Fallback single task due to: {e}"}

    latency = (time.time() - start) * 1000
    context.agent_outputs["decomposition"] = AgentOutput(
        agent_id="decomposition",
        content={
            "sub_tasks": [t.model_dump() for t in context.sub_tasks],
            "dependency_graph": data.get("dependency_graph_explanation", "")
        },
        token_count=needed,
    )

    if stream_callback:
        stream_callback({
            "agent": "decomposition",
            "event": "output",
            "data": f"Decomposed into {len(context.sub_tasks)} sub-tasks",
            "sub_tasks": [t.model_dump() for t in context.sub_tasks],
            "budget_remaining": budget.remaining("decomposition")
        })

    log.info("decomposition_done", tasks=len(context.sub_tasks), latency_ms=latency)
    return context


def _topological_sort(tasks: list[SubTask]) -> list[SubTask]:
    """Kahn's algorithm — ensures dependent tasks execute after their dependencies."""
    id_map = {t.id: t for t in tasks}
    in_degree = {t.id: 0 for t in tasks}
    for t in tasks:
        for dep in t.dependencies:
            in_degree[t.id] = in_degree.get(t.id, 0) + 1

    queue = [t for t in tasks if in_degree[t.id] == 0]
    result = []
    while queue:
        node = queue.pop(0)
        result.append(node)
        for t in tasks:
            if node.id in t.dependencies:
                in_degree[t.id] -= 1
                if in_degree[t.id] == 0:
                    queue.append(t)
    return result if len(result) == len(tasks) else tasks  # fallback if cycle