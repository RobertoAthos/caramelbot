from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlmodel import Field, Session, SQLModel, create_engine, select


class TaskStatus(str, Enum):
    RUNNING = "RUNNING"
    AWAITING_INPUT = "AWAITING_INPUT"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Conversation(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class Task(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    conversation_id: Optional[int] = Field(default=None, foreign_key="conversation.id")
    skill_name: str
    status: TaskStatus = TaskStatus.RUNNING
    input_data: str = "{}"
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class Message(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    conversation_id: Optional[int] = Field(default=None, foreign_key="conversation.id")
    task_id: Optional[int] = Field(default=None, foreign_key="task.id")
    role: str  # "system", "user", "assistant", "tool"
    content: str
    tool_calls: Optional[str] = None  # JSON-serialized tool calls
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///caramelbot.db")
engine = create_engine(DATABASE_URL, echo=False)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Session:
    return Session(engine)


def create_conversation() -> Conversation:
    with get_session() as session:
        conv = Conversation()
        session.add(conv)
        session.commit()
        session.refresh(conv)
        return conv


def get_conversation(conversation_id: int) -> Conversation | None:
    with get_session() as session:
        return session.get(Conversation, conversation_id)


def get_conversation_messages(conversation_id: int) -> list[Message]:
    with get_session() as session:
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .where(Message.task_id == None)  # noqa: E711
            .order_by(Message.id)
        )
        return list(session.exec(stmt).all())


def create_task(skill_name: str, input_data: dict | None = None, conversation_id: int | None = None) -> Task:
    with get_session() as session:
        task = Task(
            skill_name=skill_name,
            input_data=json.dumps(input_data or {}),
            conversation_id=conversation_id,
        )
        session.add(task)
        session.commit()
        session.refresh(task)
        return task


def update_task_status(task_id: int, status: TaskStatus) -> Task:
    with get_session() as session:
        task = session.get(Task, task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")
        task.status = status
        task.updated_at = datetime.now(timezone.utc).isoformat()
        session.add(task)
        session.commit()
        session.refresh(task)
        return task


def get_task(task_id: int) -> Task | None:
    with get_session() as session:
        return session.get(Task, task_id)


def list_tasks(status: TaskStatus | None = None) -> list[Task]:
    with get_session() as session:
        stmt = select(Task)
        if status:
            stmt = stmt.where(Task.status == status)
        return list(session.exec(stmt).all())


def save_message(
    role: str,
    content: str,
    tool_calls: list | None = None,
    conversation_id: int | None = None,
    task_id: int | None = None,
) -> Message:
    with get_session() as session:
        msg = Message(
            conversation_id=conversation_id,
            task_id=task_id,
            role=role,
            content=content,
            tool_calls=json.dumps(tool_calls) if tool_calls else None,
        )
        session.add(msg)
        session.commit()
        session.refresh(msg)
        return msg


def get_messages(task_id: int) -> list[Message]:
    with get_session() as session:
        stmt = select(Message).where(Message.task_id == task_id).order_by(Message.id)
        return list(session.exec(stmt).all())
