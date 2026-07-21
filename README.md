# RedisRAG — AI-Powered GitHub Profile Analyzer

> Analyze any GitHub developer's profile and have an AI conversation about their projects, powered by Retrieval-Augmented Generation (RAG).

RedisRAG fetches public repositories, reads their README files, converts them into vector embeddings using **Google Gemini**, stores those vectors in **Redis**, and lets you ask questions about the developer's work. When you ask a question, the system searches Redis for the most relevant README snippets and sends them to **Groq's Llama 3.3 70B** to generate an accurate, grounded answer with source citations.

---

## How It Works (The Big Picture)

```mermaid
graph LR
    subgraph You["You"]
        Browser[Browser]
    end

    subgraph Frontend["React Frontend (Vercel)"]
        UI[Dashboard UI]
    end

    subgraph Backend["FastAPI Backend (Render)"]
        API[REST API]
        Embed[Gemini Embeddings]
        RAG[RAG Engine]
    end

    subgraph External["External APIs"]
        GitHub[GitHub API]
        Gemini[Google Gemini API]
        Groq[Groq LLM API]
    end

    subgraph Storage["Databases"]
        Redis[(Redis Vector DB)]
        Postgres[(PostgreSQL)]
    end

    Browser --> UI
    UI --> API
    API --> GitHub
    API --> Embed
    Embed --> Gemini
    RAG --> Groq
    API --> Redis
    API --> Postgres
```

### Step-by-Step Flow

**When you click "Analyze":**

```mermaid
graph TD
    A["Enter GitHub username"] --> B["Fetch repos + READMEs from GitHub API"]
    B --> C["Split each README into text chunks"]
    C --> D["Convert chunks to 3072-dim vectors via Google Gemini REST API"]
    D --> E["Store vectors + metadata in Redis"]
    E --> F["Profile ready for questions!"]

    style A fill:#e8f5e9
    style F fill:#e8f5e9
```

**When you ask a question:**

```mermaid
graph TD
    Q["You ask: 'What projects use FastAPI?'"] --> V["Convert question to vector via Gemini"]
    V --> S["Search Redis for most similar README chunks (KNN cosine)"]
    S --> P["Build prompt: 'Based on these docs, answer...'"] 
    P --> L["Send prompt to Groq Llama 3.3 70B"]
    L --> R["Get grounded answer with source repos"]

    style Q fill:#e3f2fd
    style R fill:#e3f2fd
```

---

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Frontend** | React 19 + TypeScript + Vite | Dashboard UI with auth, profile viewer, and AI chat |
| **Backend** | Python + FastAPI + Uvicorn | REST API server |
| **Vector DB** | Redis Stack (RediSearch module) | Store and search embedding vectors |
| **User DB** | PostgreSQL | Store verified user accounts |
| **Embeddings** | Google Gemini REST API (`gemini-embedding-001`) | Convert text to 3072-dimensional vectors |
| **LLM** | Groq API (Llama 3.3 70B Versatile) | Generate AI answers from retrieved context |
| **Auth** | Email OTP + JWT tokens | Stateless authentication |
| **Email** | Resend API (primary) / Gmail SMTP (fallback) | Send OTP verification emails |
| **Hosting** | Render (backend) + Vercel (frontend) | Production deployment |

---

## Features

### Authentication
- **Email OTP login** — Users enter their email, receive a 6-digit code, and verify it.
- **OTP stored in Redis** with a 5-minute TTL (auto-expires).
- **JWT tokens** — After verification, the API issues a Bearer token that protects all endpoints.
- **User persistence** — Verified users are saved to PostgreSQL after first login.

### GitHub Profile Analysis
- **Fetches all public repos** and their README files via GitHub API.
- **Smart filtering** — Skips forks, archived repos, and READMEs shorter than 300 characters.
- **Ranks repos** by popularity (stars + forks) and indexes the top 15.
- **Background processing** — Analysis runs in a background thread so the API responds instantly.
- **Real-time progress** — Frontend polls status with exponential backoff to track progress.

### Embeddings & Vector Storage
- **Google Gemini REST API** — Direct HTTP POST calls to `generativelanguage.googleapis.com` (no SDK, no deadlocks).
- **3072-dimensional vectors** — High-fidelity semantic representations of README content.
- **Zero-dependency text splitter** — Pure Python recursive splitter (no langchain import needed).
- **SHA-based caching** — Tracks the Git SHA of each README. Re-analysis skips unchanged repos entirely.
- **Dynamic index management** — Automatically detects vector dimension mismatches and recreates the Redis index.

### RAG Chat
- **Cosine similarity search** — KNN Flat algorithm in Redis finds the most relevant README chunks.
- **Groq Llama 3.3 70B** — Generates fast, accurate answers grounded in the retrieved context.
- **Source citations** — Every answer lists which repositories were referenced.

---

## Project Structure

```
redis-rag/
├── backend/
│   ├── app/
│   │   ├── api/                  # Route handlers
│   │   │   ├── auth.py           #   Email OTP + JWT login
│   │   │   ├── github.py         #   Profile analysis + status polling
│   │   │   └── chat.py           #   RAG question answering
│   │   ├── core/                 # Configuration & clients
│   │   │   ├── config.py         #   All env vars (pydantic-settings)
│   │   │   ├── indexing_config.py#   Tunable indexing parameters
│   │   │   ├── redis_client.py   #   Redis connection
│   │   │   └── jwt.py            #   JWT token utilities
│   │   ├── db/                   # PostgreSQL layer
│   │   │   ├── database.py       #   SQLAlchemy engine + session
│   │   │   ├── models.py         #   User model
│   │   │   └── crud.py           #   Create/read operations
│   │   ├── schemas/              # Pydantic request/response models
│   │   └── services/             # Business logic
│   │       ├── embedding_service.py  #   Chunking, embedding, vector storage, search
│   │       ├── github_service.py     #   GitHub API fetching
│   │       ├── rag_service.py        #   LLM prompt + answer generation
│   │       ├── email_service.py      #   OTP email sending (Resend + SMTP)
│   │       └── otp_service.py        #   OTP generation + Redis caching
│   ├── requirements.txt
│   └── main.py
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── LandingPage.tsx       #   Hero page with feature showcase
│   │   │   ├── AuthCard.tsx          #   Email OTP login form
│   │   │   ├── DashboardWorkspace.tsx#   Profile analysis + progress view
│   │   │   └── ChatConsole.tsx       #   AI chat interface
│   │   ├── services/
│   │   │   └── api.ts                #   Backend API client
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── package.json
│   └── vite.config.ts
├── docker-compose.yml            # Redis Stack + PostgreSQL for local dev
└── .env                          # Environment variables (not committed)
```

---

## Setup & Installation

### Prerequisites
- Python 3.11+
- Node.js 18+
- Docker & Docker Compose (for local Redis + PostgreSQL)

### 1. Start Databases

```bash
docker compose up -d
```

This starts:
- **Redis Stack** on port `6379` (includes RediSearch for vector search)
- **RedisInsight** on port `8001` (web UI to inspect Redis data)
- **PostgreSQL** on port `5432`

### 2. Configure Environment Variables

Create a `.env` file in the project root:

```env
# ── Email (pick one) ─────────────────────────────────────────
RESEND_API_KEY=re_xxxxxxxxxxxx          # Recommended for production
EMAIL_ADDRESS=your-email@gmail.com      # Fallback: Gmail SMTP
EMAIL_PASSWORD=your-app-password        # Gmail App Password (not regular password)

# ── Database ─────────────────────────────────────────────────
DATABASE_URL=postgresql://postgres:admin123@localhost:5432/redisrag

# ── Redis ────────────────────────────────────────────────────
REDIS_HOST=localhost
REDIS_PORT=6379
# REDIS_PASSWORD=                       # Only needed for cloud Redis

# ── Auth ─────────────────────────────────────────────────────
SECRET_KEY=your-jwt-secret-key

# ── GitHub ───────────────────────────────────────────────────
GITHUB_TOKEN=ghp_xxxxxxxxxxxx           # Optional, increases rate limit

# ── AI APIs ──────────────────────────────────────────────────
GOOGLE_API_KEY=AIzaSy...                # Required — for Gemini embeddings
GROQ_API_KEY=gsk_...                    # Required — for Llama 3.3 chat
```

> **Note:** `GOOGLE_API_KEY` is the most critical variable. Get it free from [Google AI Studio](https://aistudio.google.com/apikey).

### 3. Start the Backend

```bash
cd backend
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --reload
```

API docs available at: **http://127.0.0.1:8000/docs**

### 4. Start the Frontend

```bash
cd frontend
npm install
npm run dev
```

App runs at: **http://localhost:5173**

---

## API Reference

### Authentication

| Endpoint | Method | Body | Description |
|----------|--------|------|-------------|
| `/auth/send-otp` | POST | `{ "email": "user@example.com" }` | Sends a 6-digit OTP to the email |
| `/auth/verify-otp` | POST | `{ "email": "...", "otp": "123456" }` | Verifies OTP, returns JWT token |
| `/auth/me` | GET | — | Returns current user info (requires Bearer token) |

### GitHub Analysis

| Endpoint | Method | Body | Description |
|----------|--------|------|-------------|
| `/github/analyze` | POST | `{ "username": "torvalds" }` | Starts background analysis of a GitHub profile |
| `/github/status/{username}` | GET | — | Returns analysis progress (`not_started` / `processing` / `completed` / `failed`) |

### RAG Chat

| Endpoint | Method | Body | Description |
|----------|--------|------|-------------|
| `/chat` | POST | `{ "username": "torvalds", "question": "What language is linux written in?" }` | Returns AI answer + source repos |

> All endpoints except `/auth/send-otp` and `/auth/verify-otp` require `Authorization: Bearer <token>` header.

---

## Deployment

### Architecture (Production)

```mermaid
graph LR
    subgraph Vercel["Vercel (Frontend)"]
        React["React 19 + Vite"]
    end

    subgraph Render["Render (Backend)"]
        FastAPI["FastAPI + Uvicorn"]
    end

    subgraph Cloud["Cloud Services"]
        RedisCloud["Redis Cloud"]
        Neon["Neon PostgreSQL"]
        GeminiAPI["Google Gemini API"]
        GroqAPI["Groq API"]
        ResendAPI["Resend Email API"]
    end

    React -->|"VITE_API_URL"| FastAPI
    FastAPI --> RedisCloud
    FastAPI --> Neon
    FastAPI --> GeminiAPI
    FastAPI --> GroqAPI
    FastAPI --> ResendAPI
```

### Deploy Backend to Render

1. Push code to GitHub.
2. Create a **Web Service** on [Render](https://render.com).
3. Set **Build Command**: `pip install -r requirements.txt`
4. Set **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
5. Set **Root Directory**: `backend`
6. Add all environment variables from `.env` to Render's dashboard.

### Deploy Frontend to Vercel

1. Create a new project on [Vercel](https://vercel.com) connected to your GitHub repo.
2. Set **Root Directory**: `frontend`
3. Set **Framework Preset**: Vite
4. Add this environment variable:
   ```
   VITE_API_URL=https://your-backend.onrender.com
   ```
5. Deploy. **Important:** If you change `VITE_API_URL` later, you must **redeploy** because Vite bakes env vars into the JavaScript at build time.

---

## Indexing Pipeline (Detailed)

The embedding pipeline is the core engine. Here's exactly what happens when you click "Analyze":

```mermaid
graph TD
    Start["POST /github/analyze"] --> BG["Launch background thread"]
    BG --> Fetch["1. Fetch GitHub profile + repos"]
    Fetch --> Filter["2. Filter: skip forks, archived, short READMEs"]
    Filter --> Rank["3. Rank by stars+forks, pick top 15"]
    Rank --> Loop["4. For each repo:"]

    subgraph PerRepo["Per-Repository Processing"]
        Loop --> SHA{"Check SHA cache in Redis"}
        SHA -->|"Same SHA"| Skip["Skip (already indexed)"]
        SHA -->|"Different/New"| Clean["Delete old vectors for this repo"]
        Clean --> Chunk["Split README into ~1500-char chunks"]
        Chunk --> Batch["Batch chunks (up to 32 per API call)"]
        Batch --> Embed["POST to Gemini batchEmbedContents"]
        Embed --> Store["Write vectors + metadata to Redis"]
        Store --> Cache["Save new SHA to cache"]
    end

    Skip --> Next["Next repo"]
    Cache --> Next
    Next --> Done["Mark status as 'completed'"]

    style Skip fill:#d4edda,stroke:#28a745
    style Embed fill:#fff3cd,stroke:#ffc107
```

### Key Optimizations

| Optimization | What It Does | Impact |
|---|---|---|
| **SHA caching** | Stores the Git file SHA of each indexed README. Skips repos that haven't changed. | Re-analysis completes in <1 second instead of minutes |
| **Per-repo streaming** | Processes one repo at a time instead of loading all chunks into memory | Peak memory stays at `O(single_repo)` instead of `O(all_repos)` |
| **Batch embedding** | Sends up to 32 text chunks in a single API call | ~5x faster than individual requests |
| **Direct REST API** | Calls Gemini via `httpx.post()` instead of through the Google SDK | Eliminates the GCP credential detection deadlock |
| **Zero-dep text splitter** | Pure Python recursive splitter, no `langchain_text_splitters` import | Instant startup, no 4-second import freeze |
| **Single-user mode** | When enabled, cleans up previous users' vectors before indexing | Keeps Redis memory under free-tier limits (~30MB) |
| **Stale vector cleanup** | Deletes old vectors for a repo before inserting new ones | Prevents duplicate/outdated results in search |

### Tunable Parameters

All indexing behavior is controlled from [`indexing_config.py`](backend/app/core/indexing_config.py):

| Parameter | Default | Description |
|---|---|---|
| `MAX_REPOS_TO_INDEX` | 15 | Only index the top N repos by popularity |
| `MIN_README_LENGTH` | 300 | Skip READMEs shorter than this (chars) |
| `CHUNK_SIZE` | 1500 | Characters per text chunk (~375 words) |
| `CHUNK_OVERLAP` | 150 | Overlap between consecutive chunks |
| `EMBEDDING_BATCH_SIZE` | 32 | Chunks per Gemini API call |
| `EMBEDDING_API_TIMEOUT` | 60s | Timeout per API call |
| `EMBEDDING_MAX_RETRIES` | 3 | Retry attempts for transient failures |
| `SINGLE_USER_MODE` | true | Purge other users' data when indexing a new user |

---

## Deployment Debugging Chronicle

Every production bug encountered while deploying RedisRAG to Render + Vercel, the root causes, and the solutions. Written as a future reference.

---

### Problem 1: Google GenAI SDK Deadlock on Render

**Symptom:** Background indexing task hung forever at `repos_done: 0`. Locally the same code finished in 15 seconds. No error, no timeout — just frozen.

**Root Cause:** Google's Python SDKs (`google-genai`, `langchain-google-genai`) try to detect if they're running inside Google Cloud by sending HTTP requests to the GCP Metadata Server at `http://169.254.169.254`. On Render (which runs on AWS), these requests never get a response. The SDK blocks waiting — **2+ minutes per attempt**, with multiple retries.

```mermaid
graph LR
    SDK["Google GenAI SDK"] -->|"HTTP GET"| Meta["GCP Metadata Server<br/>169.254.169.254"]
    Meta -.->|"No response<br/>(not on GCP)"| SDK
    SDK -->|"Blocks for 2+ min<br/>then retries..."| Dead["Thread deadlocked"]
```

**Solution:** Replaced the SDK with a `GeminiAPIEmbeddings` class that calls the Gemini REST API directly via `httpx`:

```python
# Before (DEADLOCKS on Render):
from langchain_google_genai import GoogleGenerativeAIEmbeddings
model = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001")

# After (WORKS everywhere):
response = httpx.post(
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:batchEmbedContents?key=...",
    json={"requests": [...]},
    timeout=30.0
)
```

---

### Problem 2: Text Splitter Import Freeze (CPU Starvation)

**Symptom:** Redis logs showed `[1/8] Processing repository: ...` but never `Split into X chunks`. Stuck forever.

**Root Cause:** The text splitter was lazy-imported:
```python
from langchain_text_splitters import RecursiveCharacterTextSplitter  # Takes 4+ seconds
```
This import triggers a chain reaction of heavy imports (LangChain core, Pydantic validators, regex engines). On Render's free tier (0.1 CPU core), while also handling 9+ polling requests per second, the background thread never got enough CPU time to finish the import.

**Solution:** Replaced with a pure Python recursive text splitter defined inline — zero imports, runs in microseconds.

---

### Problem 3: Frontend Polling Storm

**Symptom:** Render logs showed 9–12 `GET /github/status/...` requests **per second** during analysis. The indexing task never progressed.

**Root Cause:** React frontend used `setInterval(checkStatus, 2000)`. When the browser tab was in the background, timers got throttled, and when the user returned, all throttled requests fired simultaneously. On a 0.1 CPU core, this consumed 100% CPU — leaving zero cycles for the background indexing thread.

```mermaid
graph TD
    FE["React Frontend"] -->|"Every 2 seconds"| API["GET /status"]
    API -->|"9-12 req/sec flood"| CPU["Render CPU (0.1 core)"]
    CPU -->|"100% busy with HTTP"| BG["Background thread starved"]
```

**Solution:** Replaced with exponential backoff — polling interval grows from 2s → 4s → 6s → 8s → 10s (capped). Reduces steady-state load by 80%.

---

### Problem 4: Stale Redis Status After Deploys

**Symptom:** After deploying a new version, the frontend showed a permanent loading spinner. The Analyze button was disabled.

**Root Cause:** When Render restarts the container, the background task is killed instantly. The Redis key `status:analyze:{username}` stays at `"processing"` forever, and the frontend dutifully keeps polling it, never showing the input form.

**Solution:** Status keys have a 1-hour TTL so they eventually expire. For immediate recovery: `redis_client.delete("status:analyze:{username}")`.

---

### Problem 5: Vercel Frontend Not Hitting Render Backend

**Symptom:** Clicking "Analyze" did nothing. No request appeared in Render logs.

**Root Cause:** The API URL defaults to `http://localhost:8000` if `VITE_API_URL` is not set. Since Vite bakes env vars into the JavaScript at **build time**, you must set it in Vercel's dashboard **before building**, not after.

**Solution:** Added `VITE_API_URL=https://redis-rag.onrender.com` in Vercel environment variables and redeployed.

---

### Problem 6: Remote Debugging Without Log Access

**Symptom:** Needed to trace exactly where the server was stuck, but couldn't access Render logs programmatically.

**Solution:** Created a `log_to_redis()` helper that writes timestamped messages to a Redis list. Query from any machine:
```python
redis_client.lrange("logs:analyze:mujeebmasi", 0, -1)
# → ["[2026-07-21 14:48:19] Background task started...", "[14:48:21] Fetch complete..."]
```

---

## Important Things to Keep in Mind

### Embedding & AI APIs

| Do This | Don't Do This | Why |
|---------|---------------|-----|
| Use **direct REST API calls** (`httpx.post`) to Google Gemini | Use `langchain-google-genai` or `google-genai` SDK | SDKs deadlock on non-GCP platforms due to metadata server checks |
| **Always set `timeout=30.0`** on every HTTP call | Leave timeouts as default/infinite | One hung API call can freeze your entire background task forever |
| **Batch embed** with `batchEmbedContents` (up to 32 chunks per call) | Embed one text at a time | 5x faster due to reduced network round-trips |
| **Cache by Git SHA** — skip repos whose README hasn't changed | Re-embed everything on every analysis | Re-runs complete in <1 second instead of minutes |
| Use **Groq** for the LLM (Llama 3.3 70B) | Self-host a model on free-tier servers | Free tier gives insanely fast inference; self-hosting needs expensive GPUs |

### Free-Tier Cloud Deployment

| Do This | Don't Do This | Why |
|---------|---------------|-----|
| **Eliminate heavy imports** — replace `langchain_text_splitters` with pure Python | Lazy-load heavy libraries | Lazy-loading delays the freeze but doesn't prevent it. Under CPU starvation, a 4-second import can block for minutes |
| Use **exponential backoff** for polling (2s → 4s → 8s → 10s) | Use fixed `setInterval(fn, 2000)` | Fixed polling floods the server and starves background tasks of CPU |
| **Set TTLs on all Redis keys** (status, OTP, logs) | Rely on manual cleanup | Without TTLs, orphaned keys accumulate and hit free-tier memory limits |
| Use `print(..., flush=True)` for logging | Use regular `print()` | Python's stdout is block-buffered on Render — logs won't appear without `flush=True` |
| Design background tasks for **abrupt termination** | Assume tasks will always complete cleanly | Container restarts kill tasks instantly with no cleanup |

### Frontend + Backend Deployment

| Do This | Don't Do This | Why |
|---------|---------------|-----|
| Set `VITE_API_URL` in Vercel dashboard, then **redeploy** | Change the env var and assume it takes effect | Vite bakes env vars at **build time** — changing them requires a new build |
| Use **`CORS allow_credentials=False`** with `allow_origins=["*"]` | Use `allow_credentials=True` with wildcard origins | Browsers block this combination — CORS errors will silently kill all requests |
| Add a "force re-analyze" option for stale states | Assume the UI will always recover | If the backend restarts mid-task, the status is stuck at `"processing"` — the user needs a manual escape hatch |

### Redis & Database

| Do This | Don't Do This | Why |
|---------|---------------|-----|
| Use **`connect_timeout=10`** on PostgreSQL connections | Use default (infinite) timeout | Serverless databases (Neon) have cold starts — hanging connections block entire FastAPI startup |
| Enable **Single-User Mode** on free-tier Redis | Let multiple users' vectors accumulate | Free Redis instances have ~30MB limits; a single user's embeddings can use 5–10MB |
| Use **`log_to_redis()`** for remote debugging | Rely solely on `print()` / `logger.info()` | Redis logs survive container restarts and can be queried from any machine |
| Delete old vectors **before** inserting new ones | Append new vectors alongside old ones | Prevents duplicate/stale chunks from appearing in search results |

---

## Key Concepts (Quick Reference)

### What is RAG?
**Retrieval-Augmented Generation.** Instead of asking the LLM to answer from memory (which can hallucinate), we first search a database for relevant documents, then give those documents as context to the LLM. This grounds the answer in real data.

### What are Vector Embeddings?
An embedding model converts text into a list of numbers (e.g., `[0.01, -0.03, 0.7, ...]`). Similar text produces similar numbers. By comparing these number lists (using cosine similarity), we can find text that is semantically related — even if the exact words are different. Google Gemini produces 3072-dimensional vectors.

### How Does Redis Vector Search Work?
Redis Stack includes the RediSearch module, which can index vector fields inside Redis Hashes. When you search, it performs K-Nearest Neighbors (KNN) with cosine distance directly in memory — finding the most similar chunks in fractions of a millisecond.
