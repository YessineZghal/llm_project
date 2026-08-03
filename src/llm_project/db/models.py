from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Integer, String, Text, create_engine
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


def init_db() -> None:
    from llm_project.db import nhs_schema  # noqa: F401  (registers its tables on Base.metadata)

    Base.metadata.create_all(get_engine())


def get_session():
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine())
    return _session_factory()
