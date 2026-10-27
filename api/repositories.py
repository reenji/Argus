"""Small synchronous repositories used by API routes and legacy engine facades."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import and_, delete, or_, select, update
from sqlalchemy.orm import Session

from .database import SessionLocal
from .models import AnswerCacheEntry, ChatMessage, MemoryEntry, TaskRecord, UserConfig


MEMORY_CATEGORIES = (
    "identity", "preferences", "projects", "relationships", "wishes", "notes"
)
MAX_MEMORY_KEY_LENGTH = 120


def upsert(db: Session, model, values: dict, conflict: list[str], changes: list[str]) -> None:
    """INSERT ... ON CONFLICT DO UPDATE, so concurrent writers cannot collide.

    A select-then-insert lets two requests both see "no row" and the second
    insert fail on the unique constraint.
    """
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    elif dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:  # pragma: no cover - only Postgres and SQLite are supported
        raise RuntimeError(f"Unsupported database dialect: {dialect}")
    statement = insert(model).values(**values)
    db.execute(statement.on_conflict_do_update(
        index_elements=conflict,
        set_={**{name: statement.excluded[name] for name in changes},
              "updated_at": datetime.now(timezone.utc)},
    ))


def flatten_memory(memory: dict) -> dict[tuple[str, str], str]:
    """(category, key) -> value for the rows memory maps to.

    Unknown categories become notes, nested entries get a "parent / child"
    key and keys are cut to the column size, so nothing is silently dropped
    and Postgres never rejects the whole save for one long key.
    """
    entries: dict[tuple[str, str], str] = {}

    def visit(category: str, prefix: str, items: dict) -> None:
        for key, entry in items.items():
            name = f"{prefix} / {key}" if prefix else str(key)
            if isinstance(entry, dict) and "value" not in entry:
                visit(category, name, entry)
                continue
            value = entry.get("value") if isinstance(entry, dict) else entry
            if value is None:
                continue
            entries[(category, name[:MAX_MEMORY_KEY_LENGTH])] = str(value)

    for category, items in memory.items():
        if isinstance(items, dict):
            visit(category if category in MEMORY_CATEGORIES else "notes", "", items)
    return entries


def load_user_memory(user_id: str) -> dict:
    result = {category: {} for category in MEMORY_CATEGORIES}
    with SessionLocal() as db:
        rows = db.scalars(
            select(MemoryEntry).where(MemoryEntry.user_id == user_id)
        ).all()
    for row in rows:
        result.setdefault(row.category, {})[row.key] = {
            "value": row.value,
            "updated": row.updated_at.date().isoformat(),
        }
    return result


def replace_user_memory(user_id: str, memory: dict) -> None:
    """Make the stored memory match memory, touching only rows that changed.

    Rewriting every row reset each entry's date, so trimming "oldest first"
    removed arbitrary entries.
    """
    wanted = flatten_memory(memory)
    with SessionLocal.begin() as db:
        rows = {
            (row.category, row.key): row
            for row in db.scalars(select(MemoryEntry).where(MemoryEntry.user_id == user_id))
        }
        for name, row in rows.items():
            if name not in wanted:
                db.delete(row)
            elif row.value != wanted[name]:
                row.value = wanted[name]
        for (category, key), value in wanted.items():
            if (category, key) not in rows:
                db.add(MemoryEntry(user_id=user_id, category=category, key=key, value=value))


def upsert_user_memory(user_id: str, entries: dict[tuple[str, str], str]) -> None:
    """Write only these entries, leaving the rest of the memory alone."""
    if not entries:
        return
    with SessionLocal.begin() as db:
        for (category, key), value in entries.items():
            upsert(
                db, MemoryEntry,
                {"user_id": user_id, "category": category, "key": key, "value": value},
                conflict=["user_id", "category", "key"],
                changes=["value"],
            )


def delete_user_memory(user_id: str, names: list[tuple[str, str]]) -> None:
    if not names:
        return
    with SessionLocal.begin() as db:
        db.execute(delete(MemoryEntry).where(
            MemoryEntry.user_id == user_id,
            or_(*(and_(MemoryEntry.category == c, MemoryEntry.key == k) for c, k in names)),
        ))


def load_user_config(user_id: str, namespace: str = "general") -> dict:
    with SessionLocal() as db:
        rows = db.scalars(select(UserConfig).where(
            UserConfig.user_id == user_id,
            UserConfig.namespace == namespace,
        )).all()
    return {row.key: row.value for row in rows}


def save_user_config(user_id: str, values: dict, namespace: str = "general") -> None:
    with SessionLocal.begin() as db:
        for key, value in values.items():
            upsert(
                db, UserConfig,
                {"user_id": user_id, "namespace": namespace, "key": str(key), "value": value},
                conflict=["user_id", "namespace", "key"],
                changes=["value"],
            )


def add_chat_message(user_id: str, role: str, content: str) -> ChatMessage:
    with SessionLocal.begin() as db:
        row = ChatMessage(user_id=user_id, role=role, content=content)
        db.add(row)
    return row


def recent_chat_messages(user_id: str, limit: int = 20) -> list[ChatMessage]:
    with SessionLocal() as db:
        rows = db.scalars(
            select(ChatMessage)
            .where(ChatMessage.user_id == user_id)
            .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
            .limit(limit)
        ).all()
        return list(reversed(rows))


def add_task_record(user_id: str, payload: dict) -> dict:
    with SessionLocal.begin() as db:
        row = TaskRecord(user_id=user_id, **payload)
        db.add(row)
    return task_record_dict(row)


def task_history(user_id: str, limit: int, status: str | None = None) -> list[dict]:
    with SessionLocal() as db:
        query = select(TaskRecord).where(TaskRecord.user_id == user_id)
        if status:
            query = query.where(TaskRecord.status == status)
        rows = db.scalars(
            query.order_by(TaskRecord.created_at.desc(), TaskRecord.id.desc()).limit(limit)
        ).all()
    return [task_record_dict(row) for row in reversed(rows)]


def task_record_dict(row: TaskRecord) -> dict:
    return {
        "task_id": row.task_id,
        "goal": row.goal,
        "status": row.status,
        "result": row.result,
        "error": row.error,
        "saved_file": row.saved_file,
        "timestamp": row.created_at.strftime("%Y-%m-%d %H:%M:%S"),
    }


def get_cached(user_id: str, normalized_question: str) -> str | None:
    with SessionLocal.begin() as db:
        answer = db.scalar(select(AnswerCacheEntry.answer).where(
            AnswerCacheEntry.user_id == user_id,
            AnswerCacheEntry.normalized_question == normalized_question,
        ))
        if answer is None:
            return None
        # Increment in SQL so concurrent hits are all counted, and stamp UTC:
        # SQLite returns naive datetimes, which made now(tzinfo) local time.
        db.execute(
            update(AnswerCacheEntry)
            .where(
                AnswerCacheEntry.user_id == user_id,
                AnswerCacheEntry.normalized_question == normalized_question,
            )
            .values(hits=AnswerCacheEntry.hits + 1, updated_at=datetime.now(timezone.utc))
        )
        return answer


def put_cached(user_id: str, normalized_question: str, question: str, answer: str) -> None:
    with SessionLocal.begin() as db:
        upsert(
            db, AnswerCacheEntry,
            {
                "user_id": user_id,
                "normalized_question": normalized_question,
                "question": question,
                "answer": answer,
            },
            conflict=["user_id", "normalized_question"],
            changes=["question", "answer"],
        )
