# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**MiroFish** is a swarm intelligence engine for multi-agent simulations and predictions. It combines:
- **Graph/Knowledge Building**: Extracts entities and relationships from seed documents using LLMs
- **Agent Simulation**: Runs multi-agent simulations across dual social platforms (Twitter-style + Reddit-style) using CAMEL-AI's OASIS framework
- **Report Generation**: Analyzes simulation results and generates prediction reports

The project is a full-stack application:
- **Backend**: Flask (Python 3.11+) with async simulation runner
- **Frontend**: Vue 3 + Vite with D3 visualization

## Development Workflow

### Initial Setup

```bash
# Install all dependencies (root + frontend + backend)
npm run setup:all

# Or step by step:
npm run setup          # Root + frontend only
npm run setup:backend  # Backend with uv (auto-creates venv)
```

### Running Development Servers

```bash
# Start both frontend (port 3000) and backend (port 5001) concurrently
npm run dev

# Run individually:
npm run backend   # Flask server on localhost:5001
npm run frontend  # Vite dev server on localhost:3000
```

### Environment Configuration

1. Copy template: `cp .env.example .env`
2. Fill required variables:
   - `LLM_API_KEY` + `LLM_BASE_URL` + `LLM_MODEL_NAME` (OpenAI-compatible API)
   - `ZEP_API_KEY` (Zep Cloud for memory/knowledge graph)
3. Optional: `LLM_BOOST_*` variables for dual-platform acceleration

See `CONFIGURATION.md` for detailed provider recommendations (OpenAI, DeepSeek, Groq, etc.).

### Testing & Quality

- **Backend Tests**: `cd backend && uv run pytest [path]`
- **Linting/Format**: Not currently automated; use manual review
- **Type Checking**: Pydantic models provide runtime validation

Note: Test coverage is currently minimal (`backend/scripts/test_profile_format.py` only). New features should include tests under `backend/tests/` (not yet created).

## Backend Architecture

### Structure
```
backend/
├── app/
│   ├── __init__.py          # Flask app factory & blueprint registration
│   ├── config.py            # Config class: validates .env, loads DEBUG/FLASK_HOST/FLASK_PORT
│   ├── api/                 # Flask blueprints (three endpoints)
│   │   ├── graph.py         # /api/graph - document upload, graph building, visualization
│   │   ├── simulation.py    # /api/simulation - run simulations, manage state
│   │   └── report.py        # /api/report - analyze results, report generation
│   ├── services/            # Business logic & orchestration
│   │   ├── graph_builder.py          # GraphRAG construction from documents
│   │   ├── llm_provider.py           # LLM API wrapper (OpenAI SDK)
│   │   ├── simulation_runner.py      # Async simulation execution, process management
│   │   ├── simulation_coordinator.py # Platform orchestration (Twitter + Reddit)
│   │   └── [other services]
│   ├── models/              # Pydantic data models
│   │   ├── simulation.py    # SimulationConfig, SimulationState
│   │   ├── agent.py         # Agent profiles, personas
│   │   └── [others]
│   └── utils/
│       ├── logger.py        # Loguru setup (structured logging)
│       └── [utilities]
├── run.py                   # Entry point: runs app with Config validation
└── pyproject.toml           # uv/hatchling config, Python 3.11+ requirement
```

### Key Services & Patterns

1. **Graph Builder** (`services/graph_builder.py`):
   - Reads documents (PDF, TXT with charset detection)
   - Extracts ontology (entities, relationships) via LLM
   - Builds knowledge graph via Zep Cloud API
   - Returns structured graph for visualization

2. **Simulation Coordinator** (`services/simulation_coordinator.py`):
   - Orchestrates dual-platform parallel simulation
   - Routes Twitter requests → primary `LLM_API_KEY`
   - Routes Reddit requests → `LLM_BOOST_API_KEY` (if configured)
   - Manages simulation state across platforms

3. **Simulation Runner** (`services/simulation_runner.py`):
   - Spawns subprocess for long-running simulations (avoids blocking Flask)
   - Uses OASIS framework from camel-ai for agent interactions
   - OASIS creates SQLite databases (`twitter_simulation.db`, `reddit_simulation.db`) to store simulation results
   - Reads from SQLite to return posts, comments, and interview history to API endpoints
   - Handles subprocess cleanup and database deletion on server shutdown
   - Exposes simulation state for polling via API

4. **LLM Provider** (`services/llm_provider.py`):
   - Wraps OpenAI SDK for any OpenAI-compatible API
   - Handles parsing of reasoning models (strips `<think>` tags from output)
   - Note: Recent fix (commit 985f89f) resolved 500 errors from markdown code fences in content fields

### Configuration Management

`app/config.py` loads and validates:
- `DEBUG` (defaults to True in dev, False in production)
- `FLASK_HOST`, `FLASK_PORT` (server binding)
- `LLM_*` / `LLM_BOOST_*` (LLM configuration)
- `ZEP_API_KEY` (memory layer)
- Raises `ValueError` if required keys missing; `run.py` catches and exits cleanly

## Data Storage: Two-Tier Architecture

MiroFish uses **two independent data layers** for different purposes:

### 1. Zep Cloud (Knowledge Graph & Memory)
- **Service**: Zep Cloud SaaS (`app.getzep.com`)
- **Configured via**: `ZEP_API_KEY` environment variable
- **Purpose**: Stores knowledge graph, ontology (entities/relationships), and agent long-term memory
- **Used by**:
  - `services/graph_builder.py` - writes graph after document analysis
  - `services/simulation_coordinator.py` - agents query memory during simulation
  - `api/report.py` - semantic search for insights across simulation history
- **Lifecycle**: Persists across simulation runs; shared knowledge base
- **Dependency risk**: Zep Community Edition (self-hosted) was sunsetted December 2025. The CE code is still available and runnable but is unmaintained. The only supported option is the Zep Cloud SaaS. Replacing Zep is a significant undertaking — see ~2,900 lines across `services/zep_tools.py`, `services/zep_graph_memory_updater.py`, `services/zep_entity_reader.py`, and `utils/zep_paging.py`. The main challenge is that Zep performs automatic entity/relationship extraction from raw text; raw graph databases (Neo4j, FalkorDB) do not and would require an explicit LLM-based extraction pipeline.

### 2. SQLite (Simulation Output)
- **Service**: Local SQLite databases created per simulation
- **Files**: `twitter_simulation.db` and `reddit_simulation.db` in simulation working directory
- **Purpose**: Stores posts, comments, users, interaction history from OASIS simulation
- **Used by**:
  - `services/simulation_runner.py` - created by OASIS framework during simulation execution
  - `api/simulation.py` - reads posts/comments/users/interview history to return to frontend
- **Lifecycle**: Created at simulation start, read during/after simulation, cleaned up when simulation deleted

### Read Patterns

- **Graph Building** → Zep writes, frontend reads via `/api/graph/visualization`
- **Simulation Execution** → OASIS writes to SQLite, frontend polls `/api/simulation/status` for progress
- **Results & Reports** → Read from SQLite for posts/comments; Zep for semantic analysis
- **Cleanup** → SQLite files deleted; Zep knowledge persists unless explicitly cleared

## Frontend Architecture

### Structure
```
frontend/
├── src/
│   ├── App.vue              # Root component
│   ├── main.js              # Vue app entry
│   ├── api/                 # HTTP client utilities
│   ├── components/          # Reusable Vue components
│   ├── views/               # Page-level components
│   ├── router/              # Vue Router config
│   ├── store/               # Pinia/state management
│   └── assets/              # Static files
├── package.json             # npm scripts, dependencies
└── vite.config.js           # Vite build config
```

### Key Dependencies

- **Vue 3**: Reactivity, composition API
- **Vite**: Fast dev server, optimized builds
- **Axios**: HTTP client for `/api/*` calls
- **D3**: Graph visualization (simulation results)
- **Vue Router**: Multi-page SPA routing

### Workflow

1. **Upload & Graph**: User uploads document → backend builds graph → frontend visualizes via D3
2. **Simulation**: User configures simulation → polls `/api/simulation/status` → displays results as simulation progresses
3. **Report**: User queries simulation results → backend runs report generation → frontend displays interactive report

## Common Development Tasks

### Adding a New API Endpoint

1. Create handler in `backend/app/api/[module].py` (or new file)
2. Register blueprint in `backend/app/__init__.py`: `app.register_blueprint([name]_bp, url_prefix='/api/[path]')`
3. Test with: `curl http://localhost:5001/api/[path]`
4. Frontend calls via axios in `frontend/src/api/`

### Modifying the Simulation Flow

1. Changes to agent behavior → `backend/app/services/simulation_coordinator.py`
2. Changes to graph building → `backend/app/services/graph_builder.py`
3. Changes to result parsing → `backend/app/api/report.py` and `simulation.py`
4. Test with: `npm run dev` then trigger simulation via UI

### Debugging Simulations

- Backend logs → stderr (configured in `setup_logger()`)
- Request/response logs → enabled at DEBUG level
- Simulation subprocess output → captured in temp files (path logged at start)
- Use `LLM_BOOST` configuration to split load if hitting rate limits

### Adding Python Dependencies

Use `uv` (installed automatically by `npm run setup:backend`):

```bash
cd backend
uv add [package-name]  # Adds to pyproject.toml and updates uv.lock
uv sync               # Install exact versions from uv.lock
```

## Known Issues & Recent Fixes

- **Commit 985f89f**: Fixed 500 errors from reasoning models (OpenAI o1, MiniMax, GLM) that emit `<think>` tags and markdown code fences in content fields. Parser now strips these before processing.
- **Commit a1ff79c**: Consolidated READMEs and created CONFIGURATION.md for clearer setup guidance.
- **Process Cleanup**: Backend registers cleanup function to terminate simulation subprocesses on server shutdown.

## Performance Considerations

1. **LLM_BOOST**: For large simulations (50+ agents per round), configure `LLM_BOOST_*` to shard Twitter vs. Reddit requests across two API keys/providers
2. **Zep Cloud**: Free tier sufficient for basic simulations; monitor token usage at `app.getzep.com`
3. **Simulation Timeout**: Long-running simulations (10+ rounds) may hit backend timeout; consider cloud deployment for production

## Standards & Conventions

- **Logging**: Use loguru via `get_logger()` for structured logs
- **Data Validation**: Pydantic models for all API request/response data
- **Code Style**: Google Python style guide (100-char line limit, uv for deps)
- **Git**: Conventional Commits; keep commits focused on single features/fixes
