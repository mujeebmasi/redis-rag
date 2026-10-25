"""
RAG Service
===========
Retrieval-Augmented Generation — the "brain" of the AI chat.

What is RAG?
- Instead of asking the LLM to answer from memory (which can hallucinate),
  we RETRIEVE relevant documents first, then give them as context to the LLM.
- This grounds the AI's answers in real data (the GitHub READMEs).

Flow:
1. User asks: "What projects use FastAPI?"
2. Check this profile has been indexed (no data → ask the user to analyze first)
3. Convert the question into an embedding vector
4. Search Redis for the most similar README chunks (embedding_service.search_similar)
5. Build a prompt with two kinds of context:
   - a profile overview (every indexed repo with language, stars, description)
   - the README chunks found by vector search
6. The LLM reads the context and generates an accurate answer
7. We return the answer + source repos

Why the profile overview?
- Vector search only returns the 5 closest chunks. Questions like
  "list all their projects" or "which languages do they use" need the
  whole list, which the overview provides in a few hundred tokens.
"""

import json
import logging

from app.core.config import settings
from app.core.errors import UserFacingError
from app.core.redis_client import redis_client
from app.services.embedding_service import count_chunks, search_similar

logger = logging.getLogger(__name__)


class LLMError(UserFacingError):
    """The language model (Groq) failed."""


# ── LLM (Large Language Model) ──────────────────────────────────────
# Using Groq (default model: OpenAI gpt-oss-120b) — extremely fast inference.
# The model is a setting (GROQ_MODEL) because Groq retires models over time.
# temperature=0.3 means slightly creative but mostly factual answers.


def _get_llm():
    """Create the LLM instance (Groq, model set by GROQ_MODEL)."""
    if not settings.GROQ_API_KEY:
        raise LLMError("GROQ_API_KEY is not set on the server.")

    from langchain_groq import ChatGroq
    return ChatGroq(
        model=settings.GROQ_MODEL,
        groq_api_key=settings.GROQ_API_KEY,
        temperature=0.3,
        timeout=60,
        max_retries=2,
    )


# ── Prompt Template ─────────────────────────────────────────────────
# This tells the LLM HOW to use the retrieved context.
# Clear instructions = better answers.

_rag_prompt = None


def _get_rag_prompt():
    global _rag_prompt
    if _rag_prompt is None:
        from langchain_core.prompts import ChatPromptTemplate
        _rag_prompt = ChatPromptTemplate.from_template(
            """You are an AI technical assistant that analyzes a developer's GitHub profile.
Answer the question using the context below: a profile overview and excerpts from the developer's README files.

Guidelines:
1. **Grounding**: Base every claim about the developer on the context. Never invent repositories, features, numbers or technologies.
2. **Missing information**: If the context doesn't contain the answer, say so plainly. You may still explain a general technical concept, as long as you make clear it is not from their profile.
3. **Explain, don't copy**: Explain how the projects work, their architecture, tech stack and design choices, referencing the context.
4. **Citations**: Always name the specific repository when discussing features or components.
5. **Best project**: If asked for the best or most impressive project, compare the projects in the context on complexity, completeness and technical depth, and explain your reasoning.
6. **Format**: Use Markdown (headings, bullet points, tables, code blocks) where it helps.

Profile overview:
{profile}

README excerpts (most relevant first):
{context}

User's Question: {question}

Technical Answer:"""
        )
    return _rag_prompt


def _format_profile(username: str) -> str:
    """
    Build a short overview of the profile from the saved analysis result.

    The analysis job stores the profile and its repository list in
    status:analyze:{username} when it completes.
    """
    try:
        raw = redis_client.get(f"status:analyze:{username}")
        profile = json.loads(raw).get("profile") if raw else None
    except ValueError:
        profile = None

    if not profile:
        return f"@{username} (no profile overview available)"

    lines = [
        f"{profile.get('name') or username} (@{profile.get('username') or username}), "
        f"{profile.get('public_repos', 0)} public repositories, "
        f"{profile.get('followers', 0)} followers."
    ]
    if profile.get("bio"):
        lines.append(f"Bio: {profile['bio']}")

    lines.append("Analyzed repositories (top by stars + forks):")
    for repo in profile.get("repositories", []):
        details = [repo.get("language") or "unknown language", f"{repo.get('stars', 0)} stars"]
        if not repo.get("has_readme"):
            details.append("no README indexed")
        line = f"- {repo['name']} ({', '.join(details)})"
        if repo.get("description"):
            line += f": {repo['description']}"
        lines.append(line)

    return "\n".join(lines)


def _format_context(documents: list[dict]) -> str:
    """
    Format retrieved documents into a single string for the prompt.

    Each chunk is labeled with its source repo for clarity.
    The LLM can then reference specific repos in its answer.
    """
    formatted = []
    for doc in documents:
        repo = doc.get("repo_name", "unknown")
        content = doc.get("content", "")
        formatted.append(
            f"[Repository: {repo}]\n{content}"
        )
    return "\n\n---\n\n".join(formatted)


def ask(username: str, question: str) -> dict:
    """
    Answer a question about a GitHub user's projects using RAG.

    Steps:
    1. Check that the profile has been indexed
    2. Search Redis Vector Store for relevant README chunks
       (uses cosine similarity between question embedding and stored embeddings)
    3. Build the prompt from the profile overview + chunks
    4. Send it to the Groq LLM via LangChain
    5. Return the answer with source repos

    Returns:
        dict: {
            "answer": "The AI-generated response...",
            "sources": ["repo-name-1", "repo-name-2", ...]
        }
    """

    # Step 1: Nothing indexed → don't spend an embedding call on it
    if count_chunks(username) == 0:
        return {
            "answer": (
                f"I don't have any README data for **@{username}** yet. "
                "Data expires 24 hours after analysis, so click **Analyze** "
                "to index the profile, then ask again."
            ),
            "sources": [],
        }

    # Step 2: Semantic search — find the most relevant README chunks
    retrieved_docs = search_similar(query=question, username=username)

    # Step 3: Build and run the LangChain chain
    #
    # Chain explanation:
    #   RAG_PROMPT  → fills in {profile}, {context} and {question}
    #   _get_llm()  → sends the filled prompt to Groq
    #   StrOutputParser() → extracts the text from the LLM response
    #
    # The "|" operator chains these together (LangChain Expression Language)
    from langchain_core.output_parsers import StrOutputParser
    chain = _get_rag_prompt() | _get_llm() | StrOutputParser()

    try:
        answer = chain.invoke({
            "profile": _format_profile(username),
            "context": _format_context(retrieved_docs),
            "question": question,
        })
    except Exception as e:
        logger.exception(f"Groq LLM call failed: {e}")
        raise LLMError(
            "The AI model (Groq) didn't answer. Please try again in a minute."
        ) from e

    # Step 4: Collect unique source repos
    sources = sorted({doc.get("repo_name", "unknown") for doc in retrieved_docs})

    return {
        "answer": answer,
        "sources": sources,
    }
