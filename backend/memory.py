from database import SessionLocal, ConversationMessage, ProjectContext
from sqlalchemy import desc


def save_message(session_id: str, role: str, content: str):
    """Save a single message to PostgreSQL."""
    db = SessionLocal()
    try:
        message = ConversationMessage(
            session_id=session_id,
            role=role,
            content=content
        )
        db.add(message)
        db.commit()
    finally:
        db.close()


def get_history(session_id: str, limit: int = 10) -> list:
    """Retrieve last N messages for a session in chronological order."""
    db = SessionLocal()
    try:
        messages = db.query(ConversationMessage)\
            .filter(ConversationMessage.session_id == session_id)\
            .order_by(desc(ConversationMessage.created_at))\
            .limit(limit)\
            .all()

        # Reverse to get chronological order
        messages.reverse()

        return [
            {"role": msg.role, "content": msg.content}
            for msg in messages
        ]
    finally:
        db.close()


def save_project_context(session_id: str, project_name: str, client_name: str, notes: str = ""):
    """Save or update project context for a session."""
    db = SessionLocal()
    try:
        existing = db.query(ProjectContext)\
            .filter(ProjectContext.session_id == session_id)\
            .first()

        if existing:
            existing.project_name = project_name
            existing.client_name = client_name
            existing.notes = notes
        else:
            context = ProjectContext(
                session_id=session_id,
                project_name=project_name,
                client_name=client_name,
                notes=notes
            )
            db.add(context)

        db.commit()
    finally:
        db.close()


def get_project_context(session_id: str) -> dict:
    """Get project context for a session."""
    db = SessionLocal()
    try:
        context = db.query(ProjectContext)\
            .filter(ProjectContext.session_id == session_id)\
            .first()

        if context:
            return {
                "project_name": context.project_name,
                "client_name": context.client_name,
                "notes": context.notes
            }
        return {}
    finally:
        db.close()


def clear_history(session_id: str):
    """Clear all messages for a session."""
    db = SessionLocal()
    try:
        db.query(ConversationMessage)\
            .filter(ConversationMessage.session_id == session_id)\
            .delete()
        db.commit()
    finally:
        db.close()


def get_session_summary(session_id: str) -> dict:
    """Get summary stats for a session."""
    db = SessionLocal()
    try:
        total = db.query(ConversationMessage)\
            .filter(ConversationMessage.session_id == session_id)\
            .count()

        last_message = db.query(ConversationMessage)\
            .filter(ConversationMessage.session_id == session_id)\
            .order_by(desc(ConversationMessage.created_at))\
            .first()

        return {
            "total_messages": total,
            "last_activity": str(last_message.created_at) if last_message else None
        }
    finally:
        db.close()