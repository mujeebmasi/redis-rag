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

When deploying to cloud platforms with constrained resources (such as **Render's Free Tier**, which limits memory to **512MB RAM**), running heavy machine learning frameworks locally in the container presents significant challenges. We implemented two critical optimizations to ensure our application runs stably in production with a tiny memory footprint.

### 1. Lazy-Loading Imports (Deferred Loading)
By default, importing large machine learning and AI orchestration packages (like PyTorch/`torch`, `sentence-transformers`, or LangChain) at the module level in Python initializes background runtimes and caches that can consume **400MB+ of RAM** immediately on app boot. This leads to Out of Memory (OOM) silent crashes during server startup, preventing Uvicorn from binding to the assigned port.

We restructured the codebase to utilize **Lazy Loading (Deferred Importing)**:
- Heavy library imports (like `RecursiveCharacterTextSplitter`, `ChatGroq`, `ChatPromptTemplate`, and `StrOutputParser`) were moved **inside** the functions where they are executed.
- Uvicorn startup completes in **under 2 seconds**, utilizing only **~50MB of RAM** (a 90% reduction).
- Health checks pass instantly, and services deploy without port scan timeouts.

### 2. Dual-Mode Embeddings (Local vs. Cloud API)
To completely prevent the heavy PyTorch runtime from loading in production, the application detects the environment and changes how it processes embeddings:
- **Local Mode (Offline)**: If running locally without environment-level cloud triggers, the app loads `HuggingFaceEmbeddings` locally using the CPU and model weights, ensuring the app remains 100% functional offline without external APIs.
- **Production Mode (Render)**: If the system detects it is running on Render (`os.getenv("RENDER") == "true"`) or if a Hugging Face Hub token is present, it routes vector generation to a custom, lightweight `HuggingFaceAPIEmbeddings` client. This client generates the exact same **384-dimensional vectors** by making HTTP calls to the **Hugging Face Cloud Inference API** via `httpx`.
- This architecture keeps the production memory footprint consistently low while preserving local, self-hosted offline execution.

---

## Key Technical Concepts

### Retrieval-Augmented Generation (RAG)
Instead of asking an LLM to answer questions purely from its pre-trained parameters (which can lead to hallucinations), a RAG pipeline first queries a vector database for documents related to the question. These relevant context snippets are appended to the LLM's prompt, instructing the model to synthesize a factually accurate answer grounded in the retrieved documentation.

### Vector Embeddings
An embedding model converts text into a high-dimensional vector of floating-point numbers. In this vector space, the geometric distance (e.g., Cosine distance) between two vectors corresponds to the semantic similarity of their respective texts. The `sentence-transformers/all-MiniLM-L6-v2` model maps text chunks to 384-dimensional vectors.

### In-Memory Vector Search
Redis Stack utilizes the RediSearch module to build indexes on Vector fields within stored Redis Hashes. It performs K-Nearest Neighbors (KNN) searches directly in memory, calculating the similarity score between a query vector and the index in fractions of a millisecond.
