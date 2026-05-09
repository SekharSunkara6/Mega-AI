from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field
import hashlib, json

class SubTask(BaseModel):
    id: str
    description: str
    type: str                          # research|code|analysis|synthesis
    dependencies: list[str] = []       # ids of tasks that must finish first
    status: str = "pending"            # pending|running|done|failed
    result: Any = None

class ChunkCitation(BaseModel):
    chunk_id: str
    source: str
    text: str
    relevance_score: float

class AgentOutput(BaseModel):
    agent_id: str
    content: Any
    citations: list[ChunkCitation] = []
    confidence: float = 1.0
    token_count: int = 0

class ClaimScore(BaseModel):
    span: str                          # the exact text span
    confidence: float
    flag: str | None = None            # disagreement reason if flagged

class CritiqueResult(BaseModel):
    agent_reviewed: str
    claim_scores: list[ClaimScore]
    overall_confidence: float

class ProvenanceEntry(BaseModel):
    sentence: str
    source_agent: str
    source_chunk_id: str | None = None

class SharedContext(BaseModel):
    job_id: str
    original_query: str
    sub_tasks: list[SubTask] = []
    agent_outputs: dict[str, AgentOutput] = {}
    critique_results: list[CritiqueResult] = []
    provenance_map: list[ProvenanceEntry] = []
    tool_call_log: list[dict] = []
    budget_remaining: dict[str, int] = {}   # agent_id -> tokens left
    policy_violations: list[str] = []
    final_answer: str | None = None
    metadata: dict = {}

    def to_hash(self) -> str:
        return hashlib.sha256(
            json.dumps(self.model_dump(), sort_keys=True, default=str).encode()
        ).hexdigest()[:12]