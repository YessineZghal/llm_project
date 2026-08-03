import uuid

import pandas as pd

from llm_project.db.models import Conversation, Feedback, get_engine, get_session, init_db


def log_conversation(
    question: str,
    answer: str,
    mode: str,
    model: str,
    response_time_seconds: float,
    search_query: str | None = None,
    retrieval_method: str | None = None,
    prompt_variant: str | None = None,
    source_doc_ids: list[str] | None = None,
) -> str:
    init_db()
    conversation_id = str(uuid.uuid4())
    doc_ids = source_doc_ids or []

    session = get_session()
    try:
        session.add(
            Conversation(
                id=conversation_id,
                question=question,
                search_query=search_query,
                answer=answer,
                mode=mode,
                retrieval_method=retrieval_method,
                prompt_variant=prompt_variant,
                model=model,
                response_time_seconds=response_time_seconds,
                num_source_docs=len(doc_ids),
                source_doc_ids=", ".join(doc_ids),
            )
        )
        session.commit()
    finally:
        session.close()

    return conversation_id


def log_feedback(conversation_id: str, rating: int) -> None:
    init_db()
    session = get_session()
    try:
        session.add(Feedback(conversation_id=conversation_id, rating=rating))
        session.commit()
    finally:
        session.close()


def get_conversations_df() -> pd.DataFrame:
    """All logged conversations, for the monitoring dashboard (app/pages/*)."""
    init_db()
    return pd.read_sql(Conversation.__table__.select().order_by(Conversation.created_at), get_engine())


def get_feedback_df() -> pd.DataFrame:
    """All logged feedback votes, for the monitoring dashboard (app/pages/*)."""
    init_db()
    return pd.read_sql(Feedback.__table__.select().order_by(Feedback.created_at), get_engine())
