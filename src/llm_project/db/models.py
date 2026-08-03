from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from llm_project.config import POSTGRES_URL


class Base(DeclarativeBase):
    pass


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    question: Mapped[str] = mapped_column(Text)
    search_query: Mapped[str] = mapped_column(Text, nullable=True)
    answer: Mapped[str] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(String)  # "rag" or "agent"
    retrieval_method: Mapped[str] = mapped_column(String, nullable=True)
    prompt_variant: Mapped[str] = mapped_column(String, nullable=True)
    model: Mapped[str] = mapped_column(String)
    response_time_seconds: Mapped[float] = mapped_column(Float)
    num_source_docs: Mapped[int] = mapped_column(Integer)
    source_doc_ids: Mapped[str] = mapped_column(Text, nullable=True)
    session_id: Mapped[str] = mapped_column(String, nullable=True)
    intent: Mapped[str] = mapped_column(String, nullable=True)  # inferred from tools actually called, not classified
    tools_called: Mapped[str] = mapped_column(Text, nullable=True)  # comma-separated tool names
    tool_success: Mapped[bool] = mapped_column(Boolean, nullable=True)  # null: no tools were called
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=True)
    estimated_cost: Mapped[float] = mapped_column(Float, nullable=True)  # USD, from toyaikit's pricing table
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(String)
    rating: Mapped[int] = mapped_column(Integer)  # +1 (up) or -1 (down)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


_engine = None
_session_factory = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(POSTGRES_URL)
    return _engine


_NEW_CONVERSATION_COLUMNS = (
    ("session_id", "VARCHAR"),
    ("intent", "VARCHAR"),
    ("tools_called", "TEXT"),
    ("tool_success", "BOOLEAN"),
    ("prompt_tokens", "INTEGER"),
    ("completion_tokens", "INTEGER"),
    ("estimated_cost", "FLOAT"),
)


def _migrate_conversations_table(engine) -> None:
    """`Base.metadata.create_all` only creates missing tables, it does not
    alter existing ones - so columns added to Conversation after the table
    already existed (from earlier runs) need an explicit, idempotent
    ADD COLUMN IF NOT EXISTS. No Alembic in this project; this is deliberately
    a small, additive-only migration rather than pulling in a migration
    framework for one table."""
    with engine.begin() as conn:
        for column_name, column_type in _NEW_CONVERSATION_COLUMNS:
            conn.execute(text(f"ALTER TABLE conversations ADD COLUMN IF NOT EXISTS {column_name} {column_type}"))


def init_db() -> None:
    from llm_project.db import nhs_schema  # noqa: F401  (registers its tables on Base.metadata)

    engine = get_engine()
    Base.metadata.create_all(engine)
    _migrate_conversations_table(engine)


def get_session():
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine())
    return _session_factory()
