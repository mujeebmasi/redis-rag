# 🚀 RedisRAG — AI Powered GitHub Profile Analyzer

RedisRAG is a full-stack backend application that lets you **analyze any GitHub profile** and then **chat with an AI** about their projects using Retrieval-Augmented Generation (RAG).

It fetches repositories, extracts README files, generates semantic embeddings, stores them in a Redis Vector Database, and uses Google Gemini to answer natural language questions about the developer's work.

> **Built as a learning project** — every file is well-documented with comments explaining *why* things work, not just *what* they do.

---

## ✨ What It Does

### 🔐 Authentication
| Feature | How It Works |
|---|---|
| Email OTP | 6-digit code sent via Gmail SMTP |
| Redis Cache | OTP stored with 5-minute TTL |
| PostgreSQL | User accounts persisted after first login |
| JWT Tokens | Stateless auth for all protected routes |

### 🧠 AI Analysis
| Feature | How It Works |
|---|---|
| GitHub Fetching | Profile + repos + READMEs via GitHub API |
| Text Chunking | READMEs split into ~250 word chunks |
| Embeddings | Google `text-embedding-004` model |
| Vector Search | Redis Vector Database (RediSearch) |
| AI Chat | Google Gemini LLM with retrieved context |

---

## 🏗️ Architecture

```
Client (Swagger UI / Frontend / cURL)
│
▼
FastAPI Backend (:8000)
│
├── /auth/*  ─── Authentication ──── Redis (OTP) + PostgreSQL (Users)
│
├── /github/* ── GitHub Service ──── GitHub API → Embeddings → Redis Vector DB
│
└── /chat    ─── RAG Pipeline ────── Redis Vector Search → Gemini LLM → Answer
```

---

## 📂 Project Structure

```
backend/
│
├── app/
│   ├── api/                    # Route handlers (HTTP layer)
│   │   ├── auth.py             # /auth/send-otp, /auth/verify-otp, /auth/me
│   │   ├── github.py           # /github/analyze
│   │   └── chat.py             # /chat
│   │
│   ├── core/                   # Shared infrastructure
│   │   ├── config.py           # Centralized settings (pydantic-settings)
│   │   ├── auth.py             # JWT auth dependency (reused by all protected routes)
│   │   └── redis_client.py     # Redis connection
│   │
│   ├── db/                     # Database layer
│   │   ├── database.py         # SQLAlchemy engine + session
│   │   ├── models.py           # User model
│   │   ├── crud.py             # Create/Read operations
│   │   └── dependencies.py     # DB session dependency
│   │
│   ├── services/               # Business logic (the real work happens here)
│   │   ├── otp_service.py      # Generate random OTP
│   │   ├── email_service.py    # Send emails via Gmail SMTP
│   │   ├── jwt_service.py      # Create & verify JWT tokens
│   │   ├── github_service.py   # Fetch data from GitHub API
│   │   ├── embedding_service.py # Chunk text → embeddings → Redis Vector Store
│   │   └── rag_service.py      # Semantic search → LLM → answer
│   │
│   ├── schemas/                # Request/Response validation (Pydantic)
│   │   ├── auth.py
│   │   ├── github.py
│   │   └── chat.py
│   │
│   └── main.py                 # FastAPI app entry point
│
├── docker-compose.yml          # Redis Stack + PostgreSQL
├── requirements.txt            # Python dependencies
└── .env                        # Environment variables (not committed)
```

---

## ⚙️ Setup

### Prerequisites
- Python 3.11+
- Docker Desktop
- Gmail account with [App Password](https://support.google.com/accounts/answer/185833)
- [Google AI API Key](https://aistudio.google.com/apikey) (free tier)

### 1. Clone & Setup

```bash
git clone https://github.com/yourusername/RedisRAG.git
cd RedisRAG
```

### 2. Start Docker Services

```bash
docker compose up -d
```

This starts:
- **Redis Stack** on port `6379` (Redis + RediSearch for vector search)
- **PostgreSQL** on port `5432`

### 3. Create Virtual Environment

```bash
cd backend
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

### 4. Install Dependencies

```bash
pip install -r requirements.txt
```

### 5. Configure Environment

Edit the `.env` file in the project root:

```env
EMAIL_ADDRESS=your-email@gmail.com
EMAIL_PASSWORD=your-gmail-app-password

DATABASE_URL=postgresql://postgres:admin123@localhost:5432/redisrag

REDIS_HOST=localhost
REDIS_PORT=6379

SECRET_KEY=your-secret-key

GOOGLE_API_KEY=your-google-api-key
```

### 6. Run the Server

```bash
uvicorn app.main:app --reload
```

📖 **Swagger Docs**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

## 🔌 API Reference

### Authentication

#### Send OTP
```http
POST /auth/send-otp
Content-Type: application/json

{
    "email": "user@example.com"
}
```

#### Verify OTP & Get Token
```http
POST /auth/verify-otp
Content-Type: application/json

{
    "email": "user@example.com",
    "otp": "123456"
}
```

Response:
```json
{
    "verified": true,
    "message": "OTP verified successfully",
    "access_token": "eyJhbGciOiJIUzI1NiIs..."
}
```

#### Get Current User
```http
GET /auth/me
Authorization: Bearer <JWT_TOKEN>
```

---

### GitHub Analysis

#### Analyze Profile
```http
POST /github/analyze
Authorization: Bearer <JWT_TOKEN>
Content-Type: application/json

{
    "username": "torvalds"
}
```

This will:
1. Fetch the user's profile and repositories from GitHub
2. Download all README files
3. Split them into chunks and generate embeddings
4. Store everything in Redis Vector Database

---

### AI Chat

#### Ask a Question
```http
POST /chat
Authorization: Bearer <JWT_TOKEN>
Content-Type: application/json

{
    "username": "torvalds",
    "question": "What programming languages are used in the projects?"
}
```

Response:
```json
{
    "answer": "Based on the repositories, the primary language used is C...",
    "sources": ["linux", "subsurface-for-dirk"]
}
```

---

## 🔄 How It All Works

### Authentication Flow
```
User enters email
        ↓
Generate 6-digit OTP
        ↓
Store OTP in Redis (5 min TTL)
        ↓
Send OTP via Gmail SMTP
        ↓
User submits OTP
        ↓
Verify against Redis
        ↓
Create user in PostgreSQL (if new)
        ↓
Return JWT token
        ↓
✅ Authenticated — use token for all requests
```

### RAG Workflow
```
GitHub Username
        ↓
Fetch Repositories (GitHub API)
        ↓
Download README Files
        ↓
Split into Chunks (1000 chars, 200 overlap)
        ↓
Generate Embeddings (Google text-embedding-004)
        ↓
Store in Redis Vector Database
        ↓
User asks a question
        ↓
Convert question → embedding → find similar chunks
        ↓
Send chunks + question to Gemini LLM
        ↓
AI generates grounded answer
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Framework | FastAPI |
| Language | Python 3.11+ |
| ORM | SQLAlchemy |
| Validation | Pydantic |
| Database | PostgreSQL |
| Cache & Vectors | Redis Stack (RediSearch) |
| Auth | JWT + Email OTP |
| AI Framework | LangChain |
| Embeddings | Google text-embedding-004 |
| LLM | Google Gemini 2.0 Flash |
| HTTP Client | httpx |
| DevOps | Docker Compose |

---

## 💡 Key Concepts (For Learning)

### What is RAG?
**Retrieval-Augmented Generation** = instead of asking an AI to answer from memory (which can be wrong), we first *retrieve* relevant documents, then give them to the AI as context. This grounds the AI's answers in real data.

### What are Embeddings?
A list of numbers (vector) that represents the *meaning* of text. Similar text → similar vectors. This enables "semantic search" — searching by meaning, not just keywords.

### Why Redis for Vectors?
Redis with the RediSearch module supports vector similarity search, making it extremely fast for finding relevant text chunks. It's also already used for OTP caching, so one less service to manage.

### Why Chunk Documents?
LLMs have context limits, and large documents contain many topics. Smaller chunks (with overlap to avoid cutting sentences) give more precise search results.

---

## 👨‍💻 Author

**Abdul Mujeeb** — Backend Developer • AI Engineer • Generative AI Enthusiast

---

⭐ If you found this project useful, consider giving it a star!
