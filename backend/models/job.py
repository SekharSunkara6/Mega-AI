import uuid
from datetime import datetime
from sqlalchemy import String, Float, Integer, Text, JSON, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database import Base

class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    query: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, default="pending")  # pending|running|done|failed
    final_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    provenance_map: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    logs: Mapped[list["AgentLog"]] = relationship(back_populates="job", order_by="AgentLog.created_at")
    tool_calls: Mapped[list["ToolLog"]] = relationship(back_populates="job")

class AgentLog(Base):
    __tablename__ = "agent_logs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"))
    agent_id: Mapped[str] = mapped_column(String)
    event_type: Mapped[str] = mapped_column(String)   # start|output|handoff|budget_violation|end
    input_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    output_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    input_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    output_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    policy_violation: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    job: Mapped["Job"] = relationship(back_populates="logs")

class ToolLog(Base):
    __tablename__ = "tool_logs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"))
    agent_id: Mapped[str] = mapped_column(String)
    tool_name: Mapped[str] = mapped_column(String)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    input_data: Mapped[dict] = mapped_column(JSON)
    output_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    accepted: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    job: Mapped["Job"] = relationship(back_populates="tool_calls")