<p align="center">
  <img src="assets/logo.png" alt="CaramelBot" width="300">
</p>

# CaramelBot

A minimalist AI agent framework with Markdown-based skills and human-in-the-loop support. CaramelBot routes natural language messages to LLM-powered skill agents via a FastAPI server, using Telegram as the primary interface and Playwright (via MCP) for browser automation.

## Features

- **Natural language routing** — Send a message and CaramelBot automatically picks the right skill to execute
- **Markdown-based skills** — Define agent behaviors as simple `.md` files with YAML frontmatter
- **Human-in-the-loop** — Agents can pause and ask the user for input (credentials, confirmations, decisions) via Telegram
- **Browser automation** — Skills can control a browser through Playwright via MCP (Model Context Protocol)
- **Multi-LLM support** — Uses [litellm](https://github.com/BerriAI/litellm) to work with OpenAI, Anthropic, Google, and other providers
- **REST API + Telegram** — Interact via HTTP endpoints or a Telegram bot

## Prerequisites

- **Python 3.11+**
- **[uv](https://docs.astral.sh/uv/)** — Python package manager
- **Node.js / npx** — Required for Playwright MCP server (spawned automatically)
- An API key for at least one LLM provider (Anthropic, OpenAI, or Google)

## Setup

### 1. Clone the repository

```bash
git clone <repo-url>
cd caramelbot
```

### 2. Install dependencies

```bash
uv sync
```

### 3. Configure environment variables

Create a `.env` file in the project root:

```env
# LLM provider (at least one API key required)
ANTHROPIC_API_KEY=sk-ant-...
# OPENAI_API_KEY=sk-...
# GEMINI_API_KEY=...

# LLM model (optional, defaults to anthropic/claude-sonnet-4-20250514)
# Uses litellm model format: provider/model-name
# DEFAULT_MODEL=anthropic/claude-sonnet-4-20250514

# Telegram bot (optional, needed for Telegram integration)
# TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
# TELEGRAM_CHAT_ID=123456789

# Database (optional, defaults to sqlite:///caramelbot.db)
# DATABASE_URL=sqlite:///caramelbot.db
```

### 4. Run the server

```bash
uv run caramelbot
```

The server starts on `http://localhost:8000` with auto-reload enabled.

Alternatively:

```bash
uv run python -m app.main
```

## API Endpoints

### Chat

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/chat` | Send a message with automatic skill routing |
| `POST` | `/webhook/telegram` | Telegram webhook for bot integration |
| `GET` | `/conversations/{id}` | Retrieve a conversation with its messages |

#### `POST /chat`

```json
{
  "message": "Emita uma nota fiscal para o cliente X",
  "conversation_id": null
}
```

### Skills

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/skills` | List all available skills |
| `POST` | `/tasks/run` | Start a skill task directly |
| `POST` | `/tasks/resume` | Resume a paused task with human input |
| `GET` | `/tasks` | List tasks (optionally filter by status) |
| `GET` | `/tasks/{id}` | Get a specific task |

## Creating Skills

Skills are Markdown files in the `skills/` directory. Each file has YAML frontmatter defining metadata and a Markdown body with agent instructions.

### Example: `skills/emitir_nota.md`

```markdown
---
name: gerador_nota_fiscal
description: Acessa o portal da prefeitura para emitir NFSe.
tools: [mcp_playwright]
---
# Instrucoes
1. Navegue ate o portal de emissao.
2. Se o login for solicitado, use a ferramenta 'ask_human'.
3. Preencha os dados do cliente e emita a nota.
4. Retorne o caminho completo do PDF resultante.
```

### Frontmatter fields

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Unique identifier for the skill (becomes the tool function name) |
| `description` | Yes | What the skill does (shown to the LLM for routing) |
| `tools` | No | List of tool sets to enable. Currently supports `mcp_playwright` |

### Available tools inside skills

- **`ask_human`** — Always available. Pauses the agent and sends a question to the user via Telegram
- **Playwright browser tools** — Enabled when `tools: [mcp_playwright]` is set. Provides full browser control (navigate, click, fill, screenshot, etc.)

## How It Works

1. **User sends a message** via Telegram or the `/chat` API
2. The **chat router** loads all skills as LLM tool definitions and calls the LLM
3. The LLM either responds conversationally or invokes a skill
4. If a skill is invoked, a **background task** runs the skill's agent loop with up to 20 iterations
5. The agent uses its tools (browser, ask_human) to complete the task
6. If `ask_human` is called, the task pauses (`AWAITING_INPUT`) and the user is notified via Telegram. The task resumes when the user responds via `POST /tasks/resume`
7. Results are sent back to the user via Telegram

## Telegram Setup

1. Create a bot with [@BotFather](https://t.me/BotFather) and get the token
2. Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in your `.env`
3. Configure a webhook pointing to `https://your-domain/webhook/telegram`

## Tech Stack

- **FastAPI** + **uvicorn** — HTTP server
- **litellm** — Multi-provider LLM abstraction
- **SQLModel** + **SQLite** — Persistence (conversations, tasks, messages)
- **Playwright via MCP** — Browser automation (stdio transport)
- **httpx** — Telegram Bot API client

## License

See [LICENSE](LICENSE) for details.
