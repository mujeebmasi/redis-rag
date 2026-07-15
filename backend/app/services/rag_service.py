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
2. We convert the question into an embedding vector
3. We search Redis for the most similar README chunks (embedding_service.search_similar)
4. We build a prompt: "Based on these documents: [...], answer: What projects use FastAPI?"
5. The LLM reads the context and generates an accurate answer
6. We return the answer + source repos

This is the key pattern that makes AI applications reliable and useful.
"""

import asyncio
import logging

from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

logger = logging.getLogger(__name__)

from app.services.embedding_service import search_similar, embed_and_store
from app.services.github_service import analyze_profile
from app.core.config import settings

# ── LLM (Large Language Model) ──────────────────────────────────────
# Using Groq (Llama 3.3 70B) — extremely fast inference and high performance.
# temperature=0.3 means slightly creative but mostly factual answers.


def _get_llm() -> ChatGroq:
    """Create the LLM instance using Groq Llama 3."""
    return ChatGroq(
        model="llama-3.3-70b-versatile",
        groq_api_key=settings.GROQ_API_KEY,
        temperature=0.3,
    )


# ── Prompt Template ─────────────────────────────────────────────────
# This tells the LLM HOW to use the retrieved context.
# Clear instructions = better answers.

RAG_PROMPT = ChatPromptTemplate.from_template(
    """You are an elite AI technical assistant specialized in analyzing GitHub profiles and developer portfolios.
Your goal is to provide insightful, comprehensive, and professional answers about the developer's projects, technical skills, and experience based on the provided context.

Follow these guidelines to deliver outstanding responses:
1. **Primary Context**: Ground your answers in the provided context from the developer's GitHub README files.
2. **Technical Explanation**: Go beyond copy-pasting. Use your deep programming knowledge to explain *how* their projects work, their architecture, tech stack choice, and design patterns, referencing the context.
3. **Structure & Presentation**: Format your answers cleanly using Markdown (bolding, headers, bullet points, table formats, and syntax-highlighted code blocks where appropriate).
4. **Honesty & Reasoning**: If the context doesn't mention a repository, framework, or details needed to answer, state that clearly. You may, however, offer high-level educational explanations of the technical concepts involved while clarifying what is absent from the profile context.
5. **Citations**: Always name the specific repository when discussing features or components.
6. **Determining the Best Project**: If asked to identify the developer's best, most impressive, or most significant project, evaluate the projects mentioned in the context. Consider factors like complexity, completeness, and technical sophistication based on their README details, and provide a reasoned assessment.

Developer's GitHub Context:
{context}

User's Question: {question}

Technical Answer:"""
)


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
    1. Search Redis Vector Store for relevant README chunks
       (uses cosine similarity between question embedding and stored embeddings)
    2. Format them as context for the LLM
    3. Send context + question to Gemini LLM via LangChain
    4. Return the answer with source repos
    
    Args:
        username: GitHub username whose repos to search
        question: The user's natural language question
    
    Returns:
        dict: {
            "answer": "The AI-generated response...",
            "sources": ["repo-name-1", "repo-name-2", ...]
        }
    """

    # Step 1: Semantic search — find the 5 most relevant README chunks
    retrieved_docs = search_similar(
        query=question,
        username=username,
        top_k=5,
    )

    # If nothing is indexed for this user, attempt an automatic fallback:
    # 1. Analyze the GitHub profile (fetch READMEs)
    # 2. Embed and store README chunks in Redis
    # 3. Retry the semantic search once
    if not retrieved_docs:
        try:
            profile_data = asyncio.run(analyze_profile(username))
            repos = profile_data.get("repositories", [])

            stored = embed_and_store(username=username, repositories=repos)

            if stored > 0:
                # Retry the semantic search after indexing
                retrieved_docs = search_similar(
                    query=question,
                    username=username,
                    top_k=5,
                )
        except Exception as e:
            logger.warning(f"Error during automatic fallback indexing for {username}: {str(e)}")
            raise e

    if not retrieved_docs:
        return {
            "answer": (
                f"I don't have any indexed data for '{username}'. "
                "Please analyze their GitHub profile first using POST /github/analyze."
            ),
            "sources": [],
        }

    # Step 2: Format context
    context = _format_context(retrieved_docs)

    # Step 3: Build and run the LangChain chain
    #
    # Chain explanation:
    #   RAG_PROMPT  → fills in {context} and {question}
    #   _get_llm()  → sends the filled prompt to Gemini
    #   StrOutputParser() → extracts the text from the LLM response
    #
    # The "|" operator chains these together (LangChain Expression Language)

    chain = RAG_PROMPT | _get_llm() | StrOutputParser()

    answer = chain.invoke({
        "context": context,
        "question": question,
    })

    # Step 4: Collect unique source repos
    sources = list(set(
        doc.get("repo_name", "unknown")
        for doc in retrieved_docs
    ))

    return {
        "answer": answer,
        "sources": sorted(sources),
    }
