import tiktoken
from schemas.context import SharedContext
import structlog

log = structlog.get_logger()

AGENT_BUDGETS = {
    "orchestrator":   8000,
    "decomposition":  4000,
    "rag":            6000,
    "critique":       4000,
    "synthesis":      6000,
    "compression":    3000,
    "meta":           4000,
}

enc = tiktoken.get_encoding("cl100k_base")

def count_tokens(text: str) -> int:
    return len(enc.encode(text))

class ContextBudgetManager:
    def __init__(self, context: SharedContext):
        self.context = context
        for agent_id, budget in AGENT_BUDGETS.items():
            if agent_id not in context.budget_remaining:
                context.budget_remaining[agent_id] = budget

    def check_budget(self, agent_id: str, text: str) -> tuple[bool, int]:
        """Returns (fits, tokens_needed). Call before adding to context."""
        needed = count_tokens(text)
        remaining = self.context.budget_remaining.get(agent_id, 0)
        return (needed <= remaining, needed)

    def consume(self, agent_id: str, text: str) -> bool:
        """Consume budget. Returns False and logs violation if exceeded."""
        fits, needed = self.check_budget(agent_id, text)
        if not fits:
            violation = f"{agent_id} attempted to use {needed} tokens but only {self.context.budget_remaining.get(agent_id,0)} remain"
            self.context.policy_violations.append(violation)
            log.error("budget_violation", agent=agent_id, needed=needed,
                      remaining=self.context.budget_remaining.get(agent_id, 0))
            return False
        self.context.budget_remaining[agent_id] -= needed
        return True

    def remaining(self, agent_id: str) -> int:
        return self.context.budget_remaining.get(agent_id, 0)