import uuid
from datetime import datetime
from sqlalchemy import String, Float, Integer, Text, JSON, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database import Base

class EvalRun(Base):
    __tablename__ = "eval_runs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    trigger: Mapped[str] = mapped_column(String, default="manual")  # manual|rerun
    summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    results: Mapped[list["EvalResult"]] = relationship(back_populates="run")

class EvalResult(Base):
    __tablename__ = "eval_results"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id: Mapped[str] = mapped_column(ForeignKey("eval_runs.id"))
    test_case_id: Mapped[str] = mapped_column(String)
    category: Mapped[str] = mapped_column(String)  # baseline|ambiguous|adversarial
    query: Mapped[str] = mapped_column(Text)
    final_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Scores — each is 0.0–1.0
    correctness_score: Mapped[float] = mapped_column(Float, default=0.0)
    correctness_justification: Mapped[str] = mapped_column(Text, default="")
    citation_score: Mapped[float] = mapped_column(Float, default=0.0)
    citation_justification: Mapped[str] = mapped_column(Text, default="")
    contradiction_score: Mapped[float] = mapped_column(Float, default=0.0)
    contradiction_justification: Mapped[str] = mapped_column(Text, default="")
    tool_efficiency_score: Mapped[float] = mapped_column(Float, default=0.0)
    tool_efficiency_justification: Mapped[str] = mapped_column(Text, default="")
    budget_compliance_score: Mapped[float] = mapped_column(Float, default=0.0)
    budget_compliance_justification: Mapped[str] = mapped_column(Text, default="")
    critique_agreement_score: Mapped[float] = mapped_column(Float, default=0.0)
    critique_agreement_justification: Mapped[str] = mapped_column(Text, default="")
    exact_prompts: Mapped[dict] = mapped_column(JSON, default=dict)
    exact_tool_calls: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    run: Mapped["EvalRun"] = relationship(back_populates="results")