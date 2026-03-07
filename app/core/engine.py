from __future__ import annotations

import asyncio
import json
import os
import re
from typing import Any

import litellm

from app.core.database import (
    TaskStatus,
    create_conversation,
    create_task,
    get_conversation,
    get_conversation_messages,
    get_messages,
    save_message,
    update_task_status,
)
from app.core.skill_loader import Skill, load_skills
from mcp import ClientSession

from app.tools import playwright, telegram

DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "anthropic/claude-sonnet-4-20250514")

FILE_PATH_RE = re.compile(r'(/[^\s,;\"\'<>]+\.\w{2,5})\b')

# Tools available in the chat router (lightweight, no browser)
ROUTER_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "ask_human",
            "description": "Pause execution and ask the human operator for input via Telegram. Use when you need credentials, confirmations, or decisions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "The question to ask the human",
                    }
                },
                "required": ["question"],
            },
        },
    },
]

# Built-in tools available inside a skill agent loop (non-MCP)
BUILTIN_SKILL_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "ask_human",
            "description": "Pause execution and ask the human operator for input via Telegram. Use when you need credentials, confirmations, or decisions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "The question to ask the human",
                    }
                },
                "required": ["question"],
            },
        },
    },
]


async def handle_tool_call(
    name: str, arguments: dict, mcp_session: ClientSession | None = None
) -> str:
    """Execute a tool call and return its result as a string."""
    try:
        if name == "ask_human":
            return json.dumps({"status": "awaiting_input", "question": arguments["question"]})

        if mcp_session is not None:
            return await playwright.call_tool(mcp_session, name, arguments)

        return json.dumps({"error": f"Unknown tool: {name}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# Chat router
# ---------------------------------------------------------------------------

CHAT_SYSTEM_PROMPT = (
    "Voce e o CaramelBot, um assistente inteligente. "
    "Responda de forma natural e amigavel. "
    "Quando o usuario pedir algo que corresponda a uma das suas skills disponiveis, "
    "chame a skill correspondente usando a tool adequada. "
    "Se nao houver skill adequada, responda normalmente."
)


async def chat(user_message: str, conversation_id: int | None = None) -> dict:
    """Main chat entry point with automatic skill routing."""
    # Create or reuse conversation
    if conversation_id is None:
        conv = create_conversation()
        conversation_id = conv.id
    else:
        conv = get_conversation(conversation_id)
        if conv is None:
            return {"error": f"Conversation {conversation_id} not found"}

    # Load skills and build tool definitions
    skills = load_skills()
    skill_tools = [s.to_tool_definition() for s in skills.values()]
    tools = skill_tools + ROUTER_TOOLS

    # Build messages from conversation history
    messages: list[dict] = [{"role": "system", "content": CHAT_SYSTEM_PROMPT}]
    for msg in get_conversation_messages(conversation_id):
        entry: dict[str, Any] = {"role": msg.role, "content": msg.content}
        if msg.tool_calls:
            entry["tool_calls"] = json.loads(msg.tool_calls)
        messages.append(entry)

    # Add current user message
    messages.append({"role": "user", "content": user_message})
    save_message("user", user_message, conversation_id=conversation_id)

    # Call LLM
    response = await litellm.acompletion(
        model=DEFAULT_MODEL,
        messages=messages,
        tools=tools,
        tool_choice="auto",
    )

    choice = response.choices[0]
    assistant_msg = choice.message

    # No tool calls -> conversational response
    if not assistant_msg.tool_calls:
        save_message("assistant", assistant_msg.content or "", conversation_id=conversation_id)
        return {
            "conversation_id": conversation_id,
            "response": assistant_msg.content,
        }

    # Process tool calls
    for tool_call in assistant_msg.tool_calls:
        fn_name = tool_call.function.name
        fn_args = json.loads(tool_call.function.arguments)

        # Check if it's a skill call
        if fn_name in skills:
            skill = skills[fn_name]
            user_request = fn_args.get("user_request", user_message)

            # Save assistant message that triggered the skill
            save_message(
                "assistant",
                assistant_msg.content or "",
                tool_calls=[tc.model_dump() for tc in assistant_msg.tool_calls],
                conversation_id=conversation_id,
            )

            # Create task upfront so we have the task_id for the response
            task = create_task(skill.name, {"input": user_request}, conversation_id=conversation_id)

            async def _run_skill_background(
                _skill: Skill, _user_request: str, _conversation_id: int, _task_id: int, _fn_name: str,
            ) -> None:
                try:
                    result = await run_skill_task(
                        skill=_skill,
                        user_input=_user_request,
                        conversation_id=_conversation_id,
                        task_id=_task_id,
                    )
                    summary = result.get("result", "Skill executada.")
                    status = result.get("status", "COMPLETED")
                    save_message("assistant", f"[Skill {_fn_name}] {summary}", conversation_id=_conversation_id)
                    if status == "COMPLETED":
                        paths = [p for p in FILE_PATH_RE.findall(summary) if os.path.isfile(p)]
                        for path in paths:
                            await telegram.send_document(path, caption=os.path.basename(path))
                        await telegram.send_message(f"[CaramelBot] Skill '{_skill.name}' finalizada:\n\n{summary}")
                    elif status == "FAILED":
                        await telegram.send_message(f"[CaramelBot] Skill '{_skill.name}' falhou:\n\n{summary}")
                except Exception as e:
                    update_task_status(_task_id, TaskStatus.FAILED)
                    save_message("assistant", f"[Skill {_fn_name}] Erro: {e}", conversation_id=_conversation_id)
                    await telegram.send_message(f"[CaramelBot] Erro na skill '{_skill.name}': {e}")

            asyncio.create_task(
                _run_skill_background(skill, user_request, conversation_id, task.id, fn_name)
            )

            return {
                "conversation_id": conversation_id,
                "response": f"Ativando skill {skill.name}...",
                "task_id": task.id,
                "task_status": "RUNNING",
            }

        # Handle router tools (ask_human)
        if fn_name == "ask_human":
            question = fn_args["question"]
            await telegram.send_message(f"[CaramelBot] Preciso da sua ajuda:\n\n{question}")
            save_message(
                "assistant",
                assistant_msg.content or "",
                tool_calls=[tc.model_dump() for tc in assistant_msg.tool_calls],
                conversation_id=conversation_id,
            )
            return {
                "conversation_id": conversation_id,
                "response": question,
                "awaiting_input": True,
            }

        # Other router tools
        result_str = await handle_tool_call(fn_name, fn_args)
        save_message(
            "assistant",
            assistant_msg.content or "",
            tool_calls=[tc.model_dump() for tc in assistant_msg.tool_calls],
            conversation_id=conversation_id,
        )
        return {
            "conversation_id": conversation_id,
            "response": assistant_msg.content or result_str,
        }

    # Fallback
    return {
        "conversation_id": conversation_id,
        "response": assistant_msg.content or "",
    }


# ---------------------------------------------------------------------------
# Skill agent loop
# ---------------------------------------------------------------------------

def _build_messages(skill: Skill, task_id: int, user_input: str | None = None) -> list[dict]:
    """Build the message list from system prompt + persisted history."""
    system_prompt = (
        f"You are an agent executing the skill '{skill.name}'.\n\n"
        f"## Instructions\n{skill.instructions}\n\n"
        "Use the provided tools to accomplish the task. "
        "If you need human input (credentials, decisions, etc.), call ask_human."
    )

    messages: list[dict] = [{"role": "system", "content": system_prompt}]

    # Load persisted history
    for msg in get_messages(task_id):
        entry: dict[str, Any] = {"role": msg.role, "content": msg.content}
        if msg.tool_calls:
            entry["tool_calls"] = json.loads(msg.tool_calls)
        messages.append(entry)

    # Append new user input if provided
    if user_input:
        messages.append({"role": "user", "content": user_input})
        save_message("user", user_input, task_id=task_id)

    return messages


async def run_skill_task(
    skill: Skill,
    user_input: str = "",
    conversation_id: int | None = None,
    task_id: int | None = None,
) -> dict:
    """Run or resume an agent task for a given skill (clean context).

    Returns a dict with task_id, status, and result.
    """
    needs_mcp = "mcp_playwright" in (skill.tools or [])

    if needs_mcp:
        async with playwright.open_session() as mcp_session:
            mcp_tools = await playwright.get_tool_definitions(mcp_session)
            tools = BUILTIN_SKILL_TOOLS + mcp_tools
            return await _run_agent_loop(skill, user_input, conversation_id, task_id, tools, mcp_session)
    else:
        return await _run_agent_loop(skill, user_input, conversation_id, task_id, BUILTIN_SKILL_TOOLS, None)


async def _run_agent_loop(
    skill: Skill,
    user_input: str,
    conversation_id: int | None,
    task_id: int | None,
    tools: list[dict],
    mcp_session: ClientSession | None,
) -> dict:
    """Inner agent loop shared by MCP and non-MCP skill tasks."""
    # Create or resume task
    if task_id is None:
        task = create_task(skill.name, {"input": user_input}, conversation_id=conversation_id)
        task_id = task.id
    else:
        update_task_status(task_id, TaskStatus.RUNNING)

    messages = _build_messages(skill, task_id, user_input if user_input else None)

    # If no user message exists yet, add a default kickoff
    if not any(m["role"] == "user" for m in messages):
        kickoff = "Execute the skill instructions now."
        messages.append({"role": "user", "content": kickoff})
        save_message("user", kickoff, task_id=task_id)

    # Agent loop
    max_iterations = 20
    for _ in range(max_iterations):
        response = await litellm.acompletion(
            model=DEFAULT_MODEL,
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )

        choice = response.choices[0]
        assistant_msg = choice.message

        # Persist assistant message
        save_message(
            "assistant",
            assistant_msg.content or "",
            tool_calls=[tc.model_dump() for tc in assistant_msg.tool_calls]
            if assistant_msg.tool_calls
            else None,
            task_id=task_id,
        )

        # No tool calls -> task is done
        if not assistant_msg.tool_calls:
            update_task_status(task_id, TaskStatus.COMPLETED)
            return {
                "task_id": task_id,
                "status": "COMPLETED",
                "result": assistant_msg.content,
            }

        # Process tool calls
        messages.append(assistant_msg.model_dump(exclude_none=True))

        for tool_call in assistant_msg.tool_calls:
            fn_name = tool_call.function.name
            fn_args = json.loads(tool_call.function.arguments)

            # Handle ask_human: pause the loop
            if fn_name == "ask_human":
                question = fn_args["question"]
                await telegram.send_message(f"[CaramelBot] Preciso da sua ajuda:\n\n{question}")
                update_task_status(task_id, TaskStatus.AWAITING_INPUT)

                tool_result = json.dumps({"status": "paused", "message": "Waiting for human response"})
                save_message("tool", tool_result, task_id=task_id)

                return {
                    "task_id": task_id,
                    "status": "AWAITING_INPUT",
                    "question": question,
                }

            # Execute other tools (MCP or built-in)
            result_str = await handle_tool_call(fn_name, fn_args, mcp_session)
            save_message("tool", result_str, task_id=task_id)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result_str,
                }
            )

    # Max iterations reached
    update_task_status(task_id, TaskStatus.FAILED)
    return {
        "task_id": task_id,
        "status": "FAILED",
        "result": "Max iterations reached",
    }


# Backward-compatible alias
async def run_task(skill_name: str, user_input: str = "", task_id: int | None = None) -> dict:
    """Legacy entry point — resolves skill by name then delegates to run_skill_task."""
    skills = load_skills()
    if skill_name not in skills:
        return {"error": f"Skill '{skill_name}' not found. Available: {list(skills.keys())}"}
    return await run_skill_task(skill=skills[skill_name], user_input=user_input, task_id=task_id)
