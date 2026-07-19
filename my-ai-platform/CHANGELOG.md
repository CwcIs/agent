# Changelog

## Phase 8 (2026-07-19) — Platform & Polish

### 8.6 Documentation
- README.md with quick start, feature overview, architecture diagram
- CHANGELOG.md (this file)
- Keyboard shortcuts reference

### 8.5 Security
- Rate limiting middleware (60 req/min per IP on chat/digest endpoints)
- Content-Security-Policy headers
- X-Content-Type-Options / X-Frame-Options headers
- SSRF protection on web import (already existed, documented)

### 8.4 Plugin System
- `plugin_loader.py` — manifest-based plugin discovery and loading
- Supports Agent, Tool, and Provider plugin types
- `PLUGIN_DIRS` environment variable for configuration
- Security: only loads from explicitly configured local directories

### 8.3 Export
- Frontend export buttons (MD ZIP / JSON) in ProfileView
- Backend: `GET /notes/export?fmt=markdown|json`

### 8.2 Admin Panel
- `GET /admin/stats` — notes, costs, models, agents, DB size
- `GET /admin/errors` — recent error log
- `GET /admin/health` — vector model status, provider checks

### 8.1 Performance
- LRU cache for vector search results (5min TTL, 64 entries)
- Thread pool for CPU-bound embedding operations

## Phase 7 (2026-07-15) — Tool Ecosystem

### 7.5 Code Execution
- `run_python` tool — Docker sandbox (primary) + subprocess (fallback)
- Config-gated: `RUN_PYTHON_ENABLED=true` required
- Safety: 10s timeout, 256MB memory limit, network disabled (Docker)

### 7.4 Multimodal
- `add_attachment` tool — attach images to notes
- `describe_images` tool — AI-powered image description via GPT-4o
- Backend: `POST /notes/{id}/attachments` + `attachments_json` column

### 7.3 Custom Tools
- `custom_tools` table + CRUD API
- Dynamic tool generation from DB (`make_tools` loads enabled custom tools)
- HTTP GET/POST with `{{response}}` template substitution

### 7.2 Calendar Integration
- `get_today_events` / `get_week_events` / `create_calendar_event` tools
- CalDAV protocol support (configurable via env vars)
- Off by default; requires `CALDAV_URL/USERNAME/PASSWORD`

### 7.1 Web Search Upgrade
- Tavily Search API as primary provider (with API key)
- DuckDuckGo as automatic fallback
- Structured results with relevance scores

## Phase 6 (2026-07-10) — Proactive Intelligence

### 6.5 User Profile
- `user_profile.py` module — thinking style, interests, active hours, coverage
- `GET /user/profile` endpoint with full knowledge landscape
- ProfileView.vue — visual knowledge dashboard

### 6.4 Writing Suggestions
- `suggest_writing` tool — detects topics with ≥5 notes
- Daily digest includes writing suggestions
- Frontend "写作灵感" section in DailyDigestPanel

### 6.3 Review Reminder
- SM-2 spaced repetition algorithm (simplified)
- `review_note` / `get_due_reviews` tools
- Notes table: `last_reviewed_at`, `review_interval`, `review_count` columns

### 6.2 Knowledge Gap Detection
- `suggest_gaps` tool — LLM-powered gap analysis
- Rule-based fallback for when LLM is unavailable

### 6.1 Scheduled Push
- `POST /digest/daily/generate` — cron-friendly endpoint
- Frontend periodic polling (5min interval)
- Web Notification API for new digest alerts

## Phase 5 (2026-07-05) — External Knowledge

### 5.5 External Search
- `web_search` tool — DuckDuckGo integration
- Registered to KnowledgeAgent

### 5.4 Citation Chain
- `GET /notes/{id}/trace` — BFS-based ancestor/descendant tracing
- Source tracking display in NoteDetailPanel

### 5.3 Source Tracking
- `source_url`, `source_file`, `source_type`, `word_count` on notes
- `source_trace` table — content hash for dedup, fetch status
- Source-group API for same-source aggregation

### 5.2 File Import
- `POST /notes/import/file` — multipart upload (MD/PDF/TXT)
- Frontmatter parsing for .md files
- PyPDF2 for PDF text extraction
- Duplicate detection via content hash

### 5.1 Web Import
- `import_webpage` tool + REST endpoint
- trafilatura for clean content extraction
- SSRF protection (DNS rebinding check, private IP block)
- 5MB size limit, 15s timeout

## Phase 4 (2026-06-25) — Knowledge Ecology

### 4.6 GraphView
- D3.js force-directed knowledge graph
- GET /notes/graph — BFS traversal with depth control
- Color-coded relations, zoom/pan, search highlight

### 4.5 Daily Digest 2.0
- LLM-powered daily/weekly/monthly digests
- Trend detection, anomaly discovery, smart follow-up questions
- Collision display in digest panel

### 4.4 Tag Intelligence
- `suggest_tags` — keyword-based tag suggestion
- `merge_tags` / `list_tag_aliases` — synonym management
- `tag_aliases` table

### 4.3 Idea Collision
- `detect_collisions` — 3-phase algorithm (candidate gen → LLM scoring → persist)
- `idea_collisions` table
- Display in daily digest

### 4.2 Retrieval Ranker
- `ranker.py` — multi-factor ranking (semantic + keyword + graph + Bayesian + recency)
- `retrieval_events` and `note_stats` tables
- Integrated into `search_notes` and `assemble_context()`

### 4.1 Trusted Relations
- Edges table: confidence, source, evidence, status columns
- Auto-similar edges on save (embedding similarity > 0.82)
- `pending_suggestions` table with accept/reject flow
- `suggest_relation` / `accept_suggestion` / `reject_suggestion` tools

### 4.0 Trace Console
- `GET /traces/recent` + `GET /traces/{id}` — full timeline view
- TraceConsole.vue — trace list, filtering, detail view
- `trace_id` threading through SSE events

## Phase 3 (2026-06-16) — A2A Architecture

- Multi-Agent routing with `@agent` mention syntax
- Parallel fan-out (MultiMentionOrchestrator)
- Gemini BrainAgent for lateral thinking
- Session persistence + crash recovery
- Model routing by agent type
- Verdict detection (natural_end / missing_handoff / loop_detected)

## Phase 2 (2026-06-09) — Semantic Memory

- sqlite-vec vector search with sentence-transformers
- FTS5 full-text search
- Context assembly with 3-layer memory
- Streaming SSE with agent switch notifications

## Phase 1 (2026-06-02) — Foundation

- Single-agent ReAct tool loop (search_notes + save_note)
- FastAPI + Vue 3 skeleton
- SQLite with 6 core tables
- Golden eval set (10/10 baseline)
