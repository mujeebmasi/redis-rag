# RedisRAG - AI Powered GitHub Profile Analyzer

RedisRAG is a full-stack application designed to analyze public GitHub profiles and enable interactive chat sessions about a developer's projects. It uses Retrieval-Augmented Generation (RAG) to ground the answers.

The system retrieves repositories, extracts README files, splits them into semantic chunks, and generates vector embeddings using a local HuggingFace model. These embeddings are stored in a Redis Vector Database. When a user asks a question, a similarity search is performed in Redis, and the most relevant README segments are sent as context to the Groq LLM (Llama 3) to generate an accurate, source-cited response.

---

## Architecture

The system's architecture is divided into two main pipelines: GitHub Profile Ingestion & Embedding, and Semantic Search & RAG Chat.

### 1. Ingestion & Embedding Pipeline
This flow describes how developer READMEs are fetched, chunked, embedded locally, and stored in Redis.

```mermaid
graph LR
    subgraph Ingestion["1. Data Ingestion"]
        Client[Client Browser] -->|Post Ingest Request| FastAPI[FastAPI Backend]
        FastAPI -->|Fetch Profile & READMEs| GitHub[GitHub API]
        GitHub -->|Return README Text| FastAPI
    end
    
    subgraph Embedding["2. Embedding & Storage"]
        FastAPI -->|Split README into chunks| Chunks[Text Chunks]
        Chunks -->|Send chunks| HF[Local HuggingFace Model]
        HF -->|Return 384-dim vectors| FastAPI
        FastAPI -->|Store Vectors & Metadata| Redis[Redis Vector DB]
    end
```

### 2. Semantic Search & RAG Chat Pipeline
This flow describes how user questions are answered using vector similarity search and Groq LLM synthesis.

```mermaid
graph LR
    subgraph Query["1. Query Processing"]
        User[Client Browser] -->|Submit Question| FastAPI[FastAPI Backend]
        FastAPI -->|Send query text| HF[Local HuggingFace Model]
        HF -->|Return query vector| FastAPI
    end
    
    subgraph Retrieval["2. RAG & Response Generation"]
        FastAPI -->|KNN Cosine Search| Redis[Redis Vector DB]
        Redis -->|Return Top-K Chunks| FastAPI
        FastAPI -->|Send Prompt + Context Chunks| Groq[Groq LLM]
        Groq -->|Return Grounded Answer| FastAPI
        FastAPI -->|Return Answer + Source citations| User
    end
```

---

## Features

### Authentication and User Management
- **Email OTP Verification**: Users log in by requesting a one-time passcode sent to their email.
- **OTP Caching**: Passcodes are cached in Redis with a 5-minute time-to-live (TTL) to ensure secure, temporary verification.
- **Persistent User Accounts**: Verified users are persisted in a PostgreSQL database after their first login.
- **JSON Web Tokens (JWT)**: Stateless token authentication protects all core API endpoints.

### Ingestion and Embedding Pipeline
- **GitHub Scraping**: Public repository metadata and README files are fetched dynamically.
- **Recursive Chunking**: README files are split into overlapping segments to fit token limitations and preserve semantic context.
- **Local HuggingFace Embeddings**: Vectors are generated locally using the `sentence-transformers/all-MiniLM-L6-v2` model, removing external API dependencies and rate limits.
- **Dynamic Schema Matching**: The backend automatically detects the vector dimension of the active HuggingFace model. If a dimension mismatch is found with the existing Redis search index, the index is deleted and recreated dynamically.

### Search and Generative AI
- **Redis Vector Search**: Cosine similarity is computed in-memory using RediSearch (KNN Flat algorithm) to retrieve the most relevant README segments.
- **Groq LLM Integration**: Generates final grounded responses using the Llama 3 model family, ensuring fast and accurate answers.
- **Source Attributions**: Every chat response details the specific repositories referenced in the context.

---

## Project Structure

```
.
├── backend/
│   ├── app/
│   │   ├── api/             # Route handlers (auth, github ingestion, chat)
│   │   ├── core/            # Configuration, Redis and JWT clients
│   │   ├── db/              # SQLAlchemy models, sessions, and CRUD operations
│   │   ├── schemas/         # Pydantic request and response schemas
│   │   └── services/        # Service layer (OTP, email, GitHub, embeddings, RAG)
│   ├── requirements.txt     # Python backend dependencies
│   └── main.py              # Application entry point
├── frontend/
│   ├── src/                 # React frontend application
│   ├── package.json         # Node.js dependencies and scripts
│   └── vite.config.ts       # Vite configuration
├── docker-compose.yml       # Docker configuration for Redis Stack and PostgreSQL
└── .env                     # Configuration file (not committed to git)
```

---

## Setup and Installation

### Prerequisites
- Python 3.11 or higher
- Node.js 18 or higher
- Docker and Docker Compose
- Gmail SMTP credentials or access to an SMTP mail server

### 1. Run Databases with Docker
Start Redis Stack (which includes the RediSearch and RedisJSON modules) and PostgreSQL:
```bash
docker compose up -d
```
This maps:
- Redis Stack to port `6379`
- RedisInsight UI to port `8001`
- PostgreSQL to port `5432`

### 2. Configure Environment Variables
Create a `.env` file in the root directory:
```env
EMAIL_ADDRESS=your-email@gmail.com
EMAIL_PASSWORD=your-smtp-app-password

DATABASE_URL=postgresql://postgres:admin123@localhost:5432/redisrag

REDIS_HOST=localhost
REDIS_PORT=6379

SECRET_KEY=your-jwt-secret-key
GITHUB_TOKEN=your-github-personal-access-token

GROQ_API_KEY=your-groq-api-key

HF_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
HUGGINGFACEHUB_API_TOKEN=your-huggingface-token
HF_TOKEN=your-huggingface-token
```

### 3. Start Backend Services
Navigate to the `backend` folder, set up a virtual environment, install dependencies, and run the server:
```bash
cd backend
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --reload
```
The backend API documentation is available at: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

### 4. Start Frontend Application
Navigate to the `frontend` directory, install packages, and launch the development server:
```bash
cd ../frontend
npm install
npm run dev
```
The client dashboard runs at: [http://localhost:5173/](http://localhost:5173/).

---

## API Reference

### Authentication

#### Request OTP
- **Endpoint**: `POST /auth/send-otp`
- **Body**:
  ```json
  {
    "email": "user@example.com"
  }
  ```

#### Verify OTP
- **Endpoint**: `POST /auth/verify-otp`
- **Body**:
  ```json
  {
    "email": "user@example.com",
    "otp": "123456"
  }
  ```
- **Response**:
  ```json
  {
    "verified": true,
    "message": "OTP verified successfully",
    "access_token": "eyJhbGciOiJIUzI1Ni..."
  }
  ```

### GitHub Profile Analysis

#### Ingest Profile
- **Endpoint**: `POST /github/analyze`
- **Headers**: `Authorization: Bearer <access_token>`
- **Body**:
  ```json
  {
    "username": "torvalds"
  }
  ```

#### Check Ingestion Status
- **Endpoint**: `GET /github/status/{username}`
- **Headers**: `Authorization: Bearer <access_token>`
- **Response Statuses**: `not_started`, `processing`, `completed`, `failed`

### RAG Chat

#### Submit Question
- **Endpoint**: `POST /chat`
- **Headers**: `Authorization: Bearer <access_token>`
- **Body**:
  ```json
  {
    "username": "torvalds",
    "question": "What primary language is used in the linux repository?"
  }
  ```
- **Response**:
  ```json
  {
    "answer": "The primary language used in the linux repository is C...",
    "sources": ["linux"]
  }
  ```

---

## Production & Deployment Optimizations

When deploying to cloud platforms with constrained resources (such as **Render's Free Tier**, which limits memory to **512MB RAM**), running heavy machine learning frameworks locally in the container presents significant challenges. We implemented several critical optimizations to ensure our application runs stably in production with a tiny memory footprint, high resilience, and robust error handling.

### 1. Dual-Mode Embedding Architecture (Mermaid Flow)
To completely prevent the heavy PyTorch runtime from loading in production, the application dynamically detects the environment and switches the vector search path:

```mermaid
graph TD
    subgraph Env["1. Environment Detection"]
        Start[App Ingestion/Query Request] --> Check{Is Render or Token Configured?}
    end

    subgraph Production["2. Production Mode (Render Cloud)"]
        Check -->|Yes / RENDER=true| HF_API[Lightweight HTTP Client]
        HF_API -->|POST Request| HF_Cloud[Hugging Face Cloud Inference API]
        HF_Cloud -->|Return 384-dim Vectors| Out_Prod[Vector Search / Storage]
    end

    subgraph Development["2. Local Mode (Offline Dev)"]
        Check -->|No / Local Environment| Lazy_Load[Lazy Load sentence-transformers & PyTorch]
        Lazy_Load -->|Run Model locally on CPU| CPU_Compute[Local CPU Vector Computation]
        CPU_Compute -->|Return 384-dim Vectors| Out_Dev[Vector Search / Storage]
    end

    style Production fill:#d4edda,stroke:#28a745,stroke-width:2px
    style Development fill:#fff3cd,stroke:#ffc107,stroke-width:2px
```

* **Local Mode (Offline)**: If running locally without production triggers, the app loads `HuggingFaceEmbeddings` locally using the CPU and model weights, ensuring the app remains 100% functional offline without external APIs.
* **Production Mode (Render)**: If the system detects it is running on Render (`os.getenv("RENDER") == "true"`) or if a Hugging Face Hub token is present, it routes vector generation to a custom, lightweight `HuggingFaceAPIEmbeddings` client. This client generates the exact same **384-dimensional vectors** by making HTTP calls to the **Hugging Face Cloud Inference API** via `httpx`.
* This architecture keeps the production memory footprint consistently low while preserving local, self-hosted offline execution.

### 2. Lazy-Loading Imports (Deferred Loading)
By default, importing large machine learning and AI orchestration packages (like PyTorch/`torch`, `sentence-transformers`, or LangChain) at the module level in Python initializes background runtimes and caches that can consume **400MB+ of RAM** immediately on app boot. This leads to Out of Memory (OOM) silent crashes during server startup, preventing Uvicorn from binding to the assigned port.

We restructured the codebase to utilize **Lazy Loading (Deferred Importing)**:
- Heavy library imports (like `RecursiveCharacterTextSplitter`, `ChatGroq`, `ChatPromptTemplate`, and `StrOutputParser`) were moved **inside** the functions where they are executed.
- Uvicorn startup completes in **under 2 seconds**, utilizing only **~50MB of RAM** (a 90% reduction).
- Health checks pass instantly, and services deploy without port scan timeouts.

### 3. Database Connection Resilience (connect_timeout)
During server start, FastAPI runs database setup tasks (like verifying/creating PostgreSQL tables). If PostgreSQL experiences a cold start, network handshake delay, or temporary sleep phase (common on serverless databases like Neon), the database connection attempt can hang indefinitely.
- We added `connect_timeout: 10` to SQLAlchemy's PostgreSQL engine connection arguments.
- If a connection attempt takes longer than 10 seconds, it raises an exception, which is caught gracefully. This prevents a database hang from blocking the entire FastAPI lifespan boot sequence and causing a Render port scan timeout.

### 4. Browser CORS Stack Standardization
Because the RAG application uses Bearer Token authentication headers rather than Session Cookies, we standardized the FastAPI CORS middleware settings:
- Changed `allow_credentials=False` for browser compatibility when wildcard origins (`allow_origins=["*"]`) are used. This allows any frontend client to make cross-origin API calls without security exceptions.

### 5. Safe UTF-8 README base64 Decoding
GitHub API returns repository README files as base64-encoded bytes. If a repository has non-UTF-8 characters, binary files, or images in its README, typical string decoding crashes the entire profile ingestion pipeline.
- We implemented `errors="replace"` in the byte-decoding string logic of `github_service.py` to ensure that ingestion never crashes on non-standard Unicode characters.

### 6. Resend Email API Integration (Bypassing SMTP Blocks)
Standard outbound SMTP connections (port 465) to Gmail are typically blocked by cloud firewalls to prevent spam, causing direct email delivery to fail or hang on Render.
- We integrated the **Resend Email API** via `httpx` POST requests (port 443/HTTPS), which are never blocked by cloud firewalls.
- We added a fallback sequence: if a `RESEND_API_KEY` is present, it routes the OTP verification mail through Resend's API. If not, it falls back to the local Gmail SMTP configuration, and if both fail/are unconfigured, it logs the generated OTP directly to the container console logs for easy debugging.

### 7. High-Performance Indexing Pipeline & Caching (Claude Optimization)
When chunking and embedding generation are run synchronously for dozens of repositories, ingestion becomes a major bottleneck. Under resource-constrained production settings (like Render's Free Tier), this frequently triggers timeout limits or triggers OOM (Out of Memory) crash terminations.

Using the Claude agent, we refactored the entire indexing pipeline with 7 key performance enhancements:

```mermaid
graph TD
    Request[POST /github/analyze] --> Fetch[1. Fetch Profile & Repositories]
    Fetch --> RankFilter[2. Filter & Rank Repositories]
    RankFilter --> LoopStart[3. Stream Selected Repositories]
    
    subgraph Stream["Per-Repository Processing Loop"]
        LoopStart --> CacheCheck{4. Check SHA Cache in Redis}
        CacheCheck -->|Match| CacheHit[5. Skip & Report Cached]
        CacheCheck -->|Mismatch| Cleanup[6. Delete Stale Vectors]
        Cleanup --> Chunk[7. Chunk README Text]
        Chunk --> Embed[8. Embed Batch with Retry]
        Embed --> PipelineWrite[9. Write to Redis Pipeline]
        PipelineWrite --> CacheUpdate[10. Cache README SHA]
    end
    
    CacheHit --> NextRepo[11. Move to Next Repo]
    CacheUpdate --> NextRepo
    NextRepo --> Complete[12. Complete & Cache Final Metadata]
    
    style CacheHit fill:#d4edda,stroke:#28a745,stroke-width:1px
    style Embed fill:#f8d7da,stroke:#dc3545,stroke-width:1px
```

* **Smart Repository Filtering & Ranking**: Instead of wasting compute resources embedding low-value forks or archived projects, the system ranks repositories based on a popularity score (`stars + forks`). It restricts ingestion to the top `MAX_REPOS_TO_INDEX` (default 15) and skips repos with empty or boilerplate READMEs shorter than `MIN_README_LENGTH` characters.
* **SHA-Based Incremental Caching**: To prevent redundant embedding generation, the system saves the Git file SHA for each indexed README inside Redis (`cache:embed:{username}:{repo}`). On subsequent ingestion requests, the system compares latest SHA values; if matching, it skips chunking and model calls completely. Re-runs finish in **under 1 second** instead of minutes.
* **Per-Repository Streaming (Memory Capping)**: Instead of buffering all chunks from all repositories in memory before storage, the pipeline streams repositories sequentially. Chunks are generated, embedded, and flushed to Redis on a per-repo basis, capping peak memory usage to `O(single_repo)` rather than `O(all_repos)`.
* **Configurable Tuning Parameters**: All ingestion thresholds are controlled through a centralized config module ([indexing_config.py](file:///d:/AI/redisrag/backend/app/core/indexing_config.py)), enabling fast adjustments of batch sizes, worker counts, timeouts, chunk overlaps, and ingestion limits.
* **Granular Status & Phase Tracking**: The API endpoint updates progress metrics into Redis throughout ingestion. Clients polling `/github/status/{username}` receive structured JSON detailing the current execution phase (`fetching`, `embedding`, `saving`, `completed`) along with exact statistics on chunks written, repos completed, and cache hits.
* **Robust Hugging Face API Fallbacks & Retries**: When calling the external Hugging Face Inference API for vector extraction, transient network failures (like HTTP 503 model-loading warmups or HTTP 429 rate-limits) are caught and automatically retried using exponential backoff (up to 3 times: 2s → 4s → 8s).
* **Stale Vector Garbage Collection**: To prevent vector pollution when a README's layout or chunk count changes, the pipeline locates and deletes any legacy Redis search records (`doc:readme:{username}:{repo}:*`) prior to inserting new ones.
* **Single-User Mode (Redis Memory Cap)**: If `SINGLE_USER_MODE = True` is configured in `indexing_config.py`, indexing a new user automatically sweeps Redis and purges vectors, SHA caches, and status logs belonging to any other user. This guarantees the Redis instance remains small, clean, and runs safely within free-tier resource bounds.

---


## Key Technical Concepts

### Retrieval-Augmented Generation (RAG)
Instead of asking an LLM to answer questions purely from its pre-trained parameters (which can lead to hallucinations), a RAG pipeline first queries a vector database for documents related to the question. These relevant context snippets are appended to the LLM's prompt, instructing the model to synthesize a factually accurate answer grounded in the retrieved documentation.

### Vector Embeddings
An embedding model converts text into a high-dimensional vector of floating-point numbers. In this vector space, the geometric distance (e.g., Cosine distance) between two vectors corresponds to the semantic similarity of their respective texts. The `sentence-transformers/all-MiniLM-L6-v2` model maps text chunks to 384-dimensional vectors.

### In-Memory Vector Search
Redis Stack utilizes the RediSearch module to build indexes on Vector fields within stored Redis Hashes. It performs K-Nearest Neighbors (KNN) searches directly in memory, calculating the similarity score between a query vector and the index in fractions of a millisecond.

---

## Deployment Debugging Chronicle

This section documents every production bug encountered while deploying RedisRAG to **Render** (backend) and **Vercel** (frontend), the exact root causes, and the solutions applied. Written as a reference for future deployments.

### Problem 1: Google GenAI SDK Deadlock on Render (GCP Metadata Server Hang)

**Symptom**: The background indexing task would hang indefinitely at `repos_done: 0` on Render. Locally, the same code completed in under 15 seconds. No error was thrown, no timeout fired — the process simply froze.

**Root Cause**: Google's official Python SDKs (`google-genai` and `langchain-google-genai`) include an **Application Default Credentials (ADC)** lookup at initialization. This feature detects whether the code is running inside Google Cloud Platform by sending HTTP requests to the **GCP Instance Metadata Server** at `http://169.254.169.254`. Since Render runs on AWS/GCP infrastructure but is _not_ a native GCP environment, these metadata requests never receive a response. The SDK blocks the thread waiting for a response, with internal timeouts of **2+ minutes per attempt** and multiple retries.

**Solution**: Replaced the `GoogleGenerativeAIEmbeddings` (from `langchain-google-genai`) with a custom `GeminiAPIEmbeddings` class that makes **direct REST API calls** to the Google Gemini endpoint using `httpx`:

```python
class GeminiAPIEmbeddings:
    """Direct REST client — bypasses SDK credential detection entirely."""

    def embed_documents(self, texts):
        response = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/{model}:batchEmbedContents?key={api_key}",
            json={"requests": [...]},
            timeout=30.0
        )
        return [e["values"] for e in response.json()["embeddings"]]
```

**Key Takeaway**: Never use Google's official Python SDKs on non-GCP cloud platforms for latency-sensitive background tasks. Direct REST calls are faster, lighter, and eliminate the metadata server deadlock entirely.

---

### Problem 2: `langchain_text_splitters` Import Freeze Under CPU Starvation

**Symptom**: The diagnostic Redis logs showed the background task reached `[1/8] Processing repository: advanced-whale-optimization-algorithm` but never advanced to `Split into X chunks`. The task appeared permanently frozen.

**Root Cause**: The text splitter was **lazy-imported** inside the function:
```python
def _get_text_splitter():
    from langchain_text_splitters import RecursiveCharacterTextSplitter  # 4+ second import
```

Importing `langchain_text_splitters` triggers a chain of heavy imports (LangChain core, Pydantic validators, regex engines). Locally this takes ~4 seconds, but on **Render's Free Tier (0.1 CPU core)**, under a simultaneous polling storm of 9–12 HTTP requests per second from the frontend, the background thread was **starved of CPU time**. The import never completed because the main thread consumed all available CPU cycles responding to status polling requests.

**Solution**: Replaced the entire `langchain_text_splitters` dependency with a **zero-dependency, pure-Python recursive text splitter** defined inline:

```python
def _split_text(text: str, chunk_size=None, chunk_overlap=None) -> list[str]:
    separators = ["\n\n", "\n", ". ", "! ", "? ", "; ", ", ", " ", ""]
    # ... recursive splitting logic with overlap
```

This function requires zero imports, runs in microseconds, and produces equivalent chunking output.

**Key Takeaway**: On resource-constrained containers, every `import` statement is a potential freeze point. Replace heavy library imports with lightweight inline implementations wherever possible.

---

### Problem 3: Frontend Polling Storm Starving Backend CPU

**Symptom**: Render logs showed the backend receiving 9–12 `GET /github/status/{username}` requests **per second** while the background indexing task was supposedly running. The task never made progress.

**Root Cause**: The React frontend used a fixed `setInterval(checkStatus, 2000)` (every 2 seconds) for status polling. However, modern browsers **throttle background tabs** to poll only once per minute. When the user switched back to the browser tab, all throttled timers fired simultaneously, creating a burst of requests. Combined with React Strict Mode (which double-mounts effects in development), and possible multiple open tabs, the Render server was overwhelmed.

On Render's Free Tier (0.1 CPU), handling 9+ HTTP requests/second consumed 100% of the available CPU, leaving **zero cycles for the background indexing thread** (which needs CPU for text splitting, HTTP calls to Gemini, and Redis writes).

**Solution**: Replaced fixed-interval polling with **exponential backoff**:

```typescript
// Polling interval: 2s → 4s → 6s → 8s → 10s (capped)
const getInterval = () => Math.min(2000 + pollCount * 2000, 10000);

let timeoutId: ReturnType<typeof setTimeout>;
const scheduleNext = () => {
    pollCount++;
    timeoutId = setTimeout(async () => {
        await checkStatus();
        scheduleNext();
    }, getInterval());
};
```

This reduces steady-state polling to 1 request every 10 seconds instead of 1 every 2 seconds — an **80% reduction** in server load.

**Key Takeaway**: Never use fixed-interval polling against a resource-constrained backend. Always implement exponential backoff or server-sent events (SSE).

---

### Problem 4: Stale Redis Status Keys After Container Restarts

**Symptom**: After deploying a new version on Render, the user refreshed the frontend and saw a permanent loading spinner. The "Analyze" button was disabled and unclickable. No `POST /github/analyze` request appeared in the Render logs.

**Root Cause**: When Render restarts the container for a new deployment, the running background task is **killed instantly** without any cleanup. The Redis key `status:analyze:{username}` remains stuck at `"status": "processing"` because the task never got to update it to `"failed"` or `"completed"`. When the new container boots and the frontend polls the status, it sees `"processing"` and stays in the loading state indefinitely, **disabling the Analyze button** in the UI.

**Solution**: The status keys have a 1-hour TTL (`ex=3600`), so they eventually expire. For immediate recovery, the stuck key can be deleted manually:

```python
redis_client.delete("status:analyze:{username}")
```

A future improvement would be to add a **startup cleanup hook** in FastAPI's lifespan that detects and clears any orphaned `"processing"` status keys when the server boots.

**Key Takeaway**: Background tasks on ephemeral containers must be designed for abrupt termination. Use TTLs on all status keys, and consider startup-time cleanup of orphaned state.

---

### Problem 5: Vercel Frontend Not Connecting to Render Backend

**Symptom**: The user deployed the frontend on Vercel and backend on Render separately. Clicking "Analyze" did nothing — no request appeared in the Render logs.

**Root Cause**: The frontend API base URL was configured as:
```typescript
const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
```

Without setting the `VITE_API_URL` environment variable in Vercel's dashboard, the production build defaulted to `http://localhost:8000`, causing all API calls to target the user's local machine instead of the deployed Render backend.

**Solution**: Added `VITE_API_URL=https://redis-rag.onrender.com` as an environment variable in Vercel's project settings, then triggered a **redeployment** (required because Vite embeds environment variables at build time, not runtime).

**Key Takeaway**: Vite environment variables (`VITE_*`) are embedded at **build time**, not runtime. After changing them in the hosting dashboard, you must trigger a full rebuild/redeployment.

---

### Problem 6: Remote Debugging Without Access to Server Logs

**Symptom**: We needed to see exactly which line of code the Render server was executing, but the Render dashboard logs scrolled away quickly and the user couldn't always provide timely screenshots.

**Root Cause**: Standard `print()` and `logger.info()` output only appears in the Render dashboard log viewer, which has limited scrollback and no programmatic access.

**Solution**: Implemented a **`log_to_redis()` helper** that writes timestamped diagnostic messages directly to a Redis list:

```python
def log_to_redis(username: str, message: str) -> None:
    key = f"logs:analyze:{username}"
    redis_client.rpush(key, f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}")
    redis_client.expire(key, 3600)
```

This allowed us to query the server's execution trace in real-time from any machine:
```python
redis_client.lrange("logs:analyze:mujeebmasi", 0, -1)
```

**Key Takeaway**: When debugging deployed services without direct log access, use your existing database (Redis, PostgreSQL) as a diagnostic log sink. It's faster and more reliable than coordinating screenshots.

---

## Important Things to Keep in Mind

A collection of best practices, optimal methods, and lessons learned from building and deploying this application. Use this as a checklist for any similar Python/FastAPI + React deployment.

### Embedding & AI API Best Practices

| Practice | Why |
|---|---|
| **Use direct REST API calls** instead of official SDKs for embedding models | SDKs include cloud-detection logic that deadlocks on non-native platforms (e.g., Google GenAI SDK on Render). Direct `httpx` calls with explicit timeouts are faster, lighter, and predictable. |
| **Always set explicit timeouts** on all HTTP calls | Use `timeout=30.0` on every `httpx.post()` call. Without timeouts, a single hung API call can freeze the entire background task forever. |
| **Batch embedding requests** using `batchEmbedContents` | A single batch request for 5 chunks is ~5x faster than 5 individual requests due to reduced network round-trips and API overhead. |
| **Cache embeddings by content hash (SHA)** | Store the Git SHA of each README alongside its embeddings. On re-analysis, compare SHAs first — if unchanged, skip the entire embed-and-store cycle. Re-runs complete in under 1 second. |

### Free-Tier Cloud Deployment (Render, Railway, Fly.io)

| Practice | Why |
|---|---|
| **Eliminate heavy imports** (`langchain`, `torch`, `transformers`) | On a 0.1 CPU core, importing PyTorch alone takes 10–30 seconds and consumes 400MB+ RAM. Replace with lightweight alternatives or API calls. |
| **Never use fixed-interval polling** from the frontend | Use exponential backoff (2s → 4s → 8s → 10s). Fixed 2-second polling floods the server and starves background tasks of CPU. |
| **Design background tasks for abrupt termination** | Containers restart without warning on deploys. Use TTLs on all Redis status keys. Add startup cleanup hooks to clear orphaned `"processing"` states. |
| **Monitor memory usage** | Free tiers typically cap at 512MB. If your app approaches this limit, the platform silently throttles CPU or force-restarts the container with no error message. |
| **Use `print(..., flush=True)`** for log visibility | On Render, Python's stdout is block-buffered by default. Without `flush=True`, print statements may never appear in the dashboard logs. |

### Frontend-Backend Deployment

| Practice | Why |
|---|---|
| **Set `VITE_API_URL` in your hosting dashboard** | Vite embeds env vars at build time. If not set, the frontend defaults to `localhost:8000` and all API calls silently fail in production. |
| **Redeploy after changing env vars** | Changing a Vite environment variable in Vercel/Netlify requires a full rebuild. The old JavaScript bundle still contains the previous value until rebuilt. |
| **Use exponential backoff for status polling** | Prevents CPU starvation on free-tier backends and avoids browser tab throttling artifacts. |
| **Handle stale UI state after server restarts** | If the backend restarts mid-task, the frontend may be stuck showing a loading spinner. Consider adding a "force re-analyze" button or auto-detecting stale states (e.g., if status hasn't changed for 60 seconds, show a retry option). |

### Redis & Database

| Practice | Why |
|---|---|
| **Always use TTLs on ephemeral keys** | Status keys, OTP codes, and diagnostic logs should all expire. Without TTLs, orphaned keys accumulate and consume memory on free-tier Redis instances. |
| **Use `log_to_redis()` for remote debugging** | When you can't access server logs directly, write diagnostic checkpoints to a Redis list. Query them from any machine connected to the same Redis instance. |
| **Single-User Mode for free-tier Redis** | Free Redis instances have ~30MB limits. Enable `SINGLE_USER_MODE=True` to automatically purge previous users' vectors when a new profile is analyzed. |
| **Use `connect_timeout` on database connections** | Serverless databases (like Neon) have cold starts. Without a timeout, a sleeping database can block your entire FastAPI startup indefinitely. |

### General Python Backend

| Practice | Why |
|---|---|
| **Replace lazy imports with zero-dependency alternatives** | Lazy-loading only delays the freeze — it doesn't prevent it. Under CPU starvation, a 4-second import can block for minutes. Pure-Python implementations with no imports are always instant. |
| **Use `asyncio.run()` carefully in background threads** | `asyncio.run()` creates a new event loop and closes it. This is safe in a background thread but must not be called from an existing async context. |
| **Log exceptions to persistent storage** | `logger.exception()` only writes to stdout, which may be lost on container restarts. Write critical errors to Redis or PostgreSQL so they survive restarts and can be queried later. |
| **Test the deployed endpoint directly** | Don't rely solely on the frontend. Use `httpx` or `curl` to call your deployed API endpoints directly to isolate whether issues are frontend or backend. |
