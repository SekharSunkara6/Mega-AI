import uuid
from datetime import datetime
from sqlalchemy import String, Text, JSON, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database import Base

class PromptRewrite(Base):
    __tablename__ = "prompt_rewrites"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    eval_run_id: Mapped[str] = mapped_column(String)
    agent_id: Mapped[str] = mapped_column(String)
    dimension: Mapped[str] = mapped_column(String)   # which scoring dim was worst
    original_prompt: Mapped[str] = mapped_column(Text)
    proposed_prompt: Mapped[str] = mapped_column(Text)
    diff: Mapped[dict] = mapped_column(JSON)         # structured diff
    justification: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, default="pending")  # pending|approved|rejected
    delta: Mapped[dict | None] = mapped_column(JSON, nullable=True) # perf delta after rerun
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)