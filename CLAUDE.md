# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CaramelBot is a minimalist AI agent framework with Markdown-based skills and human-in-the-loop support. It exposes a FastAPI server that routes natural language messages to LLM-powered skill agents, with Telegram as the primary user interface and Playwright (via MCP) for browser automation.

## Commands

```bash
# Install dependencies (uses uv)
uv sync

# Run the server (port 8000, with auto-reload)
uv run caramelbot
# or
uv run python -m app.main
```

There are no tests or linting configured yet.

## Architecture

### Request Flow

1. User sends a message via **Telegram webhook** (`POST /webhook/telegram`) or **REST API** (`POST /chat`)
2. The **chat router** (`app/core/engine.py:chat`) builds conversation history from the DB, loads all skills as LLM tool definitions, and calls the LLM (via litellm)
3. If the LLM invokes a skill, a **background task** is created and the skill's agent loop (`run_skill_task`) runs independently with its own tool set (browser tools + `ask_human`)
4. If the agent needs human input, it calls `ask_human`, which pauses the task (status `AWAITING_INPUT`) and sends a Telegram message. The user resumes via `POST /tasks/resume`

### Key Modules

- **`app/main.py`** — FastAPI app, routes, Telegram webhook handler, CLI entry point (`caramelbot` command)
- **`app/core/engine.py`** — Two-tier LLM orchestration: chat router (picks skills) and skill agent loop (executes skills with tools). Uses litellm for LLM calls. Max 20 iterations per skill task
- **`app/core/database.py`** — SQLModel/SQLite persistence. Models: `Conversation`, `Task` (with status machine: RUNNING → AWAITING_INPUT → COMPLETED/FAILED), `Message`
- **`app/core/skill_loader.py`** — Parses Markdown files from `skills/` directory. Skills have YAML frontmatter (name, description, tools) and Markdown body (instructions)
- **`app/tools/telegram.py`** — Telegram Bot API client (send messages, documents, long-poll)
- **`app/tools/playwright.py`** — Proxy to MCP Playwright server via JSON-RPC for browser automation

### Skills System

Skills are `.md` files in the `skills/` directory with YAML frontmatter:

```markdown
---
name: skill_name
description: What this skill does
tools: [mcp_playwright]
---
# Instructions
Step-by-step instructions for the agent...
```

Skills are dynamically loaded and exposed to the chat router as LLM tool definitions. The `name` field becomes both the tool function name and the lookup key.

### Environment Variables

Configured via `.env` (loaded with python-dotenv):
- `DEFAULT_MODEL` — litellm model identifier (default: `anthropic/claude-sonnet-4-20250514`)
- `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` — Telegram bot credentials
- `PLAYWRIGHT_MCP_URL` — MCP Playwright server endpoint (default: `http://localhost:3000`)
- `DATABASE_URL` — SQLite connection string (default: `sqlite:///caramelbot.db`)
- LLM API keys: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`

### Tool Sets

Two distinct tool sets exist in the engine:
- **`ROUTER_TOOLS`** — Only `ask_human`; used by the chat router
- **`SKILL_TOOLS`** — `ask_human` + browser tools (`browser_navigate`, `browser_click`, `browser_fill`, `browser_screenshot`, `browser_get_text`); used inside skill agent loops

## Language

The codebase uses Portuguese (Brazilian) for user-facing strings, system prompts, and skill content. Code identifiers and comments are in English.
