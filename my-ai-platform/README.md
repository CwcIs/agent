# Thought Studio — Personal Multi-Agent Knowledge Workbench

> 把碎片想法 → 结构化笔记，让 AI 帮你连接、检索、挑战自己的思考。

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+ with pnpm
- [DeepSeek API Key](https://platform.deepseek.com/) (required)

### Setup

```bash
# 1. Install dependencies
cd packages/api && pip install -r requirements.txt
cd ../web && pnpm install
cd ../..

# 2. Configure API keys
cp .env.example .env
# Edit .env: set DEEPSEEK_API_KEY (required), OPENAI_API_KEY, GOOGLE_API_KEY (optional)

# 3. Start backend
cd packages/api
python -m src.main dev

# 4. Start frontend (in another terminal)
cd packages/web
pnpm dev

# 5. Open http://localhost:5173
```

### Optional Configuration

```bash
# Web search upgrade (Tavily, Phase 7.1)
TAVILY_API_KEY=your_key

# Calendar integration (CalDAV, Phase 7.2)
CALDAV_URL=https://your-caldav-server/
CALDAV_USERNAME=user
CALDAV_PASSWORD=pass

# Code execution (Phase 7.5)
RUN_PYTHON_ENABLED=true

# Plugin system (Phase 8.4)
PLUGIN_DIRS=/path/to/plugins
```

## Core Features

### 3 AI Agents

| Agent | Model | Role | Trigger |
|-------|-------|------|---------|
| **@knowledge** | DeepSeek | Main assistant — search, save, synthesize notes | Default (no mention) |
| **@review** | GPT-4o-mini | Challenge thinking — find bugs, flaws, contradictions | `@review` |
| **@brain** | Gemini | Brainstorm — lateral thinking, cross-domain connections | `@brain` |

### Knowledge Management

- **Smart search**: Semantic (vector) + keyword (FTS5) hybrid retrieval with multi-factor ranking
- **Knowledge graph**: Auto-discovered relations (similar/contradicts/evolved_from) with confidence scoring
- **Idea collision**: Unexpected connections between seemingly unrelated notes
- **Tag intelligence**: AI-suggested tags + synonym merging
- **Interval review**: Spaced repetition (SM-2) to not forget what you've learned

### External Knowledge (Phase 5)

- **Web import**: Paste URL → auto-extract clean content via trafilatura
- **File import**: Upload .md / .pdf / .txt → converted to structured notes
- **Source tracking**: Every note remembers where it came from
- **Citation chain**: Trace idea lineage back through evolved_from / wikilink edges

### Proactive Intelligence (Phase 6)

- **Daily digest**: AI-generated review of today's thinking (LLM-powered trends + anomalies)
- **Knowledge gaps**: AI suggests areas worth exploring based on your coverage
- **Writing prompts**: System suggests synthesis articles when you've accumulated enough on a topic
- **Smart notifications**: Badges for pending reviews, unread collisions, stale topics
- **User profile**: Thinking style analysis, interest distribution, active hours

### Tool Ecosystem (Phase 7)

- **Web search**: Tavily (primary) + DuckDuckGo (fallback) for real-time info
- **Calendar**: CalDAV integration (configurable, off by default)
- **Custom tools**: Define your own HTTP-based tools with JSON templates
- **Multimodal**: Attach images to notes, AI-powered image description
- **Code execution**: Docker-isolated Python sandbox (configurable, off by default)

### Platform Features (Phase 8)

- **Trace console**: Full request timeline — see every agent hop, tool call, and cost breakdown
- **Graph view**: D3.js force-directed knowledge graph visualization
- **Admin panel**: Cost tracking, usage stats, error monitoring, health checks
- **Export**: Markdown (ZIP) or JSON export — your data is always yours
- **Plugin system**: Load custom agents, tools, and providers from local directories
- **Security**: CSP headers, rate limiting, SSRF protection, CORS restrictions

## Architecture

```
User Input
  → Intent Router
  → Context Assembler (3-layer memory: working / episodic / semantic)
  → Hybrid Retrieval (FTS5 + sqlite-vec)
  → Agent ReAct Tool Loop
  → @agent Handoff (prompt-chained, max 5 depth)
  → Streaming SSE Response
```

- **Backend**: Python + FastAPI + LangGraph
- **Frontend**: Vue 3 + Vite + Tailwind CSS
- **Storage**: SQLite (16 tables + FTS5 + sqlite-vec vector search)
- **Communication**: SSE (Server-Sent Events)
- **Vector model**: sentence-transformers (paraphrase-multilingual-MiniLM-L12-v2)

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Ctrl+/` | Focus chat input |
| `Ctrl+K` | Focus note search |
| `Ctrl+Shift+T` | Toggle Trace Console |
| `Ctrl+Shift+G` | Toggle Graph View |
| `Ctrl+Shift+P` | Toggle Knowledge Profile |
| `Escape` | Close drawer / overlay |

## Project Structure

```
my-ai-platform/
├── packages/
│   ├── api/          — FastAPI + LangGraph backend
│   │   └── src/
│   │       ├── agent/        — registry / router / agents / graphs / providers
│   │       ├── context/      — 3-layer memory assembly
│   │       ├── db/           — schema (16 tables + FTS5 + vec)
│   │       ├── lib/          — embeddings / ranker / budget / llm_call
│   │       ├── tools/        — 25+ LangChain tools
│   │       ├── routes/       — SSE + REST + admin endpoints
│   │       └── main.py       — app entry point
│   └── web/          — Vue 3 frontend
│       └── src/
│           ├── views/        — ChatView / NoteListView / GraphView / ProfileView etc.
│           └── components/   — AppShell / LeftRail / TopStatusBar etc.
├── prompts/          — Agent system prompts
├── evals/            — Golden test set + runner
├── docs/             — Retrospectives + architecture plans
└── scripts/          — Seed data
```

## License

MIT
