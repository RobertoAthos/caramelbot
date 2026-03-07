from __future__ import annotations

import uvicorn
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.core.database import (
    TaskStatus,
    get_conversation,
    get_conversation_messages,
    get_task,
    init_db,
    list_tasks,
)
from app.core.engine import chat, run_task
from app.core.skill_loader import load_skills

app = FastAPI(title="CaramelBot", version="0.2.0")


@app.on_event("startup")
def on_startup() -> None:
    init_db()


# --- Schemas ---

class ChatRequest(BaseModel):
    message: str
    conversation_id: int | None = None


class RunSkillRequest(BaseModel):
    skill_name: str
    input: str = ""


class ResumeTaskRequest(BaseModel):
    task_id: int
    human_response: str


# --- Routes ---

@app.post("/chat")
async def api_chat(req: ChatRequest):
    """Natural language chat with automatic skill routing."""
    result = await chat(user_message=req.message, conversation_id=req.conversation_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/conversations/{conversation_id}")
def api_get_conversation(conversation_id: int):
    """Get a conversation with its messages."""
    conv = get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    messages = get_conversation_messages(conversation_id)
    return {
        "id": conv.id,
        "created_at": conv.created_at,
        "updated_at": conv.updated_at,
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at,
            }
            for m in messages
        ],
    }


@app.get("/skills")
def get_skills():
    """List all available skills."""
    skills = load_skills()
    return {
        name: {"description": s.description, "tools": s.tools}
        for name, s in skills.items()
    }


@app.post("/tasks/run")
async def api_run_task(req: RunSkillRequest):
    """Start a new task for a skill."""
    result = await run_task(skill_name=req.skill_name, user_input=req.input)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/tasks/resume")
async def api_resume_task(req: ResumeTaskRequest):
    """Resume a paused task with human input."""
    task = get_task(req.task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status != TaskStatus.AWAITING_INPUT:
        raise HTTPException(status_code=400, detail=f"Task is {task.status}, not AWAITING_INPUT")

    result = await run_task(
        skill_name=task.skill_name,
        user_input=req.human_response,
        task_id=req.task_id,
    )
    return result


@app.get("/tasks")
def api_list_tasks(status: TaskStatus | None = None):
    """List tasks, optionally filtered by status."""
    tasks = list_tasks(status)
    return [
        {
            "id": t.id,
            "skill_name": t.skill_name,
            "status": t.status,
            "created_at": t.created_at,
            "updated_at": t.updated_at,
        }
        for t in tasks
    ]


@app.get("/tasks/{task_id}")
def api_get_task(task_id: int):
    """Get a specific task."""
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {
        "id": task.id,
        "skill_name": task.skill_name,
        "status": task.status,
        "input_data": task.input_data,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


def start():
    """Entry point for `caramelbot` CLI command."""
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    start()
